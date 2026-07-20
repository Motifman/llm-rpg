"""スポットの地理座標を表す値オブジェクト。"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    SpotPositionValidationException,
)


@dataclass(frozen=True)
class SpotPosition:
    """spot グラフの地理上の 2 次元座標。"""

    x: float
    y: float

    def __post_init__(self) -> None:
        if not _is_valid_number(self.x):
            raise SpotPositionValidationException(
                f"SpotPosition.x must be finite number: {self.x!r}"
            )
        if not _is_valid_number(self.y):
            raise SpotPositionValidationException(
                f"SpotPosition.y must be finite number: {self.y!r}"
            )


def _is_valid_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)
