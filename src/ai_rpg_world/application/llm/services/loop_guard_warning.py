"""検出器の signal を受けて、ループ警告を観測・trace・gate signal に出す。"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.application.llm.services.loop_diagnosis import (
    QUESTION_NAME as LOOP_DIAGNOSIS_QUESTION,
)
from ai_rpg_world.application.llm.services.loop_diagnosis import (
    LoopDiagnosis,
    LoopDiagnosisJudgment,
    RepeatReason,
)
from ai_rpg_world.application.llm.services.loop_guard_detectors import (
    ConsecutiveRepeat,
    CrossTickFailureRepeat,
    RepeatSignal,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)
from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

logger = logging.getLogger(__name__)

_CROSS_TICK_WARNING_TEMPLATES: tuple[str, ...] = (
    "⚠ あなたは直近 {window} tick 以内で {action_summary} を同じ失敗 "
    "(`{error_code}`) で {count} 回繰り返している。"
    "対処のヒント: {remediation} この行動は状況が変わるまで必ず失敗する。"
    "次は {action_summary} 以外の行動を選ぶこと。別の対象、別の場所、待機、"
    "所持品の使用、仲間への相談のいずれかに切り替えること。",
    "⚠ {action_summary} は直近 {window} tick 以内に {count} 回、同じ理由 "
    "(`{error_code}`) で失敗している。対処のヒント: {remediation} "
    "状況が変わっていないなら再試行してはいけない。次の行動では、この対象・"
    "この手段を避け、観測を読み直して別ルートを選ぶこと。時間経過で解ける"
    "類なら待機してから後で再試行すること。",
    "⚠ これは確定した反復失敗です: {action_summary} / `{error_code}` / "
    "{count} 回。対処のヒント: {remediation} 今すぐ同じ行動を止めること。"
    "移動する、別対象を選ぶ、必要条件を満たす、または仲間に状況を伝える"
    "行動を選ぶこと。",
)

# 同じ文面が繰り返し届くと LLM が文面ごと無視するようになるおそれがあるので、
# 発火のたびに文面を順繰りに変える。
_WARNING_TEMPLATES: tuple[str, ...] = (
    "⚠ 直近 {consecutive} ターン連続で {action_summary} を同じ引数で実行している。"
    "同じ入力を続けても状況は広がらない。次は {action_summary} 以外の行動を"
    "選ぶこと。移動、別対象、所持品、会話、待機のいずれかに切り替えること。",
    "⚠ あなたは {action_summary} に {consecutive} 回連続で固着している。"
    "次のターンで同じ行動を選んではいけない。現在の観測を読み直し、目的を"
    "進める別の手段を選ぶこと。",
    "⚠ {consecutive} 回続けて {action_summary} を選んでいる。世界から新しい"
    "反応を得るには入力を変える必要がある。次は対象・場所・手段のどれかを"
    "必ず変えること。",
    "⚠ 同じ行動の連続を検出した: {action_summary} × {consecutive}。"
    "このまま繰り返さないこと。周囲を確認する、別の候補を選ぶ、仲間に伝える、"
    "必要なら待つ、のいずれかを実行すること。",
    "⚠ {action_summary} を {consecutive} 連続で実行している。これは行動の停滞です。"
    "次の行動では同じツールと同じ対象を使わず、別の選択肢を試すこと。",
)


_TARGET_ARG_KEYS: tuple[str, ...] = (
    # ``object_label`` は interact の対象引数が ``target_label`` に改名された
    # 時点で、どの tool からも渡らなくなったので消した (``target_label`` は
    # 下に既にある)。使われない key を残すと「対応済みに見えて実は死んでいる
    # spec」になる。
    "destination_label",
    "target_player_label",
    "item_label",
    "ground_item_label",
    "sub_location_label",
    "target_label",
    "inventory_item_label",
)


def _parse_argument_fingerprint(fingerprint: str) -> dict[str, Any]:
    if not isinstance(fingerprint, str):
        return {}
    try:
        parsed = json.loads(fingerprint)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _stringify_target_value(value: Any) -> str | None:
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    return None


def _extract_target_summary_from_args(args: dict[str, Any]) -> str | None:
    """``give_item`` は ``gives`` 配列に対象が入るため、相手名を優先して短くまとめる。"""
    gives = args.get("gives")
    if isinstance(gives, list):
        names: list[str] = []
        for entry in gives:
            if not isinstance(entry, dict):
                continue
            name = _stringify_target_value(entry.get("target_player_label"))
            if name is not None and name not in names:
                names.append(name)
        if len(names) == 1:
            return names[0]
        if len(names) > 1:
            return f"{names[0]} ほか"

    for key in _TARGET_ARG_KEYS:
        value = _stringify_target_value(args.get(key))
        if value is not None:
            return value
    return None


def build_action_summary(tool_name: str, fingerprint: str) -> str:
    args = _parse_argument_fingerprint(fingerprint)
    target_summary = _extract_target_summary_from_args(args)
    if target_summary is None:
        return f"`{tool_name}`"
    return f"`{tool_name}`（対象: {target_summary}）"


@dataclass(frozen=True)
class LoopGuardGateSignal:
    """loop_guard が実際に警告を発火した事実を Phase A gate へ渡す短命 signal。"""

    pattern: str
    tool_name: str
    fingerprint: str
    error_code: str | None = None
    tick: int | None = None


@dataclass(frozen=True)
class RecentAction:
    """見立ての材料にする直近の行動 1 件。"""

    action: str
    succeeded: bool | None
    result: str | None
    #: 発言の内容。行動の要約には対象名しか出ないので、依頼の言い直しを見分ける材料に足す。
    said: str | None = None


#: 見立ての材料に載せる、いま届いている観測の上限。
_OBSERVATION_LIMIT = 8

#: 文面の区分。見立てを採らなかったときは今の順繰りの文面を使う。
_DEFAULT_WORDING = "default"


def _quote(text: str | None) -> str:
    return f"「{text.rstrip('。')}」" if text else ""


def _repetition_fact(signal: RepeatSignal, action: str) -> str:
    if isinstance(signal, ConsecutiveRepeat):
        return f"⚠ {action} を {signal.consecutive} 回続けて同じ引数で実行している。"
    return (
        f"⚠ {action} は直近 {signal.window} tick 以内に {signal.count} 回、"
        f"同じ理由 (`{signal.error_code}`) で失敗している。"
    )


def _reason_facts(
    reason: RepeatReason,
    *,
    action: str,
    location: str | None,
    recent: Sequence[RecentAction],
    observation_count: int,
) -> str:
    """理由ごとに、本人が読み落としていそうな世界の事実を並べる。命令は書かない。"""
    same = [r for r in recent if r.action == action]
    latest = same[-1] if same else None
    latest_result = _quote(latest.result if latest else None)
    here = f"いまの居場所は「{location}」。" if location else ""
    if reason is RepeatReason.ACHIEVED:
        success = next((r for r in reversed(same) if r.succeeded and r.result), None)
        done = f"この行動は前に成功している: {_quote(success.result)}。" if success else ""
        return done + here
    if reason is RepeatReason.STATE_MISTAKEN:
        last = f"直近の結果: {latest_result}。" if latest_result else ""
        return here + last
    if reason is RepeatReason.MISSING_PRECONDITION:
        failure = next((r for r in reversed(same) if r.succeeded is False and r.result), None)
        return (
            f"直近の失敗: {_quote(failure.result)}。"
            if failure
            else ""
        )
    if reason is RepeatReason.WAITING:
        return here + f"いま届いている観測は {observation_count} 件。"
    if reason is RepeatReason.UNANSWERED_REQUEST:
        last = f"直近の結果: {latest_result}。" if latest_result else ""
        said = recent[-1].said if recent else None
        if not said:
            return last
        # 宛先の有無で行動の要約が変わるので、発言は内容で数える。
        times = sum(1 for r in recent if r.said == said)
        return last + f"同じ内容を伝えたのは {times} 回目。"
    last = f"同じ手段で得た結果: {latest_result}。" if latest_result else ""
    return last


class LoopWarningEmitter:
    """signal を警告の観測にし、trace に残し、reason-first gate へ知らせる。

    見立て (``diagnosis``) があれば、警告を出す前に繰り返しの理由を問い、
    採れた理由の文面にする。採れなくても警告は必ず出す。
    """

    def __init__(
        self,
        *,
        observation_buffer: IObservationContextBuffer,
        time_label_provider: Callable[[], str | None],
        clock: Callable[[], datetime],
        trace_recorder_resolver: Callable[[], ITraceRecorder | None],
        diagnosis: LoopDiagnosis | None = None,
        location_provider: Callable[[PlayerId], str | None] | None = None,
    ) -> None:
        self._observation_buffer = observation_buffer
        self._time_label_provider = time_label_provider
        self._clock = clock
        self._resolve_trace_recorder = trace_recorder_resolver
        self._diagnosis = diagnosis
        self._location_provider = location_provider
        self._warn_count: dict[int, int] = {}
        self._cross_tick_warn_count: dict[int, int] = {}
        self._last_gate_signal: dict[int, LoopGuardGateSignal] = {}

    def emit(
        self,
        player_id: PlayerId,
        signal: RepeatSignal,
        recent: Sequence[RecentAction] = (),
    ) -> None:
        if isinstance(signal, ConsecutiveRepeat):
            self._emit_consecutive(player_id, signal, recent)
        elif isinstance(signal, CrossTickFailureRepeat):
            self._emit_cross_tick_failure(player_id, signal, recent)
        else:
            raise TypeError(f"unknown repeat signal: {type(signal).__name__}")

    def consume_gate_signal(self, player_id: PlayerId) -> LoopGuardGateSignal | None:
        return self._last_gate_signal.pop(player_id.value, None)

    def _emit_consecutive(
        self,
        player_id: PlayerId,
        signal: ConsecutiveRepeat,
        recent: Sequence[RecentAction],
    ) -> None:
        key = player_id.value
        game_time_label = self._time_label_provider()
        warn_index = self._warn_count.get(key, 0)
        self._warn_count[key] = warn_index + 1
        template = _WARNING_TEMPLATES[warn_index % len(_WARNING_TEMPLATES)]
        default_prose = template.format(
            tool_name=signal.tool_name,
            action_summary=build_action_summary(signal.tool_name, signal.fingerprint),
            consecutive=signal.consecutive,
        )
        prose, wording = self._word(player_id, signal, "streak", default_prose, recent)
        self._observation_buffer.append(
            player_id,
            self._entry(
                prose,
                structured={
                    "loop_guard": True,
                    "tool_name": signal.tool_name,
                    "argument_fingerprint": signal.fingerprint,
                    "consecutive_count": signal.consecutive,
                },
                game_time_label=game_time_label,
            ),
        )
        self._record_trace(
            tick=signal.tick,
            player_id=int(player_id.value),
            tool_name=signal.tool_name,
            argument_fingerprint=signal.fingerprint,
            consecutive_count=signal.consecutive,
            game_time_label=game_time_label,
            **wording,
        )
        self._last_gate_signal[key] = LoopGuardGateSignal(
            pattern="streak",
            tool_name=signal.tool_name,
            fingerprint=signal.fingerprint,
            tick=signal.tick,
        )

    def _emit_cross_tick_failure(
        self,
        player_id: PlayerId,
        signal: CrossTickFailureRepeat,
        recent: Sequence[RecentAction],
    ) -> None:
        key = player_id.value
        warn_index = self._cross_tick_warn_count.get(key, 0)
        self._cross_tick_warn_count[key] = warn_index + 1
        game_time_label = self._time_label_provider()
        template = _CROSS_TICK_WARNING_TEMPLATES[
            warn_index % len(_CROSS_TICK_WARNING_TEMPLATES)
        ]
        default_prose = template.format(
            action_summary=build_action_summary(signal.tool_name, signal.fingerprint),
            tool_name=signal.tool_name,
            error_code=signal.error_code,
            count=signal.count,
            window=signal.window,
            remediation=get_remediation(signal.error_code),
        )
        prose, wording = self._word(
            player_id, signal, "cross_tick_failure", default_prose, recent
        )
        self._observation_buffer.append(
            player_id,
            self._entry(
                prose,
                structured={
                    "loop_guard": True,
                    "pattern": "cross_tick_failure",
                    "tool_name": signal.tool_name,
                    "argument_fingerprint": signal.fingerprint,
                    "error_code": signal.error_code,
                    "count": signal.count,
                    "window": signal.window,
                },
                game_time_label=game_time_label,
            ),
        )
        self._last_gate_signal[key] = LoopGuardGateSignal(
            pattern="cross_tick_failure",
            tool_name=signal.tool_name,
            fingerprint=signal.fingerprint,
            error_code=signal.error_code,
            tick=signal.tick,
        )
        # ``consecutive_count`` は「連続」の意味を持つので、こちらは別の
        # フィールド名 ``window_count`` を使う。
        self._record_trace(
            tick=signal.tick,
            player_id=int(player_id.value),
            tool_name=signal.tool_name,
            argument_fingerprint=signal.fingerprint,
            window_count=signal.count,
            window_size=signal.window,
            game_time_label=game_time_label,
            pattern="cross_tick_failure",
            error_code=signal.error_code,
            **wording,
        )

    def _word(
        self,
        player_id: PlayerId,
        signal: RepeatSignal,
        pattern: str,
        default_prose: str,
        recent: Sequence[RecentAction],
    ) -> tuple[str, dict[str, str]]:
        """見立てを問い、文面と、警告の trace に足す文面の区分を返す。

        見立てが無いときは区分を足さない。見立てを入れていない run の trace を
        今と同じ形に保つため。
        """
        diagnosis = self._diagnosis
        if diagnosis is None:
            return default_prose, {}
        try:
            return self._word_by_diagnosis(
                diagnosis, player_id, signal, pattern, default_prose, recent
            )
        except Exception:
            # ここで漏れると警告も gate signal も出ず、離れた tick の失敗は発火を
            # 記録済みなので窓の間は二度と鳴らない。
            logger.exception("loop_diagnosis wording failed")
            return default_prose, {"wording": _DEFAULT_WORDING}

    def _word_by_diagnosis(
        self,
        diagnosis: LoopDiagnosis,
        player_id: PlayerId,
        signal: RepeatSignal,
        pattern: str,
        default_prose: str,
        recent: Sequence[RecentAction],
    ) -> tuple[str, dict[str, str]]:
        action = build_action_summary(signal.tool_name, signal.fingerprint)
        location = self._location(player_id)
        observations = [
            e.output.prose
            for e in self._observation_buffer.get_observations(player_id)
            if e.output.prose
        ][-_OBSERVATION_LIMIT:]
        state = self._state(signal, action, recent, location, observations)
        judgment = diagnosis.diagnose(state)
        self._record_judgment(player_id, signal, pattern, state, judgment)
        if judgment.reason is None:
            return default_prose, {"wording": _DEFAULT_WORDING}
        prose = _repetition_fact(signal, action) + _reason_facts(
            judgment.reason,
            action=action,
            location=location,
            recent=recent,
            observation_count=len(observations),
        )
        return prose, {"wording": judgment.reason.value}

    def _location(self, player_id: PlayerId) -> str | None:
        if self._location_provider is None:
            return None
        try:
            return self._location_provider(player_id) or None
        except Exception:
            return None

    @staticmethod
    def _state(
        signal: RepeatSignal,
        action: str,
        recent: Sequence[RecentAction],
        location: str | None,
        observations: Sequence[str],
    ) -> dict[str, Any]:
        """判断の材料。名前だけを入れ、整数 ID と本人の目的は入れない (#222)。

        件数は文で渡す。Jev に数えさせず、数値を ID と取り違えさせない。
        """
        if isinstance(signal, ConsecutiveRepeat):
            repetition = f"同じ引数で {signal.consecutive} 回連続"
        else:
            repetition = (
                f"直近 {signal.window} tick 以内に、同じ失敗 ({signal.error_code}) で "
                f"{signal.count} 回"
            )
        state: dict[str, Any] = {
            "repeated_action": action,
            "repetition": repetition,
            "recent_actions": [
                {
                    "action": r.action,
                    **({"said": r.said} if r.said else {}),
                    "succeeded": r.succeeded,
                    "result": r.result,
                }
                for r in recent
            ],
        }
        if location:
            state["current_location"] = location
        if observations:
            state["observations_now"] = list(observations)
        return state

    def _record_judgment(
        self,
        player_id: PlayerId,
        signal: RepeatSignal,
        pattern: str,
        state: dict[str, Any],
        judgment: LoopDiagnosisJudgment,
    ) -> None:
        recorder = self._resolve_trace_recorder()
        if recorder is None:
            return
        try:
            recorder.record(
                TraceEventKind.TYPED_JUDGMENT,
                tick=signal.tick,
                player_id=int(player_id.value),
                question=LOOP_DIAGNOSIS_QUESTION,
                pattern=pattern,
                tool_name=signal.tool_name,
                chosen=judgment.chosen,
                probabilities=dict(judgment.probabilities),
                probability=judgment.probability,
                confidence=judgment.confidence,
                min_confidence=judgment.min_confidence,
                accepted=judgment.reason is not None,
                reason=judgment.reason.value if judgment.reason else None,
                fallback_reason=judgment.fallback.value if judgment.fallback else None,
                unavailable_reason=judgment.unavailable_reason,
                latency_ms=judgment.latency_ms,
                source=judgment.source,
                state=state,
            )
        except Exception:
            logger.exception("trace_recorder.record(loop_diagnosis) failed")

    def _record_trace(self, **payload: Any) -> None:
        recorder = self._resolve_trace_recorder()
        if recorder is None:
            return
        try:
            recorder.record(TraceEventKind.LOOP_GUARD_WARNING, **payload)
        except Exception:
            # trace 失敗は警告の注入を止めない
            pass

    def _entry(
        self,
        prose: str,
        *,
        structured: dict[str, Any],
        game_time_label: str | None,
    ) -> ObservationEntry:
        return ObservationEntry(
            occurred_at=self._clock(),
            output=ObservationOutput(
                prose=prose,
                structured=structured,
                observation_category="self_only",
                schedules_turn=False,
                breaks_movement=False,
            ),
            game_time_label=game_time_label,
        )
