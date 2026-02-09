from typing import Optional, List
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import HarvestableComponent
from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import LootResult
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate


class HarvestDomainService:
    """採掘・採集に関するドメインロジックを提供するサービス"""

    def process_reward_with_item(
        self,
        harvestable: HarvestableComponent,
        loot_result: Optional[LootResult],
        item_spec: Optional[ItemSpec],
        new_item_id: Optional[ItemInstanceId],
        inventory: Optional[PlayerInventoryAggregate],
        status: Optional[PlayerStatusAggregate]
    ) -> tuple[List[DomainEvent], Optional[ItemAggregate]]:
        """
        採集の報酬付与とスタミナ消費を処理し、生成されたアイテムがあれば返す。
        """
        events = []
        item_aggregate = None

        # スタミナ消費
        if status:
            status.consume_stamina(harvestable.stamina_cost)
            events.extend(status.get_events())

        # 報酬アイテムの生成とインベントリへの追加
        if loot_result and item_spec and new_item_id and inventory:
            item_aggregate = ItemAggregate.create(
                item_instance_id=new_item_id,
                item_spec=item_spec,
                quantity=loot_result.quantity
            )
            inventory.acquire_item(new_item_id)
            
            # 生成されたアイテムのイベントとインベントリのイベント（取得成功 or オーバーフロー）を収集
            events.extend(item_aggregate.get_events())
            events.extend(inventory.get_events())
            
        return events, item_aggregate

    def can_start_harvest(
        self,
        status: PlayerStatusAggregate,
        harvestable: HarvestableComponent
    ) -> bool:
        """採集を開始できるかチェックする"""
        return status.stamina.value >= harvestable.stamina_cost
