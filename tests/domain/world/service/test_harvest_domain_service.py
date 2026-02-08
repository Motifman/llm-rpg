import pytest
from unittest.mock import MagicMock
from ai_rpg_world.domain.world.service.harvest_domain_service import HarvestDomainService
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import HarvestableComponent, ActorComponent
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import LootResult
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.common.value_object import WorldTick

class TestHarvestDomainService:
    @pytest.fixture
    def service(self):
        return HarvestDomainService()

    @pytest.fixture
    def actor(self):
        return WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.NPC,
            component=ActorComponent()
        )

    @pytest.fixture
    def harvestable_comp(self):
        return HarvestableComponent(
            loot_table_id="iron_ore",
            stamina_cost=15
        )

    @pytest.fixture
    def item_spec(self):
        return ItemSpec(
            item_spec_id=ItemSpecId(101),
            name="Iron Ore",
            item_type=ItemType.MATERIAL,
            rarity=Rarity.COMMON,
            description="A piece of iron ore.",
            max_stack_size=MaxStackSize(99)
        )

    def test_process_reward_with_player_success(self, service, actor, harvestable_comp, item_spec):
        """プレイヤーが採集に成功した場合の報酬処理テスト"""
        # 準備
        loot_result = LootResult(item_spec_id=item_spec.item_spec_id, quantity=2)
        new_item_id = ItemInstanceId(500)
        
        inventory = MagicMock(spec=PlayerInventoryAggregate)
        inventory.get_events.return_value = []
        status = MagicMock(spec=PlayerStatusAggregate)
        status.get_events.return_value = []
        
        # 実行
        events, item_aggregate = service.process_reward_with_item(
            harvestable=harvestable_comp,
            loot_result=loot_result,
            item_spec=item_spec,
            new_item_id=new_item_id,
            inventory=inventory,
            status=status
        )
        
        # 検証
        status.consume_stamina.assert_called_once_with(15)
        inventory.acquire_item.assert_called_once_with(new_item_id)
        assert item_aggregate is not None
        assert item_aggregate.item_instance_id == new_item_id
        assert item_aggregate.quantity == 2

    def test_process_reward_with_npc_success(self, service, actor, harvestable_comp, item_spec):
        """NPC（ステータスやインベントリがないアクター）が採集した場合のテスト"""
        # 準備
        loot_result = LootResult(item_spec_id=item_spec.item_spec_id, quantity=1)
        new_item_id = ItemInstanceId(501)
        
        # inventory, status を None にする
        events, item_aggregate = service.process_reward_with_item(
            harvestable=harvestable_comp,
            loot_result=loot_result,
            item_spec=item_spec,
            new_item_id=new_item_id,
            inventory=None,
            status=None
        )
        
        # 検証: エラーにならず、アイテムも生成されない（付与先がないため）
        assert item_aggregate is None
        assert len(events) == 0

    def test_process_reward_no_loot(self, service, actor, harvestable_comp, item_spec):
        """抽選で何も出なかった場合のテスト"""
        # 準備
        inventory = MagicMock(spec=PlayerInventoryAggregate)
        status = MagicMock(spec=PlayerStatusAggregate)
        status.get_events.return_value = []
        
        # 実行
        events, item_aggregate = service.process_reward_with_item(
            harvestable=harvestable_comp,
            loot_result=None, # ハズレ
            item_spec=None,
            new_item_id=None,
            inventory=inventory,
            status=status
        )
        
        # 検証: スタミナだけ消費される
        status.consume_stamina.assert_called_once_with(15)
        inventory.acquire_item.assert_not_called()
        assert item_aggregate is None
