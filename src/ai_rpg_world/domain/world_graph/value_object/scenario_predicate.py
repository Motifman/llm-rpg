"""用途を跨いで同じ意味を持つ、型付きのシナリオ述語。"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ScenarioPredicateValidationException,
)


@dataclass(frozen=True)
class FlagSetPredicate:
    """名前が完全一致する世界フラグが立っていることを要求する。"""

    flag_name: str

    def __post_init__(self) -> None:
        if not isinstance(self.flag_name, str) or not self.flag_name.strip():
            raise ScenarioPredicateValidationException(
                "FlagSetPredicate.flag_name must be a non-empty str"
            )


ScenarioPredicate = FlagSetPredicate


__all__ = ["FlagSetPredicate", "ScenarioPredicate"]
