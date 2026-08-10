"""道具に宣言された操作を item spec ごとに引く登録簿。"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Tuple

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef


@dataclass(frozen=True)
class ItemInteractionRegistry:
    """ItemSpecId と world_graph の InteractionDef を結ぶ不変な登録簿。

    JSON 上は道具の仕様に操作を並べるが、``InteractionDef`` を item
    ドメインへ依存させない。既存の依存方向 (world_graph → item) を保つため、
    loader がこの登録簿へ射影する。
    """

    _entries: Mapping[ItemSpecId, Tuple[InteractionDef, ...]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        normalized = {
            spec_id: tuple(interactions)
            for spec_id, interactions in self._entries.items()
            if interactions
        }
        object.__setattr__(self, "_entries", MappingProxyType(normalized))

    def interactions_for(self, item_spec_id: ItemSpecId) -> Tuple[InteractionDef, ...]:
        """品目に宣言された操作を宣言順で返す。無ければ空タプル。"""
        return self._entries.get(item_spec_id, ())
