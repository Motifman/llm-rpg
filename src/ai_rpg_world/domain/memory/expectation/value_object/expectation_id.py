from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.memory.expectation.exception.expectation_exception import (
    ExpectationValidationException,
)


@dataclass(frozen=True)
class ExpectationId:
    """予期を一意に識別する値オブジェクト。"""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ExpectationValidationException(
                "ExpectationId.value must be a non-empty str"
            )
        object.__setattr__(self, "value", self.value.strip())

    def __str__(self) -> str:
        return self.value


__all__ = ["ExpectationId"]
