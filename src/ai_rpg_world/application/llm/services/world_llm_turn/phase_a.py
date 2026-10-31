"""Phase A: snapshot 構築 + LLM 呼び出し + reason-first。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.services.world_llm_turn.wiring import (
        WorldLlmWiring,
    )

import copy
import logging
import uuid
from typing import Any

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.dynamic_argument_candidates import (
    inject_dynamic_argument_candidate_table,
)
from ai_rpg_world.application.llm.services.world_llm_turn.escape_tools import (
    filter_definitions_for_escape_llm,
)
from ai_rpg_world.application.llm.services.world_llm_turn.metrics_sink import (
    LlmMetricsTraceSink,
)
from ai_rpg_world.application.llm.services.world_llm_turn.types import (
    LlmPhaseAResult,
    ReasonFirstGateDecision,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_ASSESS_SITUATION
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

logger = logging.getLogger(__name__)

from ai_rpg_world.application.llm.services.world_llm_turn.prompt_capture import (
    build_prompt_capture_context,
    llm_session_kwargs,
)
from ai_rpg_world.application.llm.services.world_llm_turn.reason_first_trace import (
    record_reason_first_trace,
)
from ai_rpg_world.application.llm.services.world_llm_turn.tool_dispatch import (
    coerce_arguments,
)
from ai_rpg_world.application.llm.services.world_llm_turn.truncated_output_retry import (
    TruncatedOutputRetryAllowance,
    invoke_retrying_truncated_output,
)


def resolve_reason_first_gate(wiring: WorldLlmWiring, player_id: PlayerId) -> ReasonFirstGateDecision:
    """reason-first 2段階 turn の Phase A gate を解決する。

    bool flag は「gated reason-first を有効化する」だけで、常時 2段階には
    しない。発火条件は既存 shared state に限定する:

    - loop_guard が直前に警告を注入した
    - 直近 2 件の action result が同一失敗

    callable は PR-3/4 の契約テスト用 override として残す。実 run では
    ``ResolvedLlmRuntimeConfig.reason_first_two_step_enabled`` 由来の bool を使う。
    """

    flag = getattr(wiring.runtime, "reason_first_two_step_enabled", False)
    if callable(flag):
        try:
            enabled = bool(flag(player_id))
        except Exception:
            logger.exception("reason_first_two_step_enabled callable failed")
            return ReasonFirstGateDecision(False, "callable_failed")
        return ReasonFirstGateDecision(enabled, "callable_override" if enabled else "callable_disabled")
    if not bool(flag):
        return ReasonFirstGateDecision(False, "feature_disabled")

    signal = wiring.tool_call_loop_guard.consume_gate_signal(player_id)
    if signal is not None:
        return ReasonFirstGateDecision(True, "loop_guard_warning")
    if has_recent_same_failure(wiring, player_id):
        return ReasonFirstGateDecision(True, "recent_same_failure")
    return ReasonFirstGateDecision(False, "no_trigger")


def has_recent_same_failure(wiring: WorldLlmWiring, player_id: PlayerId) -> bool:
    """ActionResultStore の直近2件が同一失敗なら True。

    新しい検知器は作らず、Phase B が既に保存している共有 action result を
    読むだけに留める。成功が最新なら False になるため、古い失敗で
    reason-first が発火し続けることはない。
    """

    store = getattr(wiring.runtime, "_action_result_store", None)
    get_recent = getattr(store, "get_recent", None)
    if not callable(get_recent):
        return False
    try:
        recent = list(get_recent(player_id, 2))
    except Exception:
        logger.exception("reason-first gate: action_result_store.get_recent failed")
        return False
    if len(recent) < 2:
        return False
    latest, previous = recent[0], recent[1]
    if getattr(latest, "success", True) or getattr(previous, "success", True):
        return False
    latest_key = wiring._action_failure_key(latest)
    previous_key = wiring._action_failure_key(previous)
    return latest_key is not None and latest_key == previous_key


def action_failure_key(entry: Any) -> tuple[str, str, str] | None:
    tool_name = str(getattr(entry, "tool_name", "") or "").strip()
    error_code = str(getattr(entry, "error_code", "") or "").strip()
    fingerprint = str(getattr(entry, "argument_fingerprint", "") or "").strip()
    action_summary = str(getattr(entry, "action_summary", "") or "").strip()
    identity = fingerprint or action_summary
    if not tool_name or not error_code or not identity:
        return None
    return (tool_name, error_code, identity)


def build_tools_payload(
    wiring: WorldLlmWiring, player_id: PlayerId, *, tool_schema_mode: str = "legacy"
) -> list[dict[str, Any]]:
    """runtime tool 定義を LLM API の tools payload へ変換する。"""

    definitions = (
        wiring.runtime.get_tool_definitions(player_id=player_id)
        if tool_schema_mode == "legacy"
        else wiring.runtime.get_tool_definitions(tool_schema_mode=tool_schema_mode, player_id=player_id)
    )
    return [
        {
            "type": "function",
            "function": {
                "name": definition.name,
                "description": definition.description,
                "parameters": definition.parameters,
            },
        }
        for definition in filter_definitions_for_escape_llm(definitions)
    ]


def run_phase_a(wiring: WorldLlmWiring, player_id: PlayerId) -> LlmPhaseAResult:
    """Phase A: snapshot 構築 + LLM 呼び出し。並列化可能。

    - build_full_prompt は observation buffer を drain するが、buffer は
      player_id keyed で別プレイヤー間で衝突しないので並列実行できる
    - LLM 呼び出しはブロッキング HTTP。GIL を解放するので thread 並列で
      実時間を稼げる
    - 例外は捕まえて結果に詰める (Phase B 側で LlmCommandResultDto 化)
    """
    tool_choice = getattr(
        getattr(wiring.runtime, "_runtime_config", None),
        "llm_tool_choice",
        "required",
    )
    # auto の補助文に載せる名前は、この呼び出しで実際に API へ渡す payload
    # から取る。宣言一覧を別に持つと disabled_tools や状態フィルタとずれる。
    tools_payload = build_tools_payload(wiring, player_id)
    tool_names = [t.get("function", {}).get("name") for t in tools_payload if t.get("function", {}).get("name")]
    action_instruction = None
    if tool_choice == "auto":
        action_instruction = wiring.runtime.escape_game_action_instruction(tool_names)
    if action_instruction is None:
        prompt = wiring.runtime.build_full_prompt(player_id)
    else:
        prompt = wiring.runtime.build_full_prompt(
            player_id,
            action_instruction=action_instruction,
        )
    reason_first_gate = resolve_reason_first_gate(wiring, player_id)
    if reason_first_gate.enabled:
        return run_reason_first_phase_a(wiring, player_id, prompt, gate_reason=reason_first_gate.reason)
    prompt = inject_dynamic_argument_candidate_table(prompt, set(tool_names))
    # PR-A: 脱出ランタイムで恒久的に UNSUPPORTED_TOOL になる tool は LLM に
    # 見せない。Y_after_issue621 trace で set_sub_location が 3 回叩かれて
    # 全部失敗していた問題を入口で塞ぐ。
    # 実験 #356 対応: LLM 1 呼び出しごとに metrics (wall_latency / tokens / TPS)
    # を trace に流す。Phase A の中で player_id / tick の context を sink に閉
    # じ込めて、後で集計スクリプトが per-agent / per-model 分布を出せるよう
    # にする。
    # PR-F: LLM がその tick で実際に prompt 経由で見た tool 名集合も渡す。
    # tools_payload から function name を抽出する (= OpenAI function calling
    # 形式の "type":"function" 構造から function.name を読む)。
    metrics_sink = build_llm_metrics_sink(wiring, player_id, tool_names=tool_names)
    last_llm_call_id: str | None = None
    # prompt dataset の attempt_index は、このターンの呼び出しの数で振る。呼び出しが例外で落ちても番号が重ならないため。
    calls_made = 0

    def _invoke(
        *,
        attempt_index: int,
        parent_attempt_id: str | None = None,
        messages_override: list[dict[str, Any]] | None = None,
        reasoning_effort: str | None = None,
        call_metrics_sink: Any | None = None,
    ) -> dict[str, Any] | None:
        nonlocal last_llm_call_id, calls_made
        calls_made += 1
        # tool_choice は解決済み実験設定をそのまま渡す。required が両立しない
        # provider を使う run だけ、profile で明示した auto と末尾指示を使う。
        # 呼び出し中の静かな降格は行わない。
        messages = messages_override or prompt["messages"]
        prompt_capture_context = build_prompt_capture_context(
            wiring,
            player_id=player_id,
            prompt=prompt,
            tool_choice=tool_choice,
            reasoning_effort=reasoning_effort,
            attempt_index=attempt_index,
            parent_attempt_id=parent_attempt_id,
            phase="one_step",
            exposed_tool_names=set(tool_names),
        )
        if prompt_capture_context is not None:
            last_llm_call_id = prompt_capture_context.context.llm_call_id
        invoke_kwargs = {
            "metrics_sink": metrics_sink if call_metrics_sink is None else call_metrics_sink,
            "reasoning_effort": reasoning_effort,
            **llm_session_kwargs(wiring, player_id),
        }
        if prompt_capture_context is not None:
            invoke_kwargs["prompt_capture_context"] = prompt_capture_context
        invoked: dict[str, Any] | None = wiring.llm_client.invoke(
            messages,
            tools_payload,
            tool_choice,
            **invoke_kwargs,
        )
        return invoked

    def _result(tool_call: dict[str, Any] | None, exception: BaseException | None) -> LlmPhaseAResult:
        return LlmPhaseAResult(
            player_id=player_id,
            prompt=prompt,
            tools_payload=tools_payload,
            tool_call=tool_call,
            exception=exception,
            llm_call_id=last_llm_call_id,
        )

    try:
        tool_call = invoke_retrying_truncated_output(
            lambda attempt, parent, effort, watch: _invoke(
                attempt_index=attempt,
                parent_attempt_id=parent,
                reasoning_effort=effort,
                call_metrics_sink=watch,
            ),
            wiring=wiring,
            player_id=player_id,
            phase="one_step",
            metrics_sink=metrics_sink,
            attempt_index=0,
            parent_attempt_id=None,
            last_llm_call_id=lambda: last_llm_call_id,
            allowance=TruncatedOutputRetryAllowance(),
        )
    except Exception as exc:  # KeyboardInterrupt / SystemExit / GeneratorExit は伝播
        logger.exception("Phase A llm invoke failed for player_id=%s", player_id.value)
        return _result(None, exc)

    if tool_choice == "auto" and tool_call is None:
        # auto では文章回答が返り得る。最初の失敗を即 no-op にせず、同じ
        # prefix の末尾だけを強めて 1 回だけ再試行する。回数を設定化すると
        # run 条件と費用が静かに増えるため固定する。
        retry_messages = [dict(message) for message in prompt["messages"]]
        retry_messages[-1]["content"] = (
            str(retry_messages[-1].get("content", ""))
            + "\n\n文章での回答は受け取れません。いま呼べるツールを必ず 1 つ呼び出してください。"
        )
        try:
            parent = last_llm_call_id
            tool_call = _invoke(
                attempt_index=calls_made,
                parent_attempt_id=parent,
                messages_override=retry_messages,
            )
        except Exception as exc:  # noqa: BLE001 — 2回目の失敗は通常の失敗結果へ渡す
            logger.exception(
                "Phase A auto retry invoke failed for player_id=%s",
                player_id.value,
            )
            return _result(None, exc)

    return _result(tool_call, None)


def run_reason_first_phase_a(
    wiring: Any,
    player_id: PlayerId,
    prompt: dict[str, Any],
    *,
    gate_reason: str,
) -> LlmPhaseAResult:
    """reason-first 2段階ターンの Phase A。

    step1 は ``assess_situation`` を named tool_choice で強制する。成立した
    評価だけを step2 末尾 prompt に追記し、step2 は評価 tool を除いた
    action tool list で通常 action を required にする。契約違反時は行動
    実行へ進めない。
    """

    assess_tools_payload = build_tools_payload(wiring, player_id, tool_schema_mode="reason_first")
    action_tools_payload = [
        tool for tool in assess_tools_payload if tool.get("function", {}).get("name") != TOOL_NAME_ASSESS_SITUATION
    ]
    assess_tool_names = [
        t.get("function", {}).get("name") for t in assess_tools_payload if t.get("function", {}).get("name")
    ]
    action_tool_names = [
        t.get("function", {}).get("name") for t in action_tools_payload if t.get("function", {}).get("name")
    ]
    assess_metrics_sink = build_llm_metrics_sink(wiring, player_id, tool_names=assess_tool_names)
    action_metrics_sink = build_llm_metrics_sink(wiring, player_id, tool_names=action_tool_names)
    reason_first_turn_id = f"reason-first-{uuid.uuid4().hex}"
    last_llm_call_id: str | None = None
    # 評価の段の prompt dataset の attempt_index は、評価の段の呼び出しの数で振る。呼び出しが例外で落ちても番号が重ならないため。
    assess_calls_made = 0
    assess_choice = {
        "type": "function",
        "function": {"name": TOOL_NAME_ASSESS_SITUATION},
    }
    record_reason_first_trace(
        wiring,
        TraceEventKind.REASON_FIRST_STARTED,
        player_id,
        reason_first_turn_id=reason_first_turn_id,
        gate_reason=gate_reason,
        assess_phase_tool_count=len(assess_tool_names),
        action_phase_tool_count=len(action_tool_names),
        retry_limit=1,
    )

    def _result(
        tool_call: dict[str, Any] | None,
        exception: BaseException | None,
        *,
        subjective_overrides: dict[str, Any] | None = None,
        failure_result: LlmCommandResultDto | None = None,
    ) -> LlmPhaseAResult:
        return LlmPhaseAResult(
            player_id=player_id,
            prompt=prompt,
            tools_payload=action_tools_payload,
            tool_call=tool_call,
            exception=exception,
            llm_call_id=last_llm_call_id,
            subjective_overrides=subjective_overrides or {},
            failure_result=failure_result,
            reason_first_turn_id=reason_first_turn_id,
        )

    def _invoke(
        messages: list[dict[str, Any]],
        tools_payload: list[dict[str, Any]],
        tool_choice: Any,
        *,
        metrics_sink: Any,
        attempt_index: int,
        parent_attempt_id: str | None,
        phase: str,
        reasoning_effort: str | None = None,
    ) -> dict[str, Any] | None:
        nonlocal last_llm_call_id, assess_calls_made
        if phase == "assess_phase":
            assess_calls_made += 1
        prompt_capture_context = build_prompt_capture_context(
            wiring,
            player_id=player_id,
            prompt=prompt,
            tool_choice=tool_choice,
            reasoning_effort=reasoning_effort,
            attempt_index=attempt_index,
            parent_attempt_id=parent_attempt_id,
            phase=phase,
            exposed_tool_names={
                str(tool.get("function", {}).get("name"))
                for tool in tools_payload
                if tool.get("function", {}).get("name")
            },
        )
        if prompt_capture_context is not None:
            last_llm_call_id = prompt_capture_context.context.llm_call_id
        invoke_kwargs = {
            "metrics_sink": metrics_sink,
            "reasoning_effort": reasoning_effort,
            "call_phase": phase,
            **llm_session_kwargs(wiring, player_id),
        }
        if prompt_capture_context is not None:
            invoke_kwargs["prompt_capture_context"] = prompt_capture_context
        invoked: dict[str, Any] | None = wiring.llm_client.invoke(
            messages,
            tools_payload,
            tool_choice,
            **invoke_kwargs,
        )
        return invoked

    assessment: dict[str, str] | None = None
    parent_attempt_id: str | None = None
    # 打ち切られたときの呼び直しは、評価の段で 1 回まで。評価の再試行の 2 周目に持ち越す。
    assess_allowance = TruncatedOutputRetryAllowance()
    for attempt_index in (0, 1):
        try:
            tool_call = invoke_retrying_truncated_output(
                lambda attempt, parent, effort, watch: _invoke(
                    prompt["messages"],
                    assess_tools_payload,
                    assess_choice,
                    metrics_sink=watch,
                    attempt_index=attempt,
                    parent_attempt_id=parent,
                    phase="assess_phase",
                    reasoning_effort=effort,
                ),
                wiring=wiring,
                player_id=player_id,
                phase="assess_phase",
                metrics_sink=assess_metrics_sink,
                attempt_index=assess_calls_made,
                parent_attempt_id=parent_attempt_id,
                last_llm_call_id=lambda: last_llm_call_id,
                allowance=assess_allowance,
            )
        except Exception as exc:  # noqa: BLE001 — retry 後の fail-fast に変換する
            logger.warning(
                "reason-first assess_phase invoke failed for player_id=%s",
                player_id.value,
                exc_info=True,
            )
            final = attempt_index == 1
            record_reason_first_trace(
                wiring,
                TraceEventKind.REASON_FIRST_STEP_FAILED,
                player_id,
                reason_first_turn_id=reason_first_turn_id,
                gate_reason=gate_reason,
                phase="assess_phase",
                reason="invoke_exception",
                error_type=type(exc).__name__,
                error_message=str(exc),
                attempt_index=attempt_index,
                final=final,
            )
            if final:
                # 評価の不成立ではなく呼び出しの失敗なので、次の tick に回す経路へ渡す (#1595)。
                return _result(None, exc)
            parent_attempt_id = last_llm_call_id
            continue

        parsed, failure_reason = parse_assessment_tool_call(tool_call)
        if parsed is not None:
            assessment = parsed
            record_reason_first_trace(
                wiring,
                TraceEventKind.REASON_FIRST_ASSESSED,
                player_id,
                reason_first_turn_id=reason_first_turn_id,
                attempt_index=attempt_index,
            )
            break
        final = attempt_index == 1
        returned_tool = str(tool_call.get("name", "")) if isinstance(tool_call, dict) else None
        record_reason_first_trace(
            wiring,
            TraceEventKind.REASON_FIRST_STEP_FAILED,
            player_id,
            reason_first_turn_id=reason_first_turn_id,
            gate_reason=gate_reason,
            phase="assess_phase",
            reason=failure_reason,
            returned_tool=returned_tool,
            attempt_index=attempt_index,
            final=final,
        )
        if final:
            return _result(
                None,
                None,
                failure_result=reason_first_failed_result("REASON_FIRST_STEP_FAILED"),
            )
        parent_attempt_id = last_llm_call_id

    if assessment is None:
        return _result(
            None,
            None,
            failure_result=reason_first_failed_result("REASON_FIRST_STEP_FAILED"),
        )

    action_messages = append_reason_first_assessment(prompt["messages"], assessment)
    prompt = dict(prompt)
    prompt["messages"] = action_messages
    prompt["action_instruction"] = _REASON_FIRST_ACTION_INSTRUCTION
    prompt = inject_dynamic_argument_candidate_table(prompt, set(action_tool_names), in_scene=False)
    action_messages = prompt["messages"]
    try:
        action_tool_call = invoke_retrying_truncated_output(
            lambda attempt, parent, effort, watch: _invoke(
                action_messages,
                action_tools_payload,
                "required",
                metrics_sink=watch,
                attempt_index=attempt,
                parent_attempt_id=parent,
                phase="action_phase",
                reasoning_effort=effort,
            ),
            wiring=wiring,
            player_id=player_id,
            phase="action_phase",
            metrics_sink=action_metrics_sink,
            attempt_index=0,
            parent_attempt_id=None,
            last_llm_call_id=lambda: last_llm_call_id,
            allowance=TruncatedOutputRetryAllowance(),
        )
    except Exception as exc:  # noqa: BLE001 — 既存 LLM_API_FAILED 経路へ渡す
        logger.exception(
            "reason-first action_phase invoke failed for player_id=%s",
            player_id.value,
        )
        return _result(None, exc)

    action_name = str(action_tool_call.get("name", "")) if isinstance(action_tool_call, dict) else ""
    if action_name == TOOL_NAME_ASSESS_SITUATION:
        record_reason_first_trace(
            wiring,
            TraceEventKind.REASON_FIRST_STEP_FAILED,
            player_id,
            reason_first_turn_id=reason_first_turn_id,
            gate_reason=gate_reason,
            phase="action_phase",
            reason="assessment_tool_returned_in_action_phase",
            returned_tool=action_name,
            action_phase_tool_count=len(action_tool_names),
            attempt_index=0,
            final=True,
        )
        return _result(
            None,
            None,
            failure_result=reason_first_failed_result("REASON_FIRST_ACTION_PHASE_INVALID_TOOL"),
        )
    if action_tool_call is not None:
        record_reason_first_trace(
            wiring,
            TraceEventKind.REASON_FIRST_ACTION_SELECTED,
            player_id,
            reason_first_turn_id=reason_first_turn_id,
            gate_reason=gate_reason,
            tool_name=action_name,
            action_phase_tool_count=len(action_tool_names),
        )
    return _result(
        action_tool_call,
        None,
        subjective_overrides=assessment,
    )


def parse_assessment_tool_call(
    tool_call: dict[str, Any] | None,
) -> tuple[dict[str, str] | None, str]:
    if not isinstance(tool_call, dict):
        return None, "no_tool_call"
    if str(tool_call.get("name", "")) != TOOL_NAME_ASSESS_SITUATION:
        return None, "unexpected_tool"
    arguments = coerce_arguments(tool_call.get("arguments"))
    inner_thought = str(arguments.get("inner_thought") or "").strip()
    if not inner_thought:
        return None, "missing_inner_thought"
    return {"inner_thought": inner_thought}, ""


def append_reason_first_assessment(
    messages: list[dict[str, Any]],
    assessment: dict[str, str],
) -> list[dict[str, Any]]:
    copied = copy.deepcopy(messages)
    lines = [
        "【行動前の状況評価】",
        f"- 考え: {assessment['inner_thought']}",
    ]
    lines.append(_REASON_FIRST_ACTION_INSTRUCTION)
    suffix = "\n\n" + "\n".join(lines)
    if copied and copied[-1].get("role") == "user":
        copied[-1] = dict(copied[-1])
        copied[-1]["content"] = str(copied[-1].get("content", "")) + suffix
        return copied
    copied.append({"role": "user", "content": suffix.lstrip()})
    return copied


_REASON_FIRST_ACTION_INSTRUCTION = "- 上の評価を踏まえ、実行する行動 tool を1つ選ぶ。inner_thought は再生成しない。"


def reason_first_failed_result(error_code: str) -> LlmCommandResultDto:
    if error_code == "REASON_FIRST_ACTION_PHASE_INVALID_TOOL":
        return LlmCommandResultDto(
            success=False,
            message=("行動選択段階で状況評価 tool が返されたため、このターンは行動しませんでした。"),
            error_code=error_code,
            remediation="行動段階では assess_situation ではなく、実行する行動 tool を1つ選んでください。",
            should_reschedule=False,
            was_no_op=True,
        )
    return LlmCommandResultDto(
        success=False,
        message=("行動前の状況評価が成立しなかったため、このターンは行動しませんでした。"),
        error_code=error_code,
        remediation="次のターンで状況を読み直し、実行する行動 tool を選び直してください。",
        should_reschedule=False,
        was_no_op=True,
    )


def build_llm_metrics_sink(
    wiring: WorldLlmWiring,
    player_id: PlayerId,
    tool_names: list[str] | None = None,
) -> Any | None:
    """Phase A の LLM 呼び出し metrics を trace に流す sink を構築する。

    trace_recorder が無い (= テスト等) なら None を返して、litellm 側で
    no-op になる。

    Review HIGH 2 対応: current_tick は **record 時点** で取得する
    (sink 構築時の固定値だと、遅い LLM 呼び出しが tick 境界を跨いだとき
    stale な tick が記録される)。
    Review MEDIUM 後続: inner class の動的定義を避け、module-level の
    `LlmMetricsTraceSink` クラスを再利用する (parallel 経路の hot path)。
    """
    trace_recorder = getattr(wiring.runtime, "trace_recorder", None)
    if trace_recorder is None:
        return None
    return LlmMetricsTraceSink(
        trace_recorder=trace_recorder,
        runtime=wiring.runtime,
        player_id=player_id,
        tool_names=tool_names,
    )
