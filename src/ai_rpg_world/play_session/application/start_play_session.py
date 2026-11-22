from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import final

from ai_rpg_world.being.application.enter_environment import EnterEnvironment, EnterEnvironmentCommand
from ai_rpg_world.being.application.prepare_being import PrepareBeing, PrepareBeingCommand
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.game_world.application.brief_entering_person import BriefEnteringPerson, BriefEnteringPersonCommand
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.domain.value_object import DescriptionText, PersonId
from ai_rpg_world.play_session.domain.cast import Cast, CastMember, CastRepository


@final
@dataclass(frozen=True)
class Role:
    person: PersonId
    being_id: BeingId
    being_name: str
    persona_fields: Mapping[str, object]
    known_facts: DescriptionText
    objective: DescriptionText


@final
@dataclass(frozen=True)
class StartPlaySessionCommand:
    open_world: OpenWorldCommand
    environment_name: str
    roles: tuple[Role, ...]


@final
class StartPlaySession:
    def __init__(
        self,
        *,
        open_world: OpenWorld,
        brief: BriefEnteringPerson,
        prepare_being: PrepareBeing,
        enter_environment: EnterEnvironment,
        casts: CastRepository,
    ) -> None:
        self._open_world = open_world
        self._brief = brief
        self._prepare_being = prepare_being
        self._enter_environment = enter_environment
        self._casts = casts

    def __call__(self, command: StartPlaySessionCommand) -> None:
        world = command.open_world.world_id
        cast = Cast(
            world,
            command.environment_name,
            (CastMember(role.person, role.being_id, role.being_name) for role in command.roles),
        )
        self._open_world(command.open_world)
        # 紹介は相手の Being の名前で渡すので、全員を配役してから一人ずつ入れる
        for role in command.roles:
            self._prepare_being.execute(PrepareBeingCommand(being_id=role.being_id, persona_fields=role.persona_fields))
            briefing = self._brief(
                BriefEnteringPersonCommand(person=role.person, known_facts=role.known_facts, objective=role.objective)
            )
            cast.brief(
                role.person,
                orientation=briefing.orientation,
                imposed_goal=briefing.imposed_goal,
                known_people=briefing.known_people,
            )
            self._enter_environment.execute(
                EnterEnvironmentCommand(
                    being_id=role.being_id, environment_id=world.value, entry=cast.entry_of(role.person)
                )
            )
        self._casts.save(cast)
