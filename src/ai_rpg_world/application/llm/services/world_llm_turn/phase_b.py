"""Phase B: tool 実行と action-failed / prompt capture。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.services.world_llm_turn.wiring import (
        WorldLlmWiring,
    )

import logging
from dataclasses import replace as dataclass_replace
from typing import Any
from uuid import uuid4

from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.common.execution_provenance import (
    ExecutionProvenance,
    current_execution_provenance,
    execution_provenance_scope,
)
from ai_rpg_world.application.intent.tool_phase_mapping import phase_for_tool
from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.action_summary_format import (
    action_history_projection,
    format_action_summary_for_display,
)
from ai_rpg_world.application.llm.services.memo_completion_hint_service import (
    QUESTION_NAME as MEMO_COMPLETED_QUESTION,
)
from ai_rpg_world.application.llm.services.memo_completion_hint_service import (
    MemoHintDetection,
)
from ai_rpg_world.application.llm.services.subjective_args import (
    extract_subjective_action_fields,
)
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    command_post_commit_result,
)
from ai_rpg_world.application.llm.services.world_llm_turn.escape_tools import (
    offered_tools_from_payload,
)
from ai_rpg_world.application.llm.services.world_llm_turn.memo_turn import (
    apply_memo_from_call,
)
from ai_rpg_world.application.llm.services.world_llm_turn.prompt_capture import (
    record_prompt_dataset_turn_result,
)
from ai_rpg_world.application.llm.services.world_llm_turn.reason_first_trace import (
    record_reason_first_trace,
)
from ai_rpg_world.application.llm.services.world_llm_turn.say_inline_delivery import (
    with_delivery_carried_by,
)
from ai_rpg_world.application.llm.services.world_llm_turn.tool_dispatch import (
    coerce_arguments,
    execute_tool,
    maybe_interrupt_busy,
    restore_nav_state,
)
from ai_rpg_world.application.llm.services.world_llm_turn.types import (
    LLM_CALL_FAILED_ERROR_CODE,
    WORLD_ACTION_HESITATION,
    WORLD_ACTION_MOMENTARY_BLANK,
    WORLD_RESULT_HESITATION,
    WORLD_RESULT_MOMENTARY_BLANK,
    LlmPhaseAResult,
    action_result_extra_trace_payload,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.intent.value_object.intent import Intent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

logger = logging.getLogger(__name__)


def _execution_trace() -> dict[str, Any] | None:
    source = current_execution_provenance()
    return source.to_dict() if source else None


def run_phase_b(wiring: WorldLlmWiring, phase_a: LlmPhaseAResult) -> LlmCommandResultDto:
    """実行境界で当人の手番と要求IDを一度だけ確定する。"""
    runtime = wiring.runtime
    projection = getattr(runtime, "_public_sns_projection", None)
    if projection is not None and phase_a.tool_call is not None and phase_a.exception is None and phase_a.failure_result is None:
        projection.confirm_shown(int(phase_a.player_id), phase_a.prompt.get("sns_shown_notification_ids", ()))
        runtime._public_sns_screens.confirm_presented(int(phase_a.player_id), phase_a.prompt.get("sns_screen_generation"))
    turn = runtime.advance_memory_turn(phase_a.player_id)
    turns = getattr(runtime, "_execution_turns", None)
    if not isinstance(turns, dict):
        turns = {}
        runtime._execution_turns = turns
    pid = int(phase_a.player_id.value)
    # Beingに結びつかない最小構成にも、実際に開始した手番を数える。
    turn = max(turn if isinstance(turn, int) else 0, turns.get(pid, 0) + 1)
    turns[pid] = turn
    call = phase_a.tool_call or {}
    provider_id = call.get("tool_call_id") or call.get("id")
    provenance = ExecutionProvenance(
        execution_request_id=f"execution-{uuid4().hex}",
        actor_player_id=pid,
        actor_turn=turn,
        tool_call_id=provider_id if isinstance(provider_id, str) and provider_id else None,
        llm_call_id=phase_a.llm_call_id,
    )
    with execution_provenance_scope(provenance):
        return _run_phase_b(wiring, phase_a)


def _run_phase_b(wiring: WorldLlmWiring, phase_a: LlmPhaseAResult) -> LlmCommandResultDto:
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
            error_code=LLM_CALL_FAILED_ERROR_CODE,
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
    current_tick: int | None = None
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
                execution_provenance=_execution_trace(),
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
            offered_tools_at_prompt=offered_tools_from_payload(
                phase_a.tools_payload
            ),
        )
    except CommandPostCommitException as exc:
        # 業務状態はcommit済みなので通常失敗へ縮退させない。成功として扱うことで、
        # busy中断の復元やLLMの再実行が確定済み操作を二重適用するのを防ぐ。
        logger.exception(
            "tool command committed but post-commit processing failed: "
            "player_id=%s tool=%s",
            player_id.value,
            name,
        )
        result = with_delivery_carried_by(command_post_commit_result(exc), exc)
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
        result = with_delivery_carried_by(result, exc)
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
    # 済んだかの知らせより先に当てる。同じ行動で消したやることを、済んだのではと問わないため。
    memo_call = apply_memo_from_call(
        wiring,
        player_id,
        tool_name=name,
        arguments=arguments,
        tools_payload=phase_a.tools_payload,
    )
    # PR 5 (#227): メモ帳のやることが済んだかもしれないと、result.message に添える。
    if wiring.memo_completion_hint_service is not None and name:
        try:
            # #552 PR-A: memo hint は target/action/result に key すべきで、
            # 主観入力に依存させない。sanitized summary を使う (健全化)。
            action_summary = format_action_summary_for_display(name, arguments)
            # Issue #240 後続: detect() を直接呼び、hint 発火時に trace に
            # MEMO_HINT を emit。実 LLM 試走で hint が出たかを trace 経由で追える。
            acting = wiring.runtime._acting_being_for(player_id)
            if acting is not None:
                # 同じ行動で足したやることは問わない。足した行動の文と重なるのは当然で、済んだ印ではない。
                detection = wiring.memo_completion_hint_service.detect(
                    acting.being_id,
                    action_summary,
                    result.message,
                    excluded_ids=memo_call.added_memo_ids,
                )
                # #1322: 問うた memo ごとの判断を、採否に関わらず残す。採用分
                # だけ残すと、hint が減った run を見て「意味判定が厳しすぎる」と
                # 誤読する。縮退したときも理由を 1 件残す。
                _record_memo_completion_judgments(
                    detection,
                    trace_recorder=trace_recorder,
                    current_tick=current_tick,
                    player_id=player_id,
                    tool_name=name,
                )
                hint = detection.hint
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
                                # 重なりの割合と確率を同じ数として集計しない。
                                hint_source=hint.source,
                                tool_name=name,
                            )
                        except Exception:
                            logger.exception("trace_recorder.record(memo_hint) failed")
        except Exception:
            logger.exception("memo_completion_hint_service.detect failed")
    if memo_call.feedback:
        result = dataclass_replace(result, message=result.message + memo_call.feedback)
    skip_duplicate_action_log = result.success and name in (
        TOOL_NAME_SPOT_GRAPH_EXPLORE,
        TOOL_NAME_SPOT_GRAPH_INTERACT,
        TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    )
    if not skip_duplicate_action_log:
        # #552 PR-A: raw args の json.dumps をやめ、主観ノイズを落とした
        # sanitized summary を記録する (失敗 / wait / listen 等の経路)。
        # sanitizer が JSON から主観入力を落とすので、構造化フィールドに残すよう
        # subjective を明示的に渡す (成功 core action は do_* 経路で配線済 = U2、
        # ここは generic 経路の補完)。
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
                execution_provenance=_execution_trace(),
                **trace_payload,
            )
        except Exception:
            logger.exception("trace_recorder.record(action_result) failed")
    # PR 4 (#227): 同一ツール連打を検知し警告観測を注入する。
    # action_result の記録後に呼ぶことで、失敗を繰り返すケースも検知対象
    # に入る。閾値超過時は次ターンの prompt 構築時に observation buffer
    # から drain されて LLM に警告が届く。
    if name:
        try:
            # PR-AA (Y_after_pr639_640 後続): success / error_code を渡して
            # 「離れた tick に散らばる同一失敗の反復」も検出できるように
            # する。既存の連続 streak 検出とは独立に動作。
            wiring.tool_call_loop_guard.record_and_check(
                player_id,
                name,
                arguments,
                success=result.success,
                error_code=result.error_code,
                result_summary=result.message,
            )
        except Exception:
            logger.exception("tool_call_loop_guard.record_and_check failed")
    # 失敗 DTO のとき ActionFailed 観測を該当プレイヤーへ投入する。
    # post-hoc に Intent VO を構築し observer に渡す (intent queue 経由は
    # しない — 即時 path で意味のある最小 wire-in)。LLM API レベルや
    # 配線エラーは emitter 側で除外される。
    if not result.success:
        emit_action_failed_observation(wiring, player_id, name, arguments, result)
    record_prompt_dataset_turn_result(wiring, phase_a, result)
    return result


def _record_memo_completion_judgments(
    detection: MemoHintDetection,
    *,
    trace_recorder: Any | None,
    current_tick: int | None,
    player_id: PlayerId,
    tool_name: str | None,
) -> None:
    """memo 完了の判断を trace に残す。記録の失敗で行動を落とさない。"""
    if trace_recorder is None:
        return
    try:
        for judgment in detection.judgments:
            trace_recorder.record(
                TraceEventKind.TYPED_JUDGMENT,
                tick=current_tick,
                player_id=int(player_id.value),
                question=MEMO_COMPLETED_QUESTION,
                memo_id=judgment.memo_id,
                probability=round(judgment.probability, 4),
                min_confidence=judgment.min_probability,
                accepted=judgment.accepted,
                latency_ms=judgment.latency_ms,
                source=judgment.source,
                unavailable_reason=None,
                tool_name=tool_name,
            )
        if detection.unavailable_reason is not None:
            # 判断を得られず重なり判定へ縮退したことを 1 件残す。**ポートを
            # 持たない run と区別できる形にする。**
            trace_recorder.record(
                TraceEventKind.TYPED_JUDGMENT,
                tick=current_tick,
                player_id=int(player_id.value),
                question=MEMO_COMPLETED_QUESTION,
                memo_id=None,
                probability=None,
                min_confidence=None,
                accepted=False,
                latency_ms=None,
                source=None,
                unavailable_reason=detection.unavailable_reason,
                tool_name=tool_name,
            )
    except Exception:
        logger.exception("trace_recorder.record(typed_judgment) failed")


def emit_action_failed_observation(
    wiring: WorldLlmWiring,
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
