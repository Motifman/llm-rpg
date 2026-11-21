from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.perception.not_perceived_reason import NotPerceivedReason
from ai_rpg_world.game_world.domain.perception.perceiver import Perceiver
from ai_rpg_world.game_world.domain.perception.perception_outcome import Perceived, PerceptionRecipient
from ai_rpg_world.game_world.domain.perception.perception_senses import PerceptionSenses
from ai_rpg_world.game_world.domain.perception.stimulus import Stimulus
from ai_rpg_world.game_world.domain.value_object import PersonId


@final
class PeopleReachedByStimuli:
    def __init__(self, recipient: PerceptionRecipient) -> None:
        self._recipient = recipient
        self._reached = _ReachedPeople(recipient)

    def deliver(self, stimulus: Stimulus, perceiver: Perceiver, senses: PerceptionSenses) -> None:
        if not stimulus.counts_toward_one_per_person:
            stimulus.perceived_in(perceiver, senses).hand_over(perceiver.person, self._recipient)
            return
        if self._reached.has_reached(perceiver.person) and not stimulus.always_delivered:
            return
        stimulus.perceived_in(perceiver, senses).hand_over(perceiver.person, self._reached)


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
