"""本人のターン数の検証。予期は世界の tick ではなく、本人の歩みで時刻を持つ。"""

from __future__ import annotations

from ai_rpg_world.domain.memory.expectation.exception.expectation_exception import (
    ExpectationValidationException,
)


def require_turn(value: object, *, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ExpectationValidationException(f"{name} must be int")
    if value < 0:
        raise ExpectationValidationException(f"{name} must be >= 0 (got {value})")
    return value


__all__ = ["require_turn"]
