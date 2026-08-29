"""Phase A: snapshot 構築 + LLM 呼び出し + reason-first。"""

from __future__ import annotations

import copy
import logging
import uuid
from typing import Any, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_ASSESS_SITUATION
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

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


def resolve_reason_first_gate(
    wiring, player_id: PlayerId
) -> ReasonFirstGateDecision:
    """reason-first 2段階 turn の Phase A gate を解決する。

    bool flag は「gated reason-first を有効化する」だけで、常時 2段階には
    しない。発火条件は既存 shared state に限定する:

    - loop_guard が直前に警告を注入した
    - 直近 2 件の action result が同一失敗
    - stagnation band が strong

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
        return ReasonFirstGateDecision(
            enabled, "callable_override" if enabled else "callable_disabled"
        )
    if not bool(flag):
        return ReasonFirstGateDecision(False, "feature_disabled")

    signal = wiring.tool_call_loop_guard.consume_gate_signal(player_id)
    if signal is not None:
        return ReasonFirstGateDecision(True, "loop_guard_warning")
    if has_recent_same_failure(wiring, player_id):
        return ReasonFirstGateDecision(True, "recent_same_failure")
    if is_stagnation_reason_first_armed(wiring, player_id):
        return ReasonFirstGateDecision(True, "stagnation_strong")
    return ReasonFirstGateDecision(False, "no_trigger")

def has_recent_same_failure(wiring, player_id: PlayerId) -> bool:
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

def action_failure_key(entry: Any) -> Optional[tuple[str, str, str]]:
    tool_name = str(getattr(entry, "tool_name", "") or "").strip()
    error_code = str(getattr(entry, "error_code", "") or "").strip()
    fingerprint = str(getattr(entry, "argument_fingerprint", "") or "").strip()
    action_summary = str(getattr(entry, "action_summary", "") or "").strip()
    identity = fingerprint or action_summary
    if not tool_name or not error_code or not identity:
        return None
    return (tool_name, error_code, identity)

def is_stagnation_reason_first_armed(wiring, player_id: PlayerId) -> bool:
    """停滞 reflect 注入直後の一発ラッチと band strong が揃ったときだけ True。

    band-gated reasoning と同じ入力を使うが、band だけを見ると停滞中の
    毎 turn で reason-first が発火してしまう。ここでは既存ラッチも peek し、
    「reflect 注入直後の 1 行動だけ」に頻度を揃える。
    """

    latch = getattr(wiring.runtime, "_stagnation_reasoning_latch", None)
    is_armed = getattr(latch, "is_armed", None)
    if not callable(is_armed):
        return False
    try:
        armed = bool(is_armed(player_id))
    except Exception:
        logger.exception("reason-first gate: stagnation latch check failed")
        return False
    if not armed:
        return False
    resolver = getattr(wiring.runtime, "_resolve_stagnation_band_value", None)
    if not callable(resolver):
        return False
    try:
        return str(resolver(player_id)) == "strong"
    except Exception:
        logger.exception("reason-first gate: stagnation band resolution failed")
        return False

def consume_stagnation_reason_first_latch(wiring, player_id: PlayerId) -> None:
    """reason-first が停滞ラッチを使ったとき、一発権を消費する。

    reason-first 経路では ``resolve_turn_reasoning_effort`` を呼ばないため、
    band-gated reasoning 側の commit/abandon 消費に乗らない。ここで消費し、
    strong band が続いても同じ reflect から毎 turn 2段階へ入らないようにする。
    """

    latch = getattr(wiring.runtime, "_stagnation_reasoning_latch", None)
    consume = getattr(latch, "consume", None)
    if not callable(consume):
        return
    try:
        consume(player_id)
    except Exception:
        logger.exception("reason-first gate: stagnation latch consume failed")

def build_tools_payload(
    wiring, player_id: PlayerId, *, tool_schema_mode: str = "legacy"
) -> list[dict[str, Any]]:
    """runtime tool 定義を LLM API の tools payload へ変換する。"""

    definitions = (
        wiring.runtime.get_tool_definitions(player_id=player_id)
        if tool_schema_mode == "legacy"
        else wiring.runtime.get_tool_definitions(
            tool_schema_mode=tool_schema_mode, player_id=player_id
        )
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
        for definition in filter_definitions_for_escape_llm(
            definitions
        )
    ]

def run_phase_a(wiring, player_id: PlayerId) -> LlmPhaseAResult:
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
    tool_names = [
        t.get("function", {}).get("name")
        for t in tools_payload
        if t.get("function", {}).get("name")
    ]
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
        return run_reason_first_phase_a(
            wiring, player_id, prompt, gate_reason=reason_first_gate.reason
        )
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
    # 案A (band-gated thinking): 停滞 strong の局面で reflect 注入直後の 1 行動
    # だけ reasoning を焚く。flag OFF / 対象外なら None (= 既定のまま reasoning
    # OFF・プロンプト byte 不変)。判断と AGENT_REASONING_ENGAGED trace は runtime
    # 側に閉じ込め、ここは effort を invoke に橋渡しし、失敗時の降格を扱う。
    reasoning_effort = wiring.runtime.resolve_turn_reasoning_effort(player_id)
    last_llm_call_id: Optional[str] = None

    def _invoke(
        effort,
        *,
        attempt_index: int,
        parent_attempt_id: Optional[str] = None,
        messages_override: Optional[list[dict[str, Any]]] = None,
    ):
        nonlocal last_llm_call_id
        # tool_choice は解決済み実験設定をそのまま渡す。required が両立しない
        # provider を使う run だけ、profile で明示した auto と末尾指示を使う。
        # 呼び出し中の静かな降格は行わない。
        messages = messages_override or prompt["messages"]
        prompt_capture_context = build_prompt_capture_context(
            wiring,
            player_id=player_id,
            prompt=prompt,
            tool_choice=tool_choice,
            reasoning_effort=effort,
            attempt_index=attempt_index,
            parent_attempt_id=parent_attempt_id,
            phase="one_step",
        )
        if prompt_capture_context is not None:
            last_llm_call_id = prompt_capture_context.context.llm_call_id
        invoke_kwargs = {
            "metrics_sink": metrics_sink,
            "reasoning_effort": effort,
            **llm_session_kwargs(wiring, player_id),
        }
        if prompt_capture_context is not None:
            invoke_kwargs["prompt_capture_context"] = prompt_capture_context
        return wiring.llm_client.invoke(
            messages, tools_payload, tool_choice,
            **invoke_kwargs,
        )

    def _result(tool_call, exception):
        return LlmPhaseAResult(
            player_id=player_id,
            prompt=prompt,
            tools_payload=tools_payload,
            tool_call=tool_call,
            exception=exception,
            llm_call_id=last_llm_call_id,
        )

    def _fallback_without_reasoning():
        # 餓死ループ修正: 熟考ターンが失敗 (例外 / tool_call なし) したら latch を
        # 消費して「同条件での再試行」を止め、reasoning なしで 1 回だけ降格再試行
        # して行動を成立させる。これをしないと詰まった agent が毎行動 same-condition
        # で失敗し続けて餓死する (実 run v3coop_stagnation_002 の P3)。
        wiring.runtime.abandon_turn_reasoning(player_id)
        try:
            parent = last_llm_call_id
            return _result(
                _invoke(None, attempt_index=1, parent_attempt_id=parent),
                None,
            )
        except Exception as exc:  # noqa: BLE001 — 降格後も失敗なら通常の失敗として詰める
            logger.exception(
                "Phase A fallback (reasoning なし) invoke failed for player_id=%s",
                player_id.value,
            )
            return _result(None, exc)

    try:
        tool_call = _invoke(reasoning_effort, attempt_index=0)
    except Exception as exc:  # KeyboardInterrupt / SystemExit / GeneratorExit は伝播
        if reasoning_effort is None:
            logger.exception(
                "Phase A llm invoke failed for player_id=%s", player_id.value
            )
            return _result(None, exc)
        logger.warning(
            "Phase A reasoning invoke failed for player_id=%s; "
            "latch を消費し reasoning なしで降格再試行する",
            player_id.value, exc_info=True,
        )
        return _fallback_without_reasoning()

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
                reasoning_effort,
                attempt_index=1,
                parent_attempt_id=parent,
                messages_override=retry_messages,
            )
        except Exception as exc:  # noqa: BLE001 — 2回目の失敗は通常の失敗結果へ渡す
            logger.exception(
                "Phase A auto retry invoke failed for player_id=%s",
                player_id.value,
            )
            return _result(None, exc)

    if (
        tool_choice == "required"
        and reasoning_effort is not None
        and tool_call is None
    ):
        # 熟考ターンだが tool_call なし (NO_TOOL_CALL)。commit せず降格再試行。
        logger.warning(
            "Phase A reasoning turn returned no tool_call for player_id=%s; "
            "latch を消費し reasoning なしで降格再試行する",
            player_id.value,
        )
        return _fallback_without_reasoning()

    # 案A HIGH 2: 熟考付き行動が「成立した後にだけ」ラッチを消費し
    # AGENT_REASONING_ENGAGED trace を残す (成立 = 例外なし かつ tool_call あり)。
    if reasoning_effort is not None and tool_call is not None:
        wiring.runtime.commit_turn_reasoning_engaged(player_id, reasoning_effort)
    return _result(tool_call, None)

def run_reason_first_phase_a(
    wiring, player_id: PlayerId, prompt: dict, *, gate_reason: str,
) -> LlmPhaseAResult:
    """reason-first 2段階ターンの Phase A。

    step1 は ``assess_situation`` を named tool_choice で強制する。成立した
    評価だけを step2 末尾 prompt に追記し、step2 は評価 tool を除いた
    action tool list で通常 action を required にする。契約違反時は行動
    実行へ進めない。
    """

    assess_tools_payload = build_tools_payload(
        wiring, player_id, tool_schema_mode="reason_first"
    )
    action_tools_payload = [
        tool
        for tool in assess_tools_payload
        if tool.get("function", {}).get("name") != TOOL_NAME_ASSESS_SITUATION
    ]
    assess_tool_names = [
        t.get("function", {}).get("name")
        for t in assess_tools_payload
        if t.get("function", {}).get("name")
    ]
    action_tool_names = [
        t.get("function", {}).get("name")
        for t in action_tools_payload
        if t.get("function", {}).get("name")
    ]
    assess_metrics_sink = build_llm_metrics_sink(
        wiring, player_id, tool_names=assess_tool_names
    )
    action_metrics_sink = build_llm_metrics_sink(
        wiring, player_id, tool_names=action_tool_names
    )
    reason_first_turn_id = f"reason-first-{uuid.uuid4().hex}"
    last_llm_call_id: Optional[str] = None
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
    if gate_reason == "stagnation_strong":
        consume_stagnation_reason_first_latch(wiring, player_id)

    def _result(
        tool_call: Optional[dict],
        exception: Optional[BaseException],
        *,
        subjective_overrides: Optional[dict[str, Any]] = None,
        failure_result: Optional[LlmCommandResultDto] = None,
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
        parent_attempt_id: Optional[str],
        phase: str,
    ) -> Optional[dict]:
        nonlocal last_llm_call_id
        prompt_capture_context = build_prompt_capture_context(
            wiring,
            player_id=player_id,
            prompt=prompt,
            tool_choice=tool_choice,
            reasoning_effort=None,
            attempt_index=attempt_index,
            parent_attempt_id=parent_attempt_id,
            phase=phase,
        )
        if prompt_capture_context is not None:
            last_llm_call_id = prompt_capture_context.context.llm_call_id
        invoke_kwargs = {
            "metrics_sink": metrics_sink,
            "reasoning_effort": None,
            "call_phase": phase,
            **llm_session_kwargs(wiring, player_id),
        }
        if prompt_capture_context is not None:
            invoke_kwargs["prompt_capture_context"] = prompt_capture_context
        return wiring.llm_client.invoke(
            messages,
            tools_payload,
            tool_choice,
            **invoke_kwargs,
        )

    assessment: Optional[dict[str, str]] = None
    parent_attempt_id: Optional[str] = None
    for attempt_index in (0, 1):
        try:
            tool_call = _invoke(
                prompt["messages"],
                assess_tools_payload,
                assess_choice,
                metrics_sink=assess_metrics_sink,
                attempt_index=attempt_index,
                parent_attempt_id=parent_attempt_id,
                phase="assess_phase",
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
                return _result(
                    None,
                    None,
                    failure_result=reason_first_failed_result(
                        "REASON_FIRST_STEP_FAILED"
                    ),
                )
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
                has_expected_result=bool(parsed.get("expected_result")),
            )
            break
        final = attempt_index == 1
        returned_tool = (
            str(tool_call.get("name", "")) if isinstance(tool_call, dict) else None
        )
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
                failure_result=reason_first_failed_result(
                    "REASON_FIRST_STEP_FAILED"
                ),
            )
        parent_attempt_id = last_llm_call_id

    if assessment is None:
        return _result(
            None,
            None,
            failure_result=reason_first_failed_result(
                "REASON_FIRST_STEP_FAILED"
            ),
        )

    action_messages = append_reason_first_assessment(
        prompt["messages"], assessment
    )
    try:
        action_tool_call = _invoke(
            action_messages,
            action_tools_payload,
            "required",
            metrics_sink=action_metrics_sink,
            attempt_index=0,
            parent_attempt_id=None,
            phase="action_phase",
        )
    except Exception as exc:  # noqa: BLE001 — 既存 LLM_API_FAILED 経路へ渡す
        logger.exception(
            "reason-first action_phase invoke failed for player_id=%s",
            player_id.value,
        )
        return _result(None, exc)

    action_name = (
        str(action_tool_call.get("name", ""))
        if isinstance(action_tool_call, dict)
        else ""
    )
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
            failure_result=reason_first_failed_result(
                "REASON_FIRST_ACTION_PHASE_INVALID_TOOL"
            ),
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
    tool_call: Optional[dict],
) -> tuple[Optional[dict[str, str]], str]:
    if not isinstance(tool_call, dict):
        return None, "no_tool_call"
    if str(tool_call.get("name", "")) != TOOL_NAME_ASSESS_SITUATION:
        return None, "unexpected_tool"
    arguments = coerce_arguments(tool_call.get("arguments"))
    inner_thought = str(arguments.get("inner_thought") or "").strip()
    if not inner_thought:
        return None, "missing_inner_thought"
    assessment = {"inner_thought": inner_thought}
    expected_result = str(arguments.get("expected_result") or "").strip()
    if expected_result:
        assessment["expected_result"] = expected_result
    return assessment, ""

def append_reason_first_assessment(
    messages: list[dict[str, Any]],
    assessment: dict[str, str],
) -> list[dict[str, Any]]:
    copied = copy.deepcopy(messages)
    lines = [
        "【行動前の状況評価】",
        f"- 考え: {assessment['inner_thought']}",
    ]
    expected_result = assessment.get("expected_result")
    if expected_result:
        lines.append(f"- 期待する結果: {expected_result}")
    lines.append(
        "- 上の評価を踏まえ、実行する行動 tool を1つ選ぶ。"
        "inner_thought / expected_result は再生成しない。"
    )
    suffix = "\n\n" + "\n".join(lines)
    if copied and copied[-1].get("role") == "user":
        copied[-1] = dict(copied[-1])
        copied[-1]["content"] = str(copied[-1].get("content", "")) + suffix
        return copied
    copied.append({"role": "user", "content": suffix.lstrip()})
    return copied

def reason_first_failed_result(error_code: str) -> LlmCommandResultDto:
    if error_code == "REASON_FIRST_ACTION_PHASE_INVALID_TOOL":
        return LlmCommandResultDto(
            success=False,
            message=(
                "行動選択段階で状況評価 tool が返されたため、このターンは"
                "行動しませんでした。"
            ),
            error_code=error_code,
            remediation="行動段階では assess_situation ではなく、実行する行動 tool を1つ選んでください。",
            should_reschedule=False,
            was_no_op=True,
        )
    return LlmCommandResultDto(
        success=False,
        message=(
            "行動前の状況評価が成立しなかったため、このターンは行動しませんでした。"
        ),
        error_code=error_code,
        remediation="次のターンで状況を読み直し、実行する行動 tool を選び直してください。",
        should_reschedule=False,
        was_no_op=True,
    )

def build_llm_metrics_sink(
    wiring, player_id: PlayerId, tool_names: Optional[list[str]] = None,
) -> Optional[Any]:
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
