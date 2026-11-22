from __future__ import annotations

from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.game_world.infrastructure.scenario.scenario_loader import LoadedScenario
from ai_rpg_world.play_session.application.start_play_session import Role


def roles_from_scenario(scenario: LoadedScenario) -> tuple[Role, ...]:
    return tuple(
        Role(
            person=person,
            # Being は世界をまたいで残るので、同じ登場人物の名前を同じ Being に当てる
            being_id=BeingId(person.value),
            being_name=str(fields["name"]),
            persona_fields=fields,
            known_facts=scenario.briefings[person].known_facts,
            objective=scenario.briefings[person].objective,
        )
        for person, fields in scenario.beings.items()
    )
