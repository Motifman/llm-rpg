from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise

from ai_rpg_world.game_world.domain.exception.rules_exception import (
    LevelBeyondLimitException,
    LevelNameBlankException,
    LevelNameDuplicatedException,
    LevelsNotAscendingException,
    LevelsNotStartingAtZeroException,
    NoLevelsDeclaredException,
    RuleLimitBelowOneException,
)


def require_level_name(type_name: str, value: str) -> None:
    if not value.strip():
        raise LevelNameBlankException(f"{type_name} must not be blank, got {value!r}")


def require_level_ladder(rule_name: str, boundaries: Sequence[int], names: Sequence[str], limit: int) -> None:
    if limit < 1:
        raise RuleLimitBelowOneException(f"{rule_name}.limit must be >= 1, got {limit}")
    if not boundaries:
        raise NoLevelsDeclaredException(f"{rule_name} must declare at least one level")
    if boundaries[0] != 0:
        raise LevelsNotStartingAtZeroException(f"{rule_name} first level must start at 0, got {boundaries[0]}")
    for lower, upper in pairwise(boundaries):
        if lower >= upper:
            raise LevelsNotAscendingException(f"{rule_name} level boundaries must strictly ascend, got {boundaries}")
    if boundaries[-1] > limit:
        raise LevelBeyondLimitException(
            f"{rule_name} level boundary {boundaries[-1]} is beyond the limit {limit} and can never be reached"
        )
    if len(set(names)) != len(names):
        raise LevelNameDuplicatedException(f"{rule_name} level names must be distinct, got {list(names)}")
