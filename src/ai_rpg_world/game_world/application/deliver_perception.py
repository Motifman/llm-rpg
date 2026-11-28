from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, final

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.observation_exit import ObservationExit
from ai_rpg_world.game_world.application.world_perception_senses import WorldPerceptionSenses, perceivers_in_world
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates
from ai_rpg_world.game_world.domain.perception import Perceived, Stimulus
from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.perception.not_perceived_reason import NotPerceivedReason
from ai_rpg_world.game_world.domain.perception.people_reached_by_stimuli import PeopleReachedByStimuli
from ai_rpg_world.game_world.domain.perception.perception_cause import PerceptionCause
from ai_rpg_world.game_world.domain.perception.perception_delivery_report import PerceptionDeliveryReport
from ai_rpg_world.game_world.domain.value_object import PersonId


class PerceptionReportReceiver(Protocol):
    def receive(self, report: PerceptionDeliveryReport) -> None: ...


@final
@dataclass(frozen=True)
class DeliverPerceptionCommand:
    cause: PerceptionCause
    from_actions: tuple[Stimulus, ...]
    from_states: tuple[Stimulus, ...]

    def in_delivery_order(self) -> tuple[Stimulus, ...]:
        return (*_ranked(self.from_actions), *_ranked(self.from_states))

    def carries_stimuli(self) -> bool:
        return bool(self.from_actions or self.from_states)


def _ranked(stimuli: tuple[Stimulus, ...]) -> list[Stimulus]:
    return sorted(stimuli, key=lambda stimulus: stimulus.delivery_rank())


@final
class DeliverPerception:
    def __init__(self, scope: CommandScope, exit: ObservationExit, reports: PerceptionReportReceiver) -> None:
        self._scope = scope
        self._exit = exit
        self._reports = reports

    def __call__(self, command: DeliverPerceptionCommand) -> None:
        perceived, report = self._scope.run(lambda session: _perceive(session, command))
        for one in perceived:
            self._exit.hand_over(one)
        self._reports.receive(report)


def _perceive(
    session: WorldSession, command: DeliverPerceptionCommand
) -> tuple[tuple[Perceived, ...], PerceptionDeliveryReport]:
    facts = session.facts()
    senses = WorldPerceptionSenses(facts)
    perceivers = perceivers_in_world(facts)
    handed_over = _PerceptionsHandedOver(session.aggregates())
    reached = PeopleReachedByStimuli(handed_over)
    reached.deliver_all(command.in_delivery_order(), perceivers, senses)
    return handed_over.perceived_so_far(), reached.report(command.cause, facts.now())


@final
class _PerceptionsHandedOver:
    def __init__(self, aggregates: WorldAggregates) -> None:
        self._aggregates = aggregates
        self._perceived: list[Perceived] = []

    def perceived(self, perceived: Perceived) -> None:
        self._perceived.append(perceived)

    def noticed_later(self, perceiver: PersonId, notice: MissedNotice) -> None:
        self._aggregates.missed_notices(perceiver).keep(notice)

    def not_perceived(self, perceiver: PersonId, reason: NotPerceivedReason) -> None:
        pass

    def perceived_so_far(self) -> tuple[Perceived, ...]:
        return tuple(self._perceived)
