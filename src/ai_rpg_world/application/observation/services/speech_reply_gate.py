"""他者の発言で起こすかを、返答の必要性で決める門。

1 人の発言が、その場で聞いた全員を次の tick に起こしている。会議では 8 人が
毎 tick 全員喋る形になり、返答の要らない人まで LLM を回す。

聞いた一人ひとりについて「この発言に自分が返答する必要があるか」を型付き判断
(Noul) に問い、明らかに不要なときだけ起こさない。取りこぼし (返答すべき人を
起こさない) は許さない側に倒す。閾値は ``noul < skip_below`` で、小さく置く。

## 判断の前の門で守るもの

判断に委ねると「呼ばれても答えない」静かな失敗になるので、次は判断を引かずに
必ず起こす。

- 囁き (宛先が自分にしか届かない)
- 本文に自分の名前がある発言
- 一定 tick 発言していない聞き手 (沈黙の上限)

``player_spoke`` 以外の観測はこの門の対象外で、そのまま起こす。投票の要求など
返答が要る観測は別の型で届くので、構造的に抑制されない。

## 観測は残す

起こさなくても観測は buffer に積まれたまま (appender が scheduler より先に
走る)。次に起きたときに読める。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
    NoulQuestion,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

logger = logging.getLogger(__name__)

#: trace の ``question``。他の型付き判断と並べて数えるための名前。
QUESTION_NAME = "speech_reply_needed"

REASON_NOT_SPEECH = "not_speech"
REASON_WHISPERED_TO_ME = "whispered_to_me"
REASON_NAMED_IN_SPEECH = "named_in_speech"
REASON_SILENCE_LIMIT = "silence_limit"
REASON_JUDGED_NEEDED = "judged_needed"
REASON_JUDGED_UNNEEDED = "judged_unneeded"
REASON_JUDGMENT_UNAVAILABLE = "judgment_unavailable"

DEFAULT_SKIP_BELOW = 0.05
DEFAULT_SILENCE_LIMIT_TICKS = 3
DEFAULT_RECENT_LIMIT = 5


@dataclass(frozen=True)
class WakeDecision:
    """起こすかどうかと、その理由。trace にそのまま載せる。"""

    wake: bool
    reason: str
    probability: Optional[float] = None
    latency_ms: Optional[float] = None
    source: Optional[str] = None
    unavailable_reason: Optional[str] = None


class IWakeGate(ABC):
    """``schedules_turn`` の観測を「起床候補」と読み替え、起こすかを決める。"""

    @abstractmethod
    def decide(self, player_id: PlayerId, output: ObservationOutput) -> WakeDecision:
        raise NotImplementedError


class SpeechReplyGate(IWakeGate):
    """他者の発言について、返答の必要性で起床を決める。"""

    def __init__(
        self,
        judgment_port: ITypedJudgmentPort,
        *,
        current_tick_provider: Callable[[], int],
        listener_name_resolver: Callable[[PlayerId], str],
        skip_below: float = DEFAULT_SKIP_BELOW,
        silence_limit_ticks: int = DEFAULT_SILENCE_LIMIT_TICKS,
        recent_observations_provider: Optional[
            Callable[[PlayerId], Sequence[str]]
        ] = None,
        trace_recorder_provider: Optional[Callable[[], Any]] = None,
        recent_limit: int = DEFAULT_RECENT_LIMIT,
    ) -> None:
        if not isinstance(judgment_port, ITypedJudgmentPort):
            raise TypeError("judgment_port must be ITypedJudgmentPort")
        if not 0.0 < float(skip_below) <= 1.0:
            raise ValueError("skip_below must be in (0, 1]")
        if int(silence_limit_ticks) < 1:
            raise ValueError("silence_limit_ticks must be 1 or greater")
        self.judgment_port = judgment_port
        self.skip_below = float(skip_below)
        self.silence_limit_ticks = int(silence_limit_ticks)
        self._current_tick = current_tick_provider
        self._listener_name = listener_name_resolver
        self._recent_observations = recent_observations_provider
        self._trace_recorder_provider = trace_recorder_provider
        self._recent_limit = int(recent_limit)
        self._last_spoke_tick: Dict[int, int] = {}
        self._first_seen_tick: Dict[int, int] = {}

    def decide(self, player_id: PlayerId, output: ObservationOutput) -> WakeDecision:
        structured = output.structured
        if structured.get("type") != "player_spoke":
            return WakeDecision(wake=True, reason=REASON_NOT_SPEECH)

        tick = int(self._current_tick())
        speaker_key = structured.get("speaker_player_id")
        if speaker_key is not None:
            self._last_spoke_tick[int(speaker_key)] = tick
        listener_key = int(player_id.value)
        self._first_seen_tick.setdefault(listener_key, tick)

        listener_name = self._listener_name(player_id)
        decision = self._decide_speech(
            player_id, listener_key, listener_name, structured, output.prose, tick
        )
        self._record(tick, player_id, listener_name, structured, output.prose, decision)
        return decision

    def _decide_speech(
        self,
        player_id: PlayerId,
        listener_key: int,
        listener_name: str,
        structured: Mapping[str, Any],
        heard: str,
        tick: int,
    ) -> WakeDecision:
        if structured.get("channel") == "whisper":
            return WakeDecision(wake=True, reason=REASON_WHISPERED_TO_ME)
        content = str(structured.get("content") or "")
        if listener_name and listener_name in content:
            return WakeDecision(wake=True, reason=REASON_NAMED_IN_SPEECH)
        since_spoke = tick - self._last_spoke_tick.get(
            listener_key, self._first_seen_tick[listener_key]
        )
        if since_spoke >= self.silence_limit_ticks:
            return WakeDecision(wake=True, reason=REASON_SILENCE_LIMIT)

        try:
            answer = self.judgment_port.judge(
                self._state(player_id, listener_name, structured, heard),
                {QUESTION_NAME: self._question(listener_name)},
            )[QUESTION_NAME]
        except TypedJudgmentUnavailableException as exc:
            return WakeDecision(
                wake=True,
                reason=REASON_JUDGMENT_UNAVAILABLE,
                unavailable_reason=getattr(exc, "error_code", "UNAVAILABLE"),
            )
        except KeyError:
            return WakeDecision(
                wake=True,
                reason=REASON_JUDGMENT_UNAVAILABLE,
                unavailable_reason="TYPED_JUDGMENT_ANSWER_MISSING",
            )
        probability = float(answer.value)
        wake = probability >= self.skip_below
        return WakeDecision(
            wake=wake,
            reason=REASON_JUDGED_NEEDED if wake else REASON_JUDGED_UNNEEDED,
            probability=probability,
            latency_ms=answer.latency_ms,
            source=answer.source.value,
        )

    def _state(
        self,
        player_id: PlayerId,
        listener_name: str,
        structured: Mapping[str, Any],
        heard: str,
    ) -> Mapping[str, Any]:
        recent: Sequence[str] = ()
        if self._recent_observations is not None:
            try:
                recent = tuple(self._recent_observations(player_id))
            except Exception:
                logger.warning("recent observations unavailable", exc_info=True)
        recent = tuple(text for text in recent if text and text != heard)
        return {
            "speech": {
                "speaker": structured.get("speaker"),
                "channel": structured.get("channel"),
                "heard": heard,
            },
            "listener": {
                "name": listener_name,
                "recent_situation": list(recent[-self._recent_limit :]),
            },
        }

    @staticmethod
    def _question(listener_name: str) -> NoulQuestion:
        return NoulQuestion(
            instructions=(
                f"{listener_name}は、この発言に自分が返答する必要があるか。"
            ),
            true_means="返答する必要がある。自分に向けられている、答えを求められている、"
            "または自分の立場から言うべきことがある",
            false_means="返答しなくてよい。自分には向けられておらず、答えも求められて"
            "いない",
        )

    def _record(
        self,
        tick: int,
        player_id: PlayerId,
        listener_name: str,
        structured: Mapping[str, Any],
        heard: str,
        decision: WakeDecision,
    ) -> None:
        provider = self._trace_recorder_provider
        recorder = provider() if provider is not None else None
        if recorder is None:
            return
        try:
            recorder.record(
                TraceEventKind.TYPED_JUDGMENT,
                tick=tick,
                player_id=int(player_id.value),
                question=QUESTION_NAME,
                listener=listener_name,
                speaker=structured.get("speaker"),
                heard=heard[:120],
                probability=(
                    round(decision.probability, 4)
                    if decision.probability is not None
                    else None
                ),
                skip_below=self.skip_below,
                woke=decision.wake,
                reason=decision.reason,
                latency_ms=decision.latency_ms,
                source=decision.source,
                unavailable_reason=decision.unavailable_reason,
            )
        except Exception:
            logger.exception("trace_recorder.record(typed_judgment) failed")


__all__ = [
    "DEFAULT_RECENT_LIMIT",
    "DEFAULT_SILENCE_LIMIT_TICKS",
    "DEFAULT_SKIP_BELOW",
    "IWakeGate",
    "QUESTION_NAME",
    "REASON_JUDGED_NEEDED",
    "REASON_JUDGED_UNNEEDED",
    "REASON_JUDGMENT_UNAVAILABLE",
    "REASON_NAMED_IN_SPEECH",
    "REASON_NOT_SPEECH",
    "REASON_SILENCE_LIMIT",
    "REASON_WHISPERED_TO_ME",
    "SpeechReplyGate",
    "WakeDecision",
]
