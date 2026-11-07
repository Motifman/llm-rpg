from __future__ import annotations

import math

from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.exception.world_design_exception import BlankDeclaredNameException


def require_int_at_least(type_name: str, value: object, minimum: int) -> None:
    # bool は int の派生なので、True を 1 として受け取らないよう先に弾く。
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueOutOfRangeException(f"{type_name} must be int, got {value!r}")
    if value < minimum:
        raise ValueOutOfRangeException(f"{type_name} must be >= {minimum}, got {value}")


def require_finite_number(type_name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueOutOfRangeException(f"{type_name} must be a finite number, got {value!r}")
    return float(value)


def require_declared_name(type_name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise BlankDeclaredNameException(f"{type_name} must be a non-blank declared name, got {value!r}")
