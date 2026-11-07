from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.game_world.domain.exception.game_world_exception import TickOrderException
from ai_rpg_world.game_world.domain.value_object._checks import require_int_at_least
from ai_rpg_world.game_world.domain.value_object.ticks import Ticks


@dataclass(frozen=True, order=True)
class WorldTick:
    """世界の時刻。始まりを 0 として数える。"""

    value: int

    def __post_init__(self) -> None:
        require_int_at_least("WorldTick", self.value, 0)

    def __add__(self, ticks: Ticks) -> WorldTick:
        if not isinstance(ticks, Ticks):
            return NotImplemented
        return WorldTick(self.value + ticks.value)

    def ticks_since(self, earlier: WorldTick) -> Ticks:
        if earlier > self:
            raise TickOrderException(f"{earlier} is later than {self}")
        return Ticks(self.value - earlier.value)
