from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick


@final
@dataclass(frozen=True)
class StruckByPerson:
    person: PersonId


@final
@dataclass(frozen=True)
class Starvation:
    pass


@final
@dataclass(frozen=True)
class WorldHappening:
    pass


FallCause = StruckByPerson | Starvation | WorldHappening


@final
@dataclass(frozen=True)
class Alive:
    pass


@final
@dataclass(frozen=True)
class Down:
    fell_at: WorldTick
    cause: FallCause


@final
@dataclass(frozen=True)
class Dead:
    died_at: WorldTick


LifeState = Alive | Down | Dead
