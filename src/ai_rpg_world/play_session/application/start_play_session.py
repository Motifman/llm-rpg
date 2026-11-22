from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import final

from ai_rpg_world.being.application.enter_environment import EnterEnvironment, EnterEnvironmentCommand
from ai_rpg_world.being.application.prepare_being import PrepareBeing, PrepareBeingCommand
from ai_rpg_world.game_world.application.brief_entering_person import BriefEnteringPerson, BriefEnteringPersonCommand
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.domain.value_object import DescriptionText, PersonId
from ai_rpg_world.play_session.domain.cast import Cast, Casting, CastRepository


@final
@dataclass(frozen=True)
class Role:
    person: PersonId
    persona_fields: Mapping[str, object]
    known_facts: DescriptionText
    objective: DescriptionText

    @property
    def being_name(self) -> str:
        return str(self.persona_fields.get("name", ""))


@final
@dataclass(frozen=True)
class StartPlaySessionCommand:
    open_world: OpenWorldCommand
    environment_name: str
    roles: tuple[Role, ...]
    casting: Casting


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
            (command.casting.member(role.person, role.being_name) for role in command.roles),
        )
        # 世界を開いて Being を入れたあとで断られると、同じコマンドでやり直せない。断られうる手順を先に済ませる
        for role in command.roles:
            briefing = self._brief(
                BriefEnteringPersonCommand(person=role.person, known_facts=role.known_facts, objective=role.objective)
            )
            cast.brief(
                role.person,
                orientation=briefing.orientation,
                imposed_goal=briefing.imposed_goal,
                known_people=briefing.known_people,
            )
        for role in command.roles:
            self._prepare_being.execute(
                PrepareBeingCommand(being_id=cast.being_of(role.person), persona_fields=role.persona_fields)
            )
        self._open_world(command.open_world)
        for role in command.roles:
            self._enter_environment.execute(
                EnterEnvironmentCommand(
                    being_id=cast.being_of(role.person), environment_id=world.value, entry=cast.entry_of(role.person)
                )
            )
        self._casts.save(cast)
