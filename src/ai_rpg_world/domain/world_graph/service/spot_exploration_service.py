from __future__ import annotations

from typing import FrozenSet, List, Tuple

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.enum.discovery_condition_type import DiscoveryConditionTypeEnum
from ai_rpg_world.domain.world_graph.value_object.discoverable_item import DiscoverableItem
from ai_rpg_world.domain.world_graph.value_object.discovery_condition import DiscoveryCondition
from ai_rpg_world.domain.world_graph.value_object.exploration_result import ExplorationResult


class SpotExplorationService:
    """スポット内探索（リポジトリ非依存）"""

    def explore(
        self,
        interior: SpotInterior,
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        cumulative_search_count: int,
        world_flags: FrozenSet[str],
    ) -> ExplorationResult:
        """探索を1回実行し、新たに発見されたアイテムを反映した SpotInterior を返す。"""
        new_list: List[DiscoverableItem] = []
        descriptions: List[str] = []
        discovered_specs: List[ItemSpecId] = []

        for d in interior.discoverable_items:
            if d.is_discovered:
                new_list.append(d)
                continue
            if self._meets_condition(
                d.discovery_condition,
                cumulative_search_count,
                owned_item_spec_ids,
                world_flags,
            ):
                marked = d.mark_discovered()
                new_list.append(marked)
                desc = marked.description.strip() if marked.description else f"アイテムを発見した（spec={marked.item_spec_id}）"
                descriptions.append(desc)
                discovered_specs.append(marked.item_spec_id)
            else:
                new_list.append(d)

        new_interior = interior.replace_discoverable_items(tuple(new_list))
        return ExplorationResult(
            new_interior=new_interior,
            discovery_descriptions=tuple(descriptions),
            item_spec_ids_newly_discovered=tuple(discovered_specs),
        )

    def _meets_condition(
        self,
        dc: DiscoveryCondition,
        cumulative_search_count: int,
        owned_item_spec_ids: FrozenSet[ItemSpecId],
        world_flags: FrozenSet[str],
    ) -> bool:
        t = dc.condition_type
        if t == DiscoveryConditionTypeEnum.ALWAYS:
            return True
        if t == DiscoveryConditionTypeEnum.SEARCH_COUNT:
            return cumulative_search_count >= dc.required_search_count
        if t == DiscoveryConditionTypeEnum.HAS_ITEM:
            return (
                dc.required_item_spec_id is not None
                and dc.required_item_spec_id in owned_item_spec_ids
            )
        if t == DiscoveryConditionTypeEnum.FLAG_SET:
            return dc.flag_name is not None and dc.flag_name in world_flags
        return False
