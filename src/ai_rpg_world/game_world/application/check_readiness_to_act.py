from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.game_world.domain.value_object.readiness_to_act import ReadinessToAct


@final
@dataclass(frozen=True)
class CheckReadinessToActCommand:
    people: Sequence[PersonId]


@final
class CheckReadinessToAct:
    def __init__(self, scope: CommandScope) -> None:
        self._scope = scope

    def __call__(self, command: CheckReadinessToActCommand) -> Mapping[PersonId, ReadinessToAct]:
        return self._scope.run(
            lambda session: {person: _readiness_of(person, session.facts()) for person in command.people}
        )


def _readiness_of(person: PersonId, facts: WorldFacts) -> ReadinessToAct:
    return facts.vitals(person).readiness_to_act(facts.now(), facts.outcomes().is_undecided(person))
