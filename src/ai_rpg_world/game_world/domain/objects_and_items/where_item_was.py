from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId


@final
@dataclass(frozen=True)
class CarriedBy:
    person: PersonId


@final
@dataclass(frozen=True)
class LyingAt:
    spot: SpotId


WhereItemWas = CarriedBy | LyingAt
