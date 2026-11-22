from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import final

from ai_rpg_world.being.application.enter_environment import EnterEnvironment, EnterEnvironmentCommand
from ai_rpg_world.being.application.prepare_being import PrepareBeing, PrepareBeingCommand
from ai_rpg_world.game_world.application.brief_entering_person import BriefEnteringPerson, BriefEnteringPersonCommand
from ai_rpg_world.game_world.application.name_person import NamePerson, NamePersonCommand
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName, PersonId
from ai_rpg_world.play_session.domain.cast import Cast, Casting, CastRepository
from ai_rpg_world.play_session.domain.turn_rounds import RoundCount, TurnRounds, TurnRoundsRepository


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
    round_limit: RoundCount
    wake_waiting_after: RoundCount


@final
class StartPlaySession:
    def __init__(
        self,
        *,
        open_world: OpenWorld,
        name_person: NamePerson,
        brief: BriefEnteringPerson,
        prepare_being: PrepareBeing,
        enter_environment: EnterEnvironment,
        casts: CastRepository,
        turn_rounds: TurnRoundsRepository,
    ) -> None:
        self._open_world = open_world
        self._name_person = name_person
        self._brief = brief
        self._prepare_being = prepare_being
        self._enter_environment = enter_environment
        self._casts = casts
        self._turn_rounds = turn_rounds

    def __call__(self, command: StartPlaySessionCommand) -> None:
        world = command.open_world.world_id
        cast = Cast(
            world,
            command.environment_name,
            (command.casting.member(role.person, role.being_name) for role in command.roles),
        )
        # 世界を開いて Being を入れたあとで断られると、同じコマンドでやり直せない。断られうる手順を先に済ませる
        for role in command.roles:
            briefing = self._brief(BriefEnteringPersonCommand(person=role.person, objective=role.objective))
            cast.brief(
                role.person,
                orientation=briefing.orientation,
                imposed_goal=briefing.imposed_goal,
                known_people=briefing.known_people,
                known_facts=role.known_facts.text,
            )
        names = tuple(NamePersonCommand(role.person, DisplayName(role.being_name)) for role in command.roles)
        for role in command.roles:
            self._prepare_being.execute(
                PrepareBeingCommand(being_id=cast.being_of(role.person), persona_fields=role.persona_fields)
            )
        # 開いた世界から届く観測の呼びかけを受け取れるよう、巡りを先に置く
        self._turn_rounds.save(
            TurnRounds(world, round_limit=command.round_limit, wake_waiting_after=command.wake_waiting_after)
        )
        self._open_world(command.open_world)
        # 世界は Being の名前を知らないので、入る前に名乗る名前を名簿に付ける (D2229-3)
        for name in names:
            self._name_person(name)
        for role in command.roles:
            self._enter_environment.execute(
                EnterEnvironmentCommand(
                    being_id=cast.being_of(role.person), environment_id=world.value, entry=cast.entry_of(role.person)
                )
            )
        self._casts.save(cast)
