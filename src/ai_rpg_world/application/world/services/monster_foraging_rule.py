from ai_rpg_world.application.world.services.monster_feed_query_service import (
    MonsterFeedQueryService,
    MonsterForagingResult,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.world_object import WorldObject


class MonsterForagingRule:
    """餌の観測と選択を返す専任 rule。"""

    def __init__(
        self,
        feed_query_service: MonsterFeedQueryService,
    ) -> None:
        self._feed_query_service = feed_query_service

    def evaluate(
        self,
        actor: WorldObject,
        physical_map: PhysicalMapAggregate,
        monster: MonsterAggregate,
        current_tick: WorldTick,
    ) -> MonsterForagingResult:
        return self._feed_query_service.build_foraging_result(
            actor=actor,
            physical_map=physical_map,
            monster=monster,
            current_tick=current_tick,
        )
