from dataclasses import dataclass
from typing import List, Optional

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.repository.loot_table_repository import LootTableRepository
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    AutonomousBehaviorComponent,
    HarvestableComponent,
)
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException
from ai_rpg_world.domain.world.service.feed_eligibility_service import is_feed_for_monster


@dataclass(frozen=True)
class MonsterForagingResult:
    visible_feed: List[WorldObject]
    selected_feed_target: Optional[WorldObject]


class MonsterFeedQueryService:
    """餌探索と spot 内 feed 判定をまとめる query service。"""

    def __init__(
        self,
        loot_table_repository: Optional[LootTableRepository],
    ) -> None:
        self._loot_table_repository = loot_table_repository

    def build_foraging_result(
        self,
        actor: WorldObject,
        physical_map: PhysicalMapAggregate,
        monster: MonsterAggregate,
        current_tick: WorldTick,
    ) -> MonsterForagingResult:
        visible_feed: List[WorldObject] = []
        selected_feed_target: Optional[WorldObject] = None

        if (
            self._loot_table_repository is None
            or not monster.template.preferred_feed_item_spec_ids
            or not isinstance(actor.component, AutonomousBehaviorComponent)
        ):
            return MonsterForagingResult(
                visible_feed=visible_feed,
                selected_feed_target=selected_feed_target,
            )

        preferred = monster.template.preferred_feed_item_spec_ids
        nearby = physical_map.get_objects_in_range(
            actor.coordinate,
            actor.component.vision_range,
        )
        for obj in nearby:
            if obj.object_id == actor.object_id:
                continue
            if not isinstance(obj.component, HarvestableComponent):
                continue
            harvestable = obj.component
            if harvestable.get_available_quantity(current_tick) <= 0:
                continue
            loot_table = self._loot_table_repository.find_by_id(
                harvestable.loot_table_id
            )
            if not loot_table or not is_feed_for_monster(loot_table.entries, preferred):
                continue
            if not physical_map.is_visible(actor.coordinate, obj.coordinate):
                continue
            visible_feed.append(obj)

        if visible_feed and monster.hunger >= monster.template.forage_threshold:
            selected_feed_target = min(
                visible_feed,
                key=lambda obj: actor.coordinate.distance_to(obj.coordinate),
            )
            monster.remember_feed(
                selected_feed_target.object_id,
                selected_feed_target.coordinate,
            )

        if (
            selected_feed_target is None
            and monster.hunger >= monster.template.forage_threshold
        ):
            memories = sorted(
                monster.behavior_last_known_feed,
                key=lambda entry: actor.coordinate.distance_to(entry.coordinate),
            )
            for entry in memories:
                try:
                    obj = physical_map.get_object(entry.object_id)
                except ObjectNotFoundException:
                    continue
                if not isinstance(obj.component, HarvestableComponent):
                    continue
                harvestable = obj.component
                if harvestable.get_available_quantity(current_tick) <= 0:
                    continue
                loot_table = self._loot_table_repository.find_by_id(
                    harvestable.loot_table_id
                )
                if not loot_table or not is_feed_for_monster(loot_table.entries, preferred):
                    continue
                selected_feed_target = obj
                break

        return MonsterForagingResult(
            visible_feed=visible_feed,
            selected_feed_target=selected_feed_target,
        )

    def spot_has_feed_for_monster(
        self,
        physical_map: PhysicalMapAggregate,
        monster: MonsterAggregate,
        current_tick: WorldTick,
    ) -> bool:
        if self._loot_table_repository is None:
            return False

        preferred = monster.template.preferred_feed_item_spec_ids
        if not preferred:
            return False

        for obj in physical_map.get_all_objects():
            if not isinstance(obj.component, HarvestableComponent):
                continue
            harvestable = obj.component
            if harvestable.get_available_quantity(current_tick) <= 0:
                continue
            loot_table = self._loot_table_repository.find_by_id(harvestable.loot_table_id)
            if not loot_table or not is_feed_for_monster(loot_table.entries, preferred):
                continue
            return True
        return False
