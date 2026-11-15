from __future__ import annotations

from typing import final

from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.perception.perceiver import Perceiver
from ai_rpg_world.game_world.domain.perception.perception_outcome import Perceived, PerceptionRecipient
from ai_rpg_world.game_world.domain.perception.perception_senses import PerceptionSenses
from ai_rpg_world.game_world.domain.perception.stimulus import Stimulus
from ai_rpg_world.game_world.domain.value_object import PersonId


@final
class PeopleReachedByStimuli:
    def __init__(self, recipient: PerceptionRecipient) -> None:
        self._recipient = recipient
        self._reached: set[PersonId] = set()

    def deliver(self, stimulus: Stimulus, perceiver: Perceiver, senses: PerceptionSenses) -> None:
        # 扉が開くのを見た人に、同じ扉の音を別の観測として重ねない (perception.md)
        if perceiver.person in self._reached and not stimulus.always_delivered:
            return
        stimulus.perceived_in(perceiver, senses).hand_over(perceiver.person, self)

    def perceived(self, perceived: Perceived) -> None:
        self._reached.add(perceived.perceiver)
        self._recipient.perceived(perceived)

    def noticed_later(self, perceiver: PersonId, notice: MissedNotice) -> None:
        self._reached.add(perceiver)
        self._recipient.noticed_later(perceiver, notice)
