"""tick の終わりに「いま自分が動く必要があるか」を型付き判断に問う起動判定。

普通は pending の全員が毎 tick 起動する。この起動判定はその直前で、一人ひとりの
buffer に溜まった未読の観測をまとめて渡し、1 回だけ問う。「本当に不要」と判定
できたとき (確率が閾値未満) だけ回さない。観測は buffer に残り、次に起きたときに
読める。

起こす経路は 1 つも足さない。起動判定は pending を減らすだけで、増やせない。

## 規則で素通しさせない

囁き、名指し、警報、沈黙の長さは、Jev に渡す材料であって、判断を飛ばす規則では
ない。発言単位の起動判定 (#217) と tick 単位の初版 (#219) は「自分宛ては必ず起こす」
などの規則を判断の前に置き、station_drill では 197 件中 155 件が Jev に届く前に
通った。規則が判断の出番を奪うと、フィルタとしての Jev は評価できない。

例外は 2 つ。1 つは未読の観測が無い人 (自己 reschedule で pending に居る人) で、
判断の材料が無いので、そのまま回す。これは規則ではなく材料不足。もう 1 つは成功した
自分の行動のあとに回した人で、`WorldLlmTurnTrigger` がこの判定にかけずに通す。
自分の行動の結果は判定の材料に入らないため (design_decisions D1597)。

## 候補は「未読のある人」全員

`schedules_turn` の観測を受けた人 (pending) だけでなく、未読の観測が 1 件でも
溜まっている人は毎 tick 判断の候補になる。前の tick に寝た人は、新しい観測が
届かなくても溜まった未読を見て判断し直される。観測型ごとの `schedules_turn` の
真偽は候補の選定に関わらず、Jev が中身を見て決める。
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
REASON_JUDGED_NEEDED = "judged_needed"
REASON_JUDGED_UNNEEDED = "judged_unneeded"
REASON_JUDGMENT_UNAVAILABLE = "judgment_unavailable"

DEFAULT_SKIP_BELOW = 0.15
DEFAULT_OBSERVATION_LIMIT = 16

_CATEGORY_LABEL = {
    "self_only": "自分の身に起きたこと",
    "environment": "世界の変化",
    "social": "他者の言動",
}


@dataclass(frozen=True)
class TurnDecision:
    """1 人ぶんの決定。trace にそのまま載せる。"""

    player_id: PlayerId
    wake: bool
    reason: str
    pending_count: int
    categories: Mapping[str, int]
    #: この tick に schedules_turn の観測を受けて pending に入っていたか。偽なら
    #: 未読が溜まっているだけの人。候補の広げ方の効果を trace で見分ける。
    scheduled: bool = True
    #: Jev に渡した観測 (見出しと本文)。起動判定が何を見て決めたかを trace で読むため。
    #: run 003 では、同じ tick 番号の観測から state を復元しようとして、判定より
    #: 後にターンの中で生まれた発言を混ぜてしまい、判断を誤読した。
    observations: tuple[Mapping[str, str], ...] = ()
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
        all_player_ids_provider: Callable[[], Sequence[PlayerId]] | None = None,
        skip_below: float = DEFAULT_SKIP_BELOW,
        trace_recorder_provider: Callable[[], Any] | None = None,
        observation_limit: int = DEFAULT_OBSERVATION_LIMIT,
    ) -> None:
        if not isinstance(judgment_port, ITypedJudgmentPort):
            raise TypeError("judgment_port must be ITypedJudgmentPort")
        if not 0.0 < float(skip_below) <= 1.0:
            raise ValueError("skip_below must be in (0, 1]")
        self.judgment_port = judgment_port
        self.skip_below = float(skip_below)
        self._current_tick = current_tick_provider
        self._player_name = player_name_resolver
        self._pending = pending_observations_provider
        self._is_meeting = is_meeting_provider
        self._all_player_ids = all_player_ids_provider
        self._trace_recorder_provider = trace_recorder_provider
        self._observation_limit = int(observation_limit)

    def candidates(self, scheduled: Sequence[PlayerId]) -> list[PlayerId]:
        """判断の候補を返す。pending の人に、未読のある人を足す。

        順序は pending の人が先、次に未読のある人を ID 順。同じ人は 1 度だけ。
        ``all_player_ids_provider`` が無ければ pending の人だけ。
        """
        ordered = list(scheduled)
        seen = {int(pid.value) for pid in ordered}
        if self._all_player_ids is not None:
            for pid in sorted(self._all_player_ids(), key=lambda p: int(p.value)):
                if int(pid.value) in seen:
                    continue
                if self._pending(pid):
                    ordered.append(pid)
                    seen.add(int(pid.value))
        return ordered

    def decide_wave(
        self,
        player_ids: Sequence[PlayerId],
        *,
        scheduled: Sequence[PlayerId] | None = None,
    ) -> list[PlayerId]:
        """この tick に回す人を返す。決定は全員ぶん trace に残す。

        ``scheduled`` は pending に入っていた人。省略すると全員が pending 扱い。
        """
        tick = int(self._current_tick())
        scheduled_ids = (
            {int(pid.value) for pid in scheduled}
            if scheduled is not None
            else {int(pid.value) for pid in player_ids}
        )
        decisions = [
            self._decide(pid, scheduled=int(pid.value) in scheduled_ids)
            for pid in player_ids
        ]
        for d in decisions:
            self._record(tick, d)
        return [d.player_id for d in decisions if d.wake]

    def _decide(self, player_id: PlayerId, *, scheduled: bool = True) -> TurnDecision:
        pending = list(self._pending(player_id))
        count = len(pending)
        categories: dict[str, int] = {}
        for o in pending:
            categories[o.observation_category] = categories.get(o.observation_category, 0) + 1
        if not pending:
            return TurnDecision(player_id, True, REASON_NO_PENDING, count, categories, scheduled=scheduled)
        name = self._player_name(player_id)
        state = self._state(name, pending)
        try:
            answer = self.judgment_port.judge(
                state, {QUESTION_NAME: self._question(name)}
            )[QUESTION_NAME]
        except TypedJudgmentUnavailableException as exc:
            return TurnDecision(
                player_id, True, REASON_JUDGMENT_UNAVAILABLE, count, categories, scheduled=scheduled,
                unavailable_reason=getattr(exc, "error_code", "UNAVAILABLE"),
            )
        except KeyError:
            return TurnDecision(
                player_id, True, REASON_JUDGMENT_UNAVAILABLE, count, categories, scheduled=scheduled,
                unavailable_reason="TYPED_JUDGMENT_ANSWER_MISSING",
            )
        probability = float(answer.value)
        wake = probability >= self.skip_below
        return TurnDecision(
            player_id, wake,
            REASON_JUDGED_NEEDED if wake else REASON_JUDGED_UNNEEDED,
            count, categories, scheduled=scheduled,
            observations=tuple(state["observations_this_tick"]),
            probability=probability,
            latency_ms=answer.latency_ms,
            source=answer.source.value,
        )

    def _state(self, name: str, pending: Sequence[ObservationOutput]) -> Mapping[str, Any]:
        # 名指し・囁きは観測の本文に含まれている。分類の見出しを付けて、
        # 自分の身に起きたことと世界の変化と他者の言動を Jev が区別できるようにする。
        recent = [
            {"kind": _CATEGORY_LABEL.get(o.observation_category, o.observation_category), "text": o.prose}
            for o in pending
            if o.prose
        ][-self._observation_limit :]
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
                "自分が動く必要がある。名指しで問われている、答えを求められている、"
                "自分の身や世界に見過ごせない変化がある、または自分の立場から言うべき"
                "ことがある"
            ),
            false_means=(
                "動かなくてよい。他人同士のやり取りや自分に関わらない報告だけで、"
                "様子を見ていればよい"
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
                categories=dict(d.categories),
                scheduled=d.scheduled,
                observations=[
                    {"kind": o["kind"], "text": str(o["text"])[:200]} for o in d.observations
                ],
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
    "DEFAULT_SKIP_BELOW",
    "QUESTION_NAME",
    "REASON_JUDGED_NEEDED",
    "REASON_JUDGED_UNNEEDED",
    "REASON_JUDGMENT_UNAVAILABLE",
    "REASON_NO_PENDING",
    "TurnDecision",
    "TurnGate",
]
