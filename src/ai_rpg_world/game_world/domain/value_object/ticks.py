from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.game_world.domain.value_object._checks import require_int_at_least


@dataclass(frozen=True, order=True)
class Ticks:
    """tick で数えた長さ。0 は猶予なし (DeathRule.grace) を表す。"""

    value: int

    def __post_init__(self) -> None:
        require_int_at_least("Ticks", self.value, 0)
