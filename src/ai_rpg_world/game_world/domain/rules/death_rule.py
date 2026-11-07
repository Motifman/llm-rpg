from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.game_world.domain.value_object import Ticks


@dataclass(frozen=True)
class DeathRule:
    grace: Ticks
