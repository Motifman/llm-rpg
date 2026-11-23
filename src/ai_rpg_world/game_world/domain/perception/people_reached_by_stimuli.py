from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, final

from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.perception.not_perceived_reason import NotPerceivedReason
from ai_rpg_world.game_world.domain.perception.perceiver import Perceiver
from ai_rpg_world.game_world.domain.perception.perception_cause import PerceptionCause
from ai_rpg_world.game_world.domain.perception.perception_delivery_report import (
    PerceptionDeliveryReport,
    StimulusDeliveryResult,
)
from ai_rpg_world.game_world.domain.perception.perception_outcome import Perceived, PerceptionRecipient
from ai_rpg_world.game_world.domain.perception.perception_senses import PerceptionSenses
from ai_rpg_world.game_world.domain.perception.stimulus import Stimulus
from ai_rpg_world.game_world.domain.perception.what_perceived_conveys import WhatPerceivedConveys
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick

# 届く見込みの無かった人まで残すと、刺激ごとに世界の全員が並び、届かなかった理由を追いたい人が埋もれる (D2206)。
_NO_CHANCE_OF_REACHING: Final = frozenset(
    {NotPerceivedReason.ELSEWHERE, NotPerceivedReason.NOT_OWN_BODY, NotPerceivedReason.NOT_ADDRESSED}
)


@final
class PeopleReachedByStimuli:
    def __init__(self, recipient: PerceptionRecipient) -> None:
        self._recipient = recipient
        self._results: list[StimulusDeliveryResult] = []

    def deliver_all(
        self, stimuli: Sequence[Stimulus], perceivers: tuple[Perceiver, ...], senses: PerceptionSenses
    ) -> None:
        handing = _HandingOver(self._recipient)
        tallies = []
        for stimulus in stimuli:
            tally = _StimulusTally(stimulus)
            for perceiver in perceivers:
                handing.offer(stimulus, perceiver, senses, tally)
            tallies.append(tally)
        handing.finish()
        self._results += (tally.result() for tally in tallies)

    def report(self, cause: PerceptionCause, at: WorldTick) -> PerceptionDeliveryReport:
        return PerceptionDeliveryReport(cause=cause, at=at, stimuli=tuple(self._results))


@final
@dataclass
class _Chosen:
    conveys: WhatPerceivedConveys
    replaceable_at: int | None
    tally: _StimulusTally


