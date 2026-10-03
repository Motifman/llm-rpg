from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.memory.expectation.exception.expectation_exception import (
    ExpectationValidationException,
)


@dataclass(frozen=True)
class ExpectationGrounds:
    """予期の根拠。頭にあった信念とエピソードのうち、その予期の材料になったもの。

    確定した当否はここにだけ返す。頭にあったものすべてに返すと、いつも頭に載る
    信念やエピソードに、関係の無い予期の当否が積まれ続ける (#1484)。
    """

    beliefs: tuple[str, ...] = ()
    episodes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("beliefs", "episodes"):
            value = getattr(self, name)
            if not isinstance(value, tuple) or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                raise ExpectationValidationException(
                    f"grounds.{name} must be tuple of non-empty str"
                )
            if len(set(value)) != len(value):
                raise ExpectationValidationException(
                    f"grounds.{name} must not have duplicates: {value}"
                )

    @property
    def is_empty(self) -> bool:
        return not self.beliefs and not self.episodes


__all__ = ["ExpectationGrounds"]
