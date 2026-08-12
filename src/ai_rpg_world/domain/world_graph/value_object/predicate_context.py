"""共通シナリオ述語へ渡す、用途から独立した評価文脈。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Optional

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    PredicateContextValidationException,
)


@dataclass(frozen=True)
class WorldFlagPredicateContext:
    """世界フラグ判定に必要な集合。Noneは未配線、空集合は正当な世界状態。"""

    world_flags: Optional[FrozenSet[str]]

    def __post_init__(self) -> None:
        if self.world_flags is not None and (
            not isinstance(self.world_flags, frozenset)
            or any(
                not isinstance(flag_name, str) or not flag_name
                for flag_name in self.world_flags
            )
        ):
            raise PredicateContextValidationException(
                "world_flags must be a frozenset of non-empty str or None"
            )


__all__ = ["WorldFlagPredicateContext"]
