from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.value_object._checks import require_int_at_least


@final
@dataclass(frozen=True)
class ConditionPath:
    _steps: tuple[int, ...]

    @classmethod
    def root(cls) -> ConditionPath:
        return cls(())

    def under(self, position: int) -> ConditionPath:
        require_int_at_least("ConditionPath position", position, 0)
        return ConditionPath((position, *self._steps))
