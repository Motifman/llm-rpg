from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.exception.person_exception import BlankStatusEffectTypeException
from ai_rpg_world.game_world.domain.value_object import WorldTick


@final
@dataclass(frozen=True)
class StatusEffectType:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise BlankStatusEffectTypeException(f"StatusEffectType must be non-blank, got {self.value!r}")


@final
@dataclass(frozen=True)
class StatusEffect:
    kind: StatusEffectType
    expires_at: WorldTick

    def has_expired(self, now: WorldTick) -> bool:
        return now >= self.expires_at


@final
@dataclass(frozen=True)
class NoPreviousStatusEffect:
    pass
