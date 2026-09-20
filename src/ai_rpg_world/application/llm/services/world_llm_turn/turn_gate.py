"""tick の終わりに「いま自分が動く必要があるか」を型付き判断に問う門。

観測 1 件ごとに `schedules_turn` で起こす形では、会議のように 1 tick に 7 件の
発言が届く場を絞れない。7 件すべてが不要と判定されないと寝られず、実データでは
1 件も減らなかった (design_decisions #217)。

この門は `run_scheduled_turns` の直前で、pending の一人ひとりについて、その人の
buffer に溜まった未読の観測をまとめて渡し、1 回だけ問う。否なら回さない。観測は
buffer に残り、次に起きたときに読める。

## 判断の前の門で守るもの

- `self_only` / `environment` の観測が 1 件でもあれば起こす。被ダメージ、所持品、
  警報、投票の要求は本人か世界の変化で、聞き流せない
- 囁き、本文に自分の名前がある発言があれば起こす
- 一定 tick 回っていない人は起こす (沈黙の上限)
- 未読の観測が無い人 (自己 reschedule で pending に居る人) は起こす
- 会議中は、候補の中で少なくとも 1 人は起こす。会議は沈黙が続くと流れる。門の
  せいで流れた会議は「議論が尽きた」と見分けられない

判断の対象は `social` の観測だけが溜まった人に限る。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
    NoulQuestion,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

logger = logging.getLogger(__name__)

QUESTION_NAME = "turn_needed"

REASON_NO_PENDING = "no_pending_observation"
REASON_NOT_ONLY_SOCIAL = "not_only_social"
REASON_WHISPERED_TO_ME = "whispered_to_me"
REASON_NAMED_IN_SPEECH = "named_in_speech"
REASON_SILENCE_LIMIT = "silence_limit"
REASON_MEETING_FLOOR = "meeting_floor"
REASON_JUDGED_NEEDED = "judged_needed"
REASON_JUDGED_UNNEEDED = "judged_unneeded"
REASON_JUDGMENT_UNAVAILABLE = "judgment_unavailable"

DEFAULT_SKIP_BELOW = 0.15
DEFAULT_SILENCE_LIMIT_TICKS = 3
DEFAULT_OBSERVATION_LIMIT = 16


@dataclass(frozen=True)
class TurnDecision:
    """1 人ぶんの決定。trace にそのまま載せる。"""

    player_id: PlayerId
    wake: bool
    reason: str
    pending_count: int
    probability: float | None = None
    latency_ms: float | None = None
    source: str | None = None
    unavailable_reason: str | None = None


class TurnGate:
    """pending の一人ひとりについて、いま回すかを決める。"""

    def __init__(
        self,
        judgment_port: ITypedJudgmentPort,
        *,
        current_tick_provider: Callable[[], int],
        player_name_resolver: Callable[[PlayerId], str],
        pending_observations_provider: Callable[[PlayerId], Sequence[ObservationOutput]],
        is_meeting_provider: Callable[[], bool],
        skip_below: float = DEFAULT_SKIP_BELOW,
        silence_limit_ticks: int = DEFAULT_SILENCE_LIMIT_TICKS,
        trace_recorder_provider: Callable[[], Any] | None = None,
        observation_limit: int = DEFAULT_OBSERVATION_LIMIT,
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
        self._player_name = player_name_resolver
        self._pending = pending_observations_provider
        self._is_meeting = is_meeting_provider
        self._trace_recorder_provider = trace_recorder_provider
        self._observation_limit = int(observation_limit)
        self._last_run_tick: dict[int, int] = {}

    def decide_wave(self, player_ids: Sequence[PlayerId]) -> list[PlayerId]:
        """この tick に回す人を返す。決定は全員ぶん trace に残す。"""
        tick = int(self._current_tick())
        decisions = [self._decide(pid, tick) for pid in player_ids]
        if decisions and self._is_meeting() and not any(d.wake for d in decisions):
            # 会議は誰も動かないと流れる。門のせいで流した会議は、議論が尽きて
            # 流れた会議と trace 上で見分けられない。確率が最も高い 1 人を起こす。
            floor = max(decisions, key=lambda d: d.probability or 0.0)
            decisions = [
                TurnDecision(
                    player_id=d.player_id,
                    wake=True,
                    reason=REASON_MEETING_FLOOR,
                    pending_count=d.pending_count,
                    probability=d.probability,
                    latency_ms=d.latency_ms,
                    source=d.source,
                )
                if d is floor
                else d
                for d in decisions
            ]
        for d in decisions:
            self._record(tick, d)
            if d.wake:
                self._last_run_tick[int(d.player_id.value)] = tick
        return [d.player_id for d in decisions if d.wake]

    def _decide(self, player_id: PlayerId, tick: int) -> TurnDecision:
        key = int(player_id.value)
        self._last_run_tick.setdefault(key, tick)
        pending = list(self._pending(player_id))
        count = len(pending)
        if not pending:
            return TurnDecision(player_id, True, REASON_NO_PENDING, count)
        if any(o.observation_category != "social" for o in pending):
            return TurnDecision(player_id, True, REASON_NOT_ONLY_SOCIAL, count)
        name = self._player_name(player_id)
        speeches = [o.structured for o in pending if o.structured.get("type") == "player_spoke"]
        if any(s.get("channel") == "whisper" for s in speeches):
            return TurnDecision(player_id, True, REASON_WHISPERED_TO_ME, count)
        if name and any(name in str(s.get("content") or "") for s in speeches):
            return TurnDecision(player_id, True, REASON_NAMED_IN_SPEECH, count)
        if tick - self._last_run_tick[key] >= self.silence_limit_ticks:
            return TurnDecision(player_id, True, REASON_SILENCE_LIMIT, count)

        try:
            answer = self.judgment_port.judge(
                self._state(name, pending), {QUESTION_NAME: self._question(name)}
            )[QUESTION_NAME]
        except TypedJudgmentUnavailableException as exc:
            return TurnDecision(
                player_id, True, REASON_JUDGMENT_UNAVAILABLE, count,
                unavailable_reason=getattr(exc, "error_code", "UNAVAILABLE"),
            )
        except KeyError:
            return TurnDecision(
                player_id, True, REASON_JUDGMENT_UNAVAILABLE, count,
                unavailable_reason="TYPED_JUDGMENT_ANSWER_MISSING",
            )
        probability = float(answer.value)
        wake = probability >= self.skip_below
        return TurnDecision(
            player_id, wake,
            REASON_JUDGED_NEEDED if wake else REASON_JUDGED_UNNEEDED,
            count,
            probability=probability,
            latency_ms=answer.latency_ms,
            source=answer.source.value,
        )

    def _state(self, name: str, pending: Sequence[ObservationOutput]) -> Mapping[str, Any]:
        recent = [o.prose for o in pending if o.prose][-self._observation_limit :]
        return {
            "listener": {"name": name, "in_meeting": bool(self._is_meeting())},
            "observations_this_tick": recent,
        }

    @staticmethod
    def _question(name: str) -> NoulQuestion:
        return NoulQuestion(
            instructions=(
                f"{name}は、いま届いたこれらの観測を受けて、次に自分が何か行動"
                " (発言を含む) する必要があるか。"
            ),
            true_means=(
                "自分が動く必要がある。答えを求められている、自分の立場から言うべき"
                "ことがある、または見過ごせない変化がある"
            ),
            false_means=(
                "動かなくてよい。他人同士のやり取りや自分に関わらない報告で、様子を"
                "見ていればよい"
            ),
        )

    def _record(self, tick: int, d: TurnDecision) -> None:
        provider = self._trace_recorder_provider
        recorder = provider() if provider is not None else None
        if recorder is None:
            return
        try:
            recorder.record(
                TraceEventKind.TYPED_JUDGMENT,
                tick=tick,
                player_id=int(d.player_id.value),
                question=QUESTION_NAME,
                pending_count=d.pending_count,
                probability=round(d.probability, 4) if d.probability is not None else None,
                skip_below=self.skip_below,
                woke=d.wake,
                reason=d.reason,
                latency_ms=d.latency_ms,
                source=d.source,
                unavailable_reason=d.unavailable_reason,
            )
        except Exception:
            logger.exception("trace_recorder.record(typed_judgment) failed")


__all__ = [
    "DEFAULT_SILENCE_LIMIT_TICKS",
    "DEFAULT_SKIP_BELOW",
    "QUESTION_NAME",
    "REASON_JUDGED_NEEDED",
    "REASON_JUDGED_UNNEEDED",
    "REASON_JUDGMENT_UNAVAILABLE",
    "REASON_MEETING_FLOOR",
    "REASON_NAMED_IN_SPEECH",
    "REASON_NOT_ONLY_SOCIAL",
    "REASON_NO_PENDING",
    "REASON_SILENCE_LIMIT",
    "REASON_WHISPERED_TO_ME",
    "TurnDecision",
    "TurnGate",
]
