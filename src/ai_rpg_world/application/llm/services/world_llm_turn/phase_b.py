"""Phase B: tool 実行と action-failed / prompt capture。"""

from __future__ import annotations

import logging
from dataclasses import replace as dataclass_replace
from typing import Any, Optional

from ai_rpg_world.application.intent.tool_phase_mapping import phase_for_tool
from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.action_summary_format import (
    format_action_summary_for_display,
    action_history_projection,
)
from ai_rpg_world.application.llm.services.subjective_args import (
    extract_subjective_action_fields,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_TODO_ADD,
    TOOL_NAME_TODO_COMPLETE,
    TOOL_NAME_TODO_LIST,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.intent.value_object.intent import Intent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

from ai_rpg_world.application.llm.services.world_llm_turn.escape_tools import (
    tool_names_from_payload,
)
from ai_rpg_world.application.llm.services.world_llm_turn.prompt_capture import (
    record_prompt_dataset_turn_result,
)
from ai_rpg_world.application.llm.services.world_llm_turn.reason_first_trace import (
    record_reason_first_trace,
)
from ai_rpg_world.application.llm.services.world_llm_turn.tool_dispatch import (
    coerce_arguments,
    execute_tool,
    maybe_interrupt_busy,
    restore_nav_state,
)
from ai_rpg_world.application.llm.services.world_llm_turn.types import (
    LlmPhaseAResult,
    WORLD_ACTION_HESITATION,
    WORLD_ACTION_MOMENTARY_BLANK,
    WORLD_RESULT_HESITATION,
    WORLD_RESULT_MOMENTARY_BLANK,
    action_result_extra_trace_payload,
)

logger = logging.getLogger(__name__)


def run_phase_b(wiring, phase_a: LlmPhaseAResult) -> LlmCommandResultDto:
    """Phase B: Phase A の結果を受けて世界 mutation を適用する。

    serial 実行が前提 (世界 mutation / 観測 broadcast / trace 順序が決定論
    的に並ぶように、Phase A の to_run 順で呼ぶ)。
    """
    player_id = phase_a.player_id
    if phase_a.failure_result is not None:
        result = phase_a.failure_result
        wiring.runtime._record_action_result(
            player_id,
            WORLD_ACTION_HESITATION,
            WORLD_RESULT_HESITATION,
            tool_name=WORLD_ACTION_HESITATION,
            success=False,
            error_code=None,
        )
        record_prompt_dataset_turn_result(wiring, phase_a, result)
        return result
    if phase_a.exception is not None:
        # Phase A で LLM 呼び出しが落ちた場合の救済 path。
        result = LlmCommandResultDto(
            success=False,
            message=WORLD_RESULT_MOMENTARY_BLANK,
            error_code="LLM_API_FAILED",
            remediation="次に意識が戻ったとき、改めて状況を確かめてください。",
            should_reschedule=False,
            was_no_op=True,
            trace_payload={"technical_error_detail": str(phase_a.exception)},
        )
        wiring.runtime._record_action_result(
            player_id,
            WORLD_ACTION_MOMENTARY_BLANK,
            WORLD_RESULT_MOMENTARY_BLANK,
            tool_name=WORLD_ACTION_MOMENTARY_BLANK,
            success=False,
            error_code=None,
        )
        record_prompt_dataset_turn_result(wiring, phase_a, result)
        return result
    prompt = phase_a.prompt
    messages = prompt["messages"]
    tool_call = phase_a.tool_call
    if tool_call is None:
        result = LlmCommandResultDto(
            success=False,
            message=WORLD_RESULT_HESITATION,
            error_code="NO_TOOL_CALL",
            remediation="次は今できることから一つを選んでください。",
            should_reschedule=False,
            was_no_op=True,
        )
        wiring.runtime._record_action_result(
            player_id,
            WORLD_ACTION_HESITATION,
            WORLD_RESULT_HESITATION,
            tool_name=WORLD_ACTION_HESITATION,
            success=False,
            error_code=None,
        )
        record_prompt_dataset_turn_result(wiring, phase_a, result)
        return result

    name = str(tool_call.get("name", ""))
    arguments = coerce_arguments(tool_call.get("arguments"))
    if phase_a.subjective_overrides:
        arguments = {
            **arguments,
            **phase_a.subjective_overrides,
        }
        record_reason_first_trace(
            wiring,
            TraceEventKind.REASON_FIRST_ASSESSMENT_INJECTED,
            player_id,
            reason_first_turn_id=phase_a.reason_first_turn_id,
            tool_name=name,
            injected_fields=sorted(phase_a.subjective_overrides.keys()),
        )
    # Phase 1d: ACTION 自動 trace (実行前)。runtime に trace_recorder が
    # 注入されていれば記録。LlmAgentOrchestrator 経路を通らない world_runtime
    # 専用 wiring のための補完。
    trace_recorder = getattr(wiring.runtime, "trace_recorder", None)
    current_tick: Optional[int] = None
    if trace_recorder is not None:
        try:
            current_tick = int(wiring.runtime.current_tick())
        except Exception:
            current_tick = None
        try:
            trace_recorder.record(
                "action",
                tick=current_tick,
                player_id=int(player_id.value),
                tool=name,
                arguments=arguments,
            )
        except Exception:
            logger.exception("trace_recorder.record(action) failed")
    # multi-tick action 中の中断ロジック: busy 中に "heavy" tool が来たら、
    # まず travel をキャンセルして agent を現在地に着地させてから tool を
    # 実行する (free tool: speech / memo / examine / wait は中断せず通す)。
    # LLM への surface は snapshot の agent_status section で既に通知済み。
    # Review HIGH 1 対応: 中断前の nav_state を snapshot して、tool 実行が
    # 失敗したら travel を復元する (= 「失敗したのに移動が消える」を防ぐ)。
    was_interrupted, nav_snapshot = maybe_interrupt_busy(
        wiring, player_id, name
    )
    infrastructure_failure = False
    try:
        result = execute_tool(
            wiring,
            player_id,
            name,
            arguments,
            prompt["tool_runtime_context"],
            offered_tool_names_at_prompt=tool_names_from_payload(
                phase_a.tools_payload
            ),
        )
    except Exception as exc:
        # PR 6 (#227 / Agent A #7): 旧コードは stack trace を握りつぶしていた
        # ため、何が起きたか追跡不能だった。logger.exception で trace を残す。
        logger.exception(
            "_execute_tool failed for player_id=%s tool=%s arguments=%s",
            player_id.value,
            name,
            arguments,
        )
        result = LlmCommandResultDto(
            success=False,
            message="行動が形にならないまま、時間が過ぎた。",
            error_code="LLM_TOOL_EXECUTION_FAILED",
            remediation="状況を見直し、別の行動を選んでください。",
            trace_payload={"technical_error_detail": str(exc)},
        )
        infrastructure_failure = True
    # Review HIGH 1 対応: tool が失敗したら travel を復元する。
    # 成功時のみ中断確定。失敗時は「travel 継続中だが今 tick は別行動を
    # 試みて失敗した」状態に戻す (LLM が次 tick で travel を再開できる)。
    rolled_back = False
    if not result.success and nav_snapshot is not None:
        restore_nav_state(wiring, player_id, nav_snapshot)
        rolled_back = True
    # 中断が起きていれば result.message に「移動を中断した」prefix を付与。
    # 観測としても次 tick で agent_status の busy=False が読めるので二重保険。
    # ロールバックされた場合は別文面: travel は維持されたまま。
    if was_interrupted and not rolled_back:
        result = dataclass_replace(
            result,
            message="進行中の移動を中断して新しい行動を選択した。 " + result.message,
        )
    elif rolled_back:
        result = dataclass_replace(
            result,
            message="行動は失敗したため、進行中の移動はそのまま継続している。 " + result.message,
        )
    # PR 5 (#227): memo 完了 hint で result.message を augment する。
    # memo_* ツール自身の実行直後は hint を出さない (冗長 / 自己参照ループ
    # 防止)。本家経路 (LlmAgentOrchestrator._maybe_augment_with_memo_hint)
    # と同等。
    if (
        wiring.memo_completion_hint_service is not None
        and name
        and name not in (TOOL_NAME_TODO_ADD, TOOL_NAME_TODO_LIST, TOOL_NAME_TODO_COMPLETE)
    ):
        try:
            # #552 PR-A: memo hint は target/action/result に key すべきで、
            # 主観入力に依存させない。sanitized summary を使う (健全化)。
            action_summary = format_action_summary_for_display(name, arguments)
            # Issue #240 後続: detect() を直接呼び、hint 発火時に trace に
            # MEMO_HINT を emit。これにより実 LLM 試走で「hint が出たか / その後
            # LLM が memo_done を呼んだか」を trace 経由で追える。
            acting = wiring.runtime._acting_being_for(player_id)
            if acting is not None:
                hint = wiring.memo_completion_hint_service.detect(
                    acting.being_id, action_summary, result.message
                )
                if hint is not None:
                    augmented_message = result.message + hint.to_hint_text()
                    result = dataclass_replace(result, message=augmented_message)
                    if trace_recorder is not None:
                        try:
                            trace_recorder.record(
                                TraceEventKind.MEMO_HINT,
                                tick=current_tick,
                                player_id=int(player_id.value),
                                memo_id=hint.memo.id,
                                memo_content=hint.memo.content,
                                similarity=round(hint.similarity, 4),
                                tool_name=name,
                            )
                        except Exception:
                            logger.exception("trace_recorder.record(memo_hint) failed")
        except Exception:
            logger.exception("memo_completion_hint_service.detect failed")
    skip_duplicate_action_log = result.success and name in (
        TOOL_NAME_SPOT_GRAPH_EXPLORE,
        TOOL_NAME_SPOT_GRAPH_INTERACT,
        TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    )
    if not skip_duplicate_action_log:
        # #552 PR-A: raw args の json.dumps をやめ、主観ノイズを落とした
        # sanitized summary を記録する (失敗 / wait / listen 等の経路)。
        # sanitizer が JSON から expected_result を落とすので、構造化フィールドに
        # 予測を残さないと失敗行の [予測:] が消える。subjective を明示的に渡す
        # (成功 core action は do_* 経路で配線済 = U2、ここは generic 経路の補完)。
        # dispatch が resolver の正規値を反映済みの射影を置いていればそれを
        # 使う (置いていない = resolver を通らない tool なら raw から作る)。
        identifier_arguments, free_text_argument_names = (
            action_history_projection(arguments)
        )
        wiring.runtime._record_action_result(
            player_id,
            format_action_summary_for_display(name, arguments),
            result.message,
            tool_name=name,
            success=result.success,
            error_code=None if infrastructure_failure else result.error_code,
            identifier_arguments=identifier_arguments,
            free_text_argument_names=free_text_argument_names,
            **extract_subjective_action_fields(arguments),
        )
    # P6 (目的の見直し): world-action tool の引数に非 null の goal_update が
    # あれば goal store に反映する (GOAL_REVISION_ENABLED OFF / goal store 無し
    # なら no-op)。書き込みゲート (トリガターン限定) は無い。
    apply_goal_update = getattr(
        wiring.runtime, "apply_goal_update_if_present", None
    )
    if callable(apply_goal_update):
        apply_goal_update(player_id, arguments)
    if trace_recorder is not None:
        try:
            trace_payload = action_result_extra_trace_payload(
                result.trace_payload
            )
            trace_recorder.record(
                "action_result",
                tick=current_tick,
                player_id=int(player_id.value),
                tool=name,
                success=result.success,
                error_code=result.error_code,
                result_summary=result.message,
                **trace_payload,
            )
        except Exception:
            logger.exception("trace_recorder.record(action_result) failed")
    # PR 4 (#227): 同一ツール連打を検知し警告観測を注入する。
    # action_result の記録後に呼ぶことで、失敗を繰り返すケースも検知対象
    # に入る。閾値超過時は次ターンの prompt 構築時に observation buffer
    # から drain されて LLM に警告が届く。
    if name:
        cross_tick_trigger = None
        try:
            # PR-AA (Y_after_pr639_640 後続): success / error_code を渡して
            # 「離れた tick に散らばる同一失敗の反復」も検出できるように
            # する。既存の連続 streak 検出とは独立に動作。
            # U6 (STRUCTURED_FAILURE): 閾値到達した回だけ
            # CrossTickFailureTrigger が返る (flag OFF でも戻り値自体は
            # 返るが、_record_structured_failure_evidence が transcriber
            # 未配線を見て no-op にする)。
            cross_tick_trigger = wiring.tool_call_loop_guard.record_and_check(
                player_id,
                name,
                arguments,
                success=result.success,
                error_code=result.error_code,
            )
        except Exception:
            logger.exception("tool_call_loop_guard.record_and_check failed")
        if cross_tick_trigger is not None:
            record_structured_failure_evidence(wiring, player_id, cross_tick_trigger)
    # 失敗 DTO のとき ActionFailed 観測を該当プレイヤーへ投入する。
    # post-hoc に Intent VO を構築し observer に渡す (intent queue 経由は
    # しない — 即時 path で意味のある最小 wire-in)。LLM API レベルや
    # 配線エラーは emitter 側で除外される。
    if not result.success:
        emit_action_failed_observation(wiring, player_id, name, arguments, result)
    record_prompt_dataset_turn_result(wiring, phase_a, result)
    return result

def record_structured_failure_evidence(
    wiring, player_id: PlayerId, trigger: Any
) -> None:
    """U6 (STRUCTURED_FAILURE + salience): loop_guard の cross_tick_failure
    閾値到達を ``BeliefEvidence`` に転記する。

    loop_guard 自身は being_id を解決できない (Being 文脈を持たない
    service のため) ので、being 解決ができる本 presentation 層で
    transcriber を呼ぶ。transcriber 未配線 (SALIENCE_STRUCTURED_FAILURE_ENABLED
    が OFF) のときは no-op。失敗しても turn 自体は止めない
    (loop_guard 本体の警告注入は既に成功しているため)。
    """
    transcriber = getattr(wiring.runtime, "_structured_failure_transcriber", None)
    if transcriber is None:
        return
    aux_resolver = getattr(wiring.runtime, "aux_being_resolver", None)
    aux_world_id = getattr(wiring.runtime, "aux_being_default_world_id", None)
    if aux_resolver is None or aux_world_id is None:
        return
    try:
        being_id = aux_resolver.resolve_being_id(aux_world_id, player_id)
    except Exception:
        logger.exception("structured_failure evidence: being resolution failed")
        return
    if being_id is None:
        return
    try:
        transcriber.record_if_triggered(
            being_id,
            tool_name=trigger.tool_name,
            error_code=trigger.error_code,
            count=trigger.count,
        )
    except Exception:
        logger.exception(
            "structured_failure_transcriber.record_if_triggered failed"
        )

def emit_action_failed_observation(
    wiring,
    player_id: PlayerId,
    tool_name: str,
    arguments: dict[str, Any],
    result: LlmCommandResultDto,
) -> None:
    if wiring.action_failed_emitter is None or wiring.intent_id_generator is None:
        return
    # 空 tool_name は LLM 出力の欠陥 (例: ``{"name": ""}``)。Intent VO は
    # 非空 str を要求するため "unknown" 等で穴埋めすると観測の tool_name
    # フィールドが false-positive な値で汚れる。診断用に warning を残し、
    # 観測そのものは emit しない (LLM API レベル失敗の扱いに準じる)。
    if not tool_name:
        logger.warning(
            "Skipping ActionFailed emission: empty tool_name from LLM "
            "(player=%s error_code=%s)",
            player_id.value,
            result.error_code,
        )
        return
    try:
        current_tick_value = int(wiring.runtime.current_tick())
        tick = WorldTick(current_tick_value)
        intent = Intent(
            intent_id=wiring.intent_id_generator.next_id(),
            player_id=player_id,
            tool_name=tool_name,
            arguments=dict(arguments),
            phase=phase_for_tool(tool_name),
            submitted_at_tick=tick,
            complete_at_tick=tick,
        )
        wiring.action_failed_emitter.on_resolution_failure(intent, result)
    except Exception:
        # observer 発火が turn 結果を倒さないよう吸収 (best-effort)。
        logger.exception(
            "Failed to emit ActionFailed observation for player=%s tool=%s",
            player_id.value,
            tool_name,
        )

