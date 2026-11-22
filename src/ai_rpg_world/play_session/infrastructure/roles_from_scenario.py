from __future__ import annotations

from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import LoadedScenario
from ai_rpg_world.play_session.application.start_play_session import Role
from ai_rpg_world.play_session.domain.cast import Casting


def roles_from_scenario(scenario: LoadedScenario) -> tuple[Role, ...]:
    return tuple(
        Role(
            person=person,
            persona_fields=fields,
            known_facts=scenario.briefings[person].known_facts,
            objective=scenario.briefings[person].objective,
        )
        for person, fields in scenario.beings.items()
    )


def casting_by_person_name(scenario: LoadedScenario) -> Casting:
    return Casting({person: BeingId(person.value) for person in scenario.beings})
