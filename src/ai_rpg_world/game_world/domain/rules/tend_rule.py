from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.game_world.domain.value_object import Rate


@dataclass(frozen=True)
class TendRule:
    revive_hp_rate: Rate


@dataclass(frozen=True)
class NoTending:
    pass
