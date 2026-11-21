from __future__ import annotations

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
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick

# 届く見込みの無かった人まで残すと、刺激ごとに世界の全員が並び、届かなかった理由を追いたい人が埋もれる (D2206)。
_NO_CHANCE_OF_REACHING: Final = frozenset(
    {NotPerceivedReason.ELSEWHERE, NotPerceivedReason.NOT_OWN_BODY, NotPerceivedReason.NOT_ADDRESSED}
)


@final
class PeopleReachedByStimuli:
    def __init__(self, recipient: PerceptionRecipient) -> None:
        self._recipient = recipient
        self._reached = _ReachedPeople(recipient)
        self._results: list[StimulusDeliveryResult] = []

    def deliver(self, stimulus: Stimulus, perceivers: tuple[Perceiver, ...], senses: PerceptionSenses) -> None:
        tally = _StimulusTally(self._reached if stimulus.counts_toward_one_per_person else self._recipient)
        for perceiver in perceivers:
            self._deliver_to(stimulus, perceiver, senses, tally)
        self._results.append(tally.result_of(stimulus))

    def report(self, cause: PerceptionCause, at: WorldTick) -> PerceptionDeliveryReport:
        return PerceptionDeliveryReport(cause=cause, at=at, stimuli=tuple(self._results))

    def _deliver_to(
        self, stimulus: Stimulus, perceiver: Perceiver, senses: PerceptionSenses, tally: _StimulusTally
    ) -> None:
        if (
            stimulus.counts_toward_one_per_person
            and self._reached.has_reached(perceiver.person)
            and not stimulus.always_delivered
        ):
            tally.not_perceived(perceiver.person, NotPerceivedReason.ALREADY_PERCEIVED)
            return
        stimulus.perceived_in(perceiver, senses).hand_over(perceiver.person, tally)


@final
class _ReachedPeople:
    def __init__(self, recipient: PerceptionRecipient) -> None:
        self._recipient = recipient
        self._people: set[PersonId] = set()

    def has_reached(self, person: PersonId) -> bool:
        return person in self._people

    def perceived(self, perceived: Perceived) -> None:
        self._people.add(perceived.perceiver)
        self._recipient.perceived(perceived)

    def noticed_later(self, perceiver: PersonId, notice: MissedNotice) -> None:
        self._people.add(perceiver)
        self._recipient.noticed_later(perceiver, notice)

    def not_perceived(self, perceiver: PersonId, reason: NotPerceivedReason) -> None:
        self._recipient.not_perceived(perceiver, reason)


@final
class _StimulusTally:
    def __init__(self, passing_to: PerceptionRecipient) -> None:
        self._passing_to = passing_to
        self._perceived_by: list[PersonId] = []
        self._kept_for: list[PersonId] = []
        self._missed_by: dict[PersonId, NotPerceivedReason] = {}

    def perceived(self, perceived: Perceived) -> None:
        self._perceived_by.append(perceived.perceiver)
        self._passing_to.perceived(perceived)

    def noticed_later(self, perceiver: PersonId, notice: MissedNotice) -> None:
        self._kept_for.append(perceiver)
        self._passing_to.noticed_later(perceiver, notice)

    def not_perceived(self, perceiver: PersonId, reason: NotPerceivedReason) -> None:
        if reason not in _NO_CHANCE_OF_REACHING:
            self._missed_by[perceiver] = reason
        self._passing_to.not_perceived(perceiver, reason)

    def result_of(self, stimulus: Stimulus) -> StimulusDeliveryResult:
        return StimulusDeliveryResult(
            stimulus=stimulus.described(),
            perceived_by=tuple(self._perceived_by),
            kept_for=tuple(self._kept_for),
            missed_by=self._missed_by,
        )
