from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    SpotGraphDomainException,
)
from ai_rpg_world.domain.common.exception import ValidationException


# 合成条件のタイプ。leaf 条件と区別するため module-level 定数として明示。
COMPOSITE_CONDITION_TYPES = frozenset({"NOT", "AND", "OR"})


class ScenarioEventConditionValidationException(SpotGraphDomainException, ValidationException):
    """ScenarioEventCondition のバリデーション例外。"""
    error_code = "WORLD_GRAPH.SCENARIO_EVENT_CONDITION_VALIDATION"


@dataclass(frozen=True)
class ScenarioEventCondition:
    """シナリオ自律イベントの発火条件。

    leaf 条件（TICK_AT_LEAST, FLAG_SET, PLAYER_AT_SPOT など）と、
    合成条件（NOT/AND/OR）を 1 つのデータ構造で表現する。

    合成条件は `children` を使う:
    - NOT: children は 1 個ちょうど。その否定。
    - AND: children 全てが真なら真。空なら真（vacuous truth）。
    - OR : children のどれか 1 つが真なら真。空なら偽。

    leaf 条件は従来通り condition_type と該当フィールドで指定する。
    """

    condition_type: str
    tick: Optional[int] = None
    tick_start: Optional[int] = None
    tick_end: Optional[int] = None
    flag_name: Optional[str] = None
    spot_id: Optional[int] = None
    object_id: Optional[int] = None
    required_state: Optional[dict[str, Any]] = None
    item_spec_id: Optional[int] = None
    # 脱出ゲーム拡張: 周期的イベント
    tick_modulo: Optional[int] = None
    tick_phase: Optional[int] = None
    # 合成条件用の子条件ツリー
    children: Tuple["ScenarioEventCondition", ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.condition_type == "NOT" and len(self.children) != 1:
            raise ScenarioEventConditionValidationException(
                f"NOT condition requires exactly 1 child, got {len(self.children)}"
            )
        if self.condition_type in {"AND", "OR"} and not isinstance(self.children, tuple):
            raise ScenarioEventConditionValidationException(
                f"{self.condition_type} condition.children must be a tuple"
            )
        if self.condition_type not in COMPOSITE_CONDITION_TYPES and self.children:
            raise ScenarioEventConditionValidationException(
                f"leaf condition '{self.condition_type}' must not have children"
            )

    @property
    def is_composite(self) -> bool:
        return self.condition_type in COMPOSITE_CONDITION_TYPES