@final
class _HandingOver:
    # 差し替えを同じ位置に入れるのは、受け取る人の観測の順が、差し替えの有無で変わらないようにするため

    def __init__(self, recipient: PerceptionRecipient) -> None:
        self._recipient = recipient
        self._handed: list[Perceived | tuple[PersonId, MissedNotice]] = []
        self._chosen: dict[PersonId, _Chosen] = {}

    def offer(self, stimulus: Stimulus, perceiver: Perceiver, senses: PerceptionSenses, tally: _StimulusTally) -> None:
        person = perceiver.person
        chosen = self._chosen.get(person) if stimulus.counts_toward_one_per_person else None
        # 伝えうる量で先に絞る。試すと、見える刺激はこっそりの見落としの抽選で乱数を引く
        if chosen is not None and not stimulus.always_delivered and stimulus.most_it_can_convey() <= chosen.conveys:
            self._not_perceived(person, NotPerceivedReason.ALREADY_PERCEIVED, tally)
            return
        stimulus.perceived_in(perceiver, senses).hand_over(person, _Offered(self, stimulus, chosen, tally))

    def perceived(
        self, perceived: Perceived, stimulus: Stimulus, chosen: _Chosen | None, tally: _StimulusTally
    ) -> None:
        person = perceived.perceiver
        if not stimulus.counts_toward_one_per_person:
            self._append(perceived)
        elif stimulus.always_delivered:
            self._append(perceived)
            if chosen is None:
                self._chosen[person] = _Chosen(perceived.conveys, None, tally)
            else:
                chosen.conveys = max(chosen.conveys, perceived.conveys)
        elif chosen is None:
            self._chosen[person] = _Chosen(perceived.conveys, self._append(perceived), tally)
        elif perceived.conveys > chosen.conveys:
            self._replace(perceived, chosen, tally)
        else:
            self._not_perceived(person, NotPerceivedReason.ALREADY_PERCEIVED, tally)
            return
        tally.perceived(person)

    def noticed_later(
        self,
        perceiver: PersonId,
        notice: MissedNotice,
        stimulus: Stimulus,
        chosen: _Chosen | None,
        tally: _StimulusTally,
    ) -> None:
        if stimulus.counts_toward_one_per_person and chosen is not None and not stimulus.always_delivered:
            self._not_perceived(perceiver, NotPerceivedReason.ALREADY_PERCEIVED, tally)
            return
        self._handed.append((perceiver, notice))
        if stimulus.counts_toward_one_per_person and chosen is None:
            self._chosen[perceiver] = _Chosen(WhatPerceivedConveys.WHAT_HAPPENED, None, tally)
        tally.kept(perceiver)

    def not_perceived(
        self,
        perceiver: PersonId,
        reason: NotPerceivedReason,
        stimulus: Stimulus,
        chosen: _Chosen | None,
        tally: _StimulusTally,
    ) -> None:
        if chosen is not None and not stimulus.always_delivered:
            reason = NotPerceivedReason.ALREADY_PERCEIVED
        self._not_perceived(perceiver, reason, tally)

    def finish(self) -> None:
        for handed in self._handed:
            if isinstance(handed, Perceived):
                self._recipient.perceived(handed)
            else:
                self._recipient.noticed_later(*handed)
        self._handed.clear()

    def _append(self, perceived: Perceived) -> int:
        self._handed.append(perceived)
        return len(self._handed) - 1

    def _replace(self, perceived: Perceived, chosen: _Chosen, tally: _StimulusTally) -> None:
        person = perceived.perceiver
        # 重ねて届けたもの (倒れたこと) と起きてから知るものは、その人に別のことを伝えているので残す
        if chosen.replaceable_at is None:
            slot = self._append(perceived)
        else:
            slot = chosen.replaceable_at
            self._handed[slot] = perceived
            chosen.tally.superseded(person)
            self._recipient.not_perceived(person, NotPerceivedReason.ALREADY_PERCEIVED)
        self._chosen[person] = _Chosen(perceived.conveys, slot, tally)

    def _not_perceived(self, perceiver: PersonId, reason: NotPerceivedReason, tally: _StimulusTally) -> None:
        tally.missed(perceiver, reason)
        self._recipient.not_perceived(perceiver, reason)


@final
class _Offered:
    def __init__(
        self, handing: _HandingOver, stimulus: Stimulus, chosen: _Chosen | None, tally: _StimulusTally
    ) -> None:
        self._handing = handing
        self._stimulus = stimulus
        self._chosen = chosen
        self._tally = tally

    def perceived(self, perceived: Perceived) -> None:
        self._handing.perceived(perceived, self._stimulus, self._chosen, self._tally)

    def noticed_later(self, perceiver: PersonId, notice: MissedNotice) -> None:
        self._handing.noticed_later(perceiver, notice, self._stimulus, self._chosen, self._tally)

    def not_perceived(self, perceiver: PersonId, reason: NotPerceivedReason) -> None:
        self._handing.not_perceived(perceiver, reason, self._stimulus, self._chosen, self._tally)


@final
class _StimulusTally:
    def __init__(self, stimulus: Stimulus) -> None:
        self._stimulus = stimulus
        self._perceived_by: list[PersonId] = []
        self._kept_for: list[PersonId] = []
        self._missed_by: dict[PersonId, NotPerceivedReason] = {}

    def perceived(self, person: PersonId) -> None:
        self._perceived_by.append(person)

    def kept(self, person: PersonId) -> None:
        self._kept_for.append(person)

    def missed(self, person: PersonId, reason: NotPerceivedReason) -> None:
        if reason not in _NO_CHANCE_OF_REACHING:
            self._missed_by[person] = reason

    def superseded(self, person: PersonId) -> None:
        self._perceived_by.remove(person)
        self._missed_by[person] = NotPerceivedReason.ALREADY_PERCEIVED

    def result(self) -> StimulusDeliveryResult:
        return StimulusDeliveryResult(
            stimulus=self._stimulus.described(),
            perceived_by=tuple(self._perceived_by),
            kept_for=tuple(self._kept_for),
            missed_by=self._missed_by,
        )
