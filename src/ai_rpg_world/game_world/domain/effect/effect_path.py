from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.value_object._checks import require_int_at_least


@final
@dataclass(frozen=True)
class EffectPath:
    _steps: tuple[int, ...]

    @classmethod
    def root(cls) -> EffectPath:
        return cls(())

    def child(self, position: int) -> EffectPath:
        require_int_at_least("EffectPath position", position, 0)
        return EffectPath((*self._steps, position))
