from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.observation_exit import ObservationExit
from ai_rpg_world.game_world.application.world_perception_senses import WorldPerceptionSenses, perceivers_in_world
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates
from ai_rpg_world.game_world.domain.perception import Perceived, Stimulus
from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.perception.people_reached_by_stimuli import PeopleReachedByStimuli
from ai_rpg_world.game_world.domain.value_object import PersonId


@final
@dataclass(frozen=True)
class DeliverPerceptionCommand:
    from_actions: tuple[Stimulus, ...]
    from_states: tuple[Stimulus, ...]

    def in_delivery_order(self) -> tuple[Stimulus, ...]:
        return (*_ranked(self.from_actions), *_ranked(self.from_states))


def _ranked(stimuli: tuple[Stimulus, ...]) -> list[Stimulus]:
    return sorted(stimuli, key=lambda stimulus: stimulus.delivery_rank())


@final
class DeliverPerception:
    def __init__(self, scope: CommandScope, exit: ObservationExit) -> None:
        self._scope = scope
        self._exit = exit

    def __call__(self, command: DeliverPerceptionCommand) -> None:
        perceived = self._scope.run(lambda session: _perceive(session, command))
        for one in perceived:
            self._exit.hand_over(one)


def _perceive(session: WorldSession, command: DeliverPerceptionCommand) -> tuple[Perceived, ...]:
    facts = session.facts()
    senses = WorldPerceptionSenses(facts)
    perceivers = perceivers_in_world(facts)
    handed_over = _PerceptionsHandedOver(session.aggregates())
    reached = PeopleReachedByStimuli(handed_over)
    for stimulus in command.in_delivery_order():
        for perceiver in perceivers:
            reached.deliver(stimulus, perceiver, senses)
    return handed_over.perceived_so_far()


@final
class _PerceptionsHandedOver:
    def __init__(self, aggregates: WorldAggregates) -> None:
        self._aggregates = aggregates
        self._perceived: list[Perceived] = []

    def perceived(self, perceived: Perceived) -> None:
        self._perceived.append(perceived)

    def noticed_later(self, perceiver: PersonId, notice: MissedNotice) -> None:
        self._aggregates.missed_notices(perceiver).keep(notice)

    def perceived_so_far(self) -> tuple[Perceived, ...]:
        return tuple(self._perceived)
