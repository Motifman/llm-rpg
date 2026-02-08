import pytest
from ai_rpg_world.domain.world.entity.world_object_component import HarvestableComponent
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.exception.harvest_exception import (
    HarvestQuantityValidationException,
    HarvestIntervalValidationException,
    ResourceExhaustedException
)
from ai_rpg_world.domain.common.exception import ValidationException


class TestHarvestableComponent:
    """HarvestableComponentの包括的なテストスイート"""

    def test_constructor_success(self):
        """正常なコンストラクタテスト"""
        comp = HarvestableComponent(
            loot_table_id="iron_ore",
            max_quantity=5,
            respawn_interval=100,
            initial_quantity=3,
            last_harvest_tick=WorldTick(50),
            required_tool_category="pickaxe"
        )
        assert comp.loot_table_id == "iron_ore"
        assert comp.required_tool_category == "pickaxe"
        assert comp.get_available_quantity(WorldTick(50)) == 3

    def test_validation_invalid_params(self):
        """不正なパラメータに対するバリデーションテスト"""
        # 空のloot_table_id
        with pytest.raises(ValidationException, match="Loot table ID cannot be empty"):
            HarvestableComponent("", max_quantity=1)
        
        # max_quantityが0以下
        with pytest.raises(HarvestQuantityValidationException, match="Max quantity must be positive"):
            HarvestableComponent("id", max_quantity=0)
            
        # respawn_intervalが負
        with pytest.raises(HarvestIntervalValidationException, match="cannot be negative"):
            HarvestableComponent("id", max_quantity=1, respawn_interval=-1)
            
        # initial_quantityが負
        with pytest.raises(HarvestQuantityValidationException, match="cannot be negative"):
            HarvestableComponent("id", max_quantity=1, initial_quantity=-1)
            
        # initial_quantity > max_quantity
        with pytest.raises(HarvestQuantityValidationException, match="cannot exceed max quantity"):
            HarvestableComponent("id", max_quantity=5, initial_quantity=6)

    def test_lazy_recovery_scenarios(self):
        """様々な状況下でのLazy Recoveryテスト"""
        # 100ティックごとに1回復、最大5、初期2、最終更新100ティック目
        comp = HarvestableComponent(
            loot_table_id="iron_ore",
            max_quantity=5,
            respawn_interval=100,
            initial_quantity=2,
            last_harvest_tick=WorldTick(100)
        )
        
        # 同一ティック：変化なし
        assert comp.get_available_quantity(WorldTick(100)) == 2
        
        # 99ティック経過：変化なし
        assert comp.get_available_quantity(WorldTick(199)) == 2
        
        # 100ティック経過：1回復
        assert comp.get_available_quantity(WorldTick(200)) == 3
        
        # 250ティック経過：2回復
        assert comp.get_available_quantity(WorldTick(350)) == 4
        
        # 1000ティック経過：最大値でクリップ
        assert comp.get_available_quantity(WorldTick(1100)) == 5
        
        # 過去のティック：現在の量を維持（あるいはエラー）
        assert comp.get_available_quantity(WorldTick(50)) == 2

    def test_harvest_flow(self):
        """採取フローのテスト"""
        comp = HarvestableComponent(
            loot_table_id="herbs",
            max_quantity=1,
            respawn_interval=100,
            initial_quantity=1,
            last_harvest_tick=WorldTick(0)
        )
        
        # 1回目：成功
        from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
        actor_id = WorldObjectId(1)
        comp.start_harvest(actor_id, WorldTick(10))
        comp.finish_harvest(actor_id, WorldTick(20))
        assert comp.get_available_quantity(WorldTick(20)) == 0
        
        # 2回目：枯渇による例外
        with pytest.raises(ResourceExhaustedException):
            comp.start_harvest(actor_id, WorldTick(30))
            
        # 120ティック目：回復して成功（最終更新20 + インターバル100 = 120）
        assert comp.get_available_quantity(WorldTick(120)) == 1
        comp.start_harvest(actor_id, WorldTick(120))
        comp.finish_harvest(actor_id, WorldTick(130))
        assert comp.get_available_quantity(WorldTick(130)) == 0

    def test_harvest_trial_flow_success(self):
        """試行・時間経過・完了のフローテスト"""
        from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
        actor_id = WorldObjectId(1)
        comp = HarvestableComponent(
            loot_table_id="iron",
            harvest_duration=10
        )
        
        current_tick = WorldTick(100)
        # 1. 開始
        finish_tick = comp.start_harvest(actor_id, current_tick)
        assert finish_tick == WorldTick(110)
        assert comp.current_actor_id == actor_id
        
        # 2. 進行中（完了判定）
        assert not comp.is_harvest_complete(WorldTick(109))
        assert comp.is_harvest_complete(WorldTick(110))
        
        # 3. 完了
        success = comp.finish_harvest(actor_id, WorldTick(110))
        assert success is True
        assert comp.get_available_quantity(WorldTick(110)) == 0
        assert comp.current_actor_id is None

    def test_harvest_trial_interruption(self):
        """採取の中断テスト"""
        from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
        actor_id = WorldObjectId(1)
        comp = HarvestableComponent(loot_table_id="iron", harvest_duration=10)
        
        comp.start_harvest(actor_id, WorldTick(100))
        assert comp.current_actor_id == actor_id
        
        # 中断
        comp.cancel_harvest(actor_id)
        assert comp.current_actor_id is None
        
        # 中断後にfinishを呼んでもエラー
        from ai_rpg_world.domain.world.entity.world_object_component import HarvestNotStartedException
        with pytest.raises(HarvestNotStartedException):
            comp.finish_harvest(actor_id, WorldTick(110))

    def test_harvest_trial_concurrency(self):
        """採取の同時実行制限テスト"""
        from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
        from ai_rpg_world.domain.world.entity.world_object_component import HarvestInProgressException
        
        actor1 = WorldObjectId(1)
        actor2 = WorldObjectId(2)
        comp = HarvestableComponent(loot_table_id="iron")
        
        comp.start_harvest(actor1, WorldTick(100))
        
        # 他のアクターは開始できない
        with pytest.raises(HarvestInProgressException):
            comp.start_harvest(actor2, WorldTick(100))

    def test_to_dict_and_properties(self):
        """シリアライズとプロパティのテスト"""
        comp = HarvestableComponent(
            loot_table_id="gold",
            max_quantity=10,
            respawn_interval=500,
            initial_quantity=5,
            last_harvest_tick=WorldTick(1000),
            required_tool_category="special_pickaxe"
        )
        
        assert comp.get_type_name() == "harvestable"
        assert comp.interaction_type == "harvest"
        assert comp.interaction_data == {
            "loot_table_id": "gold",
            "required_tool_category": "special_pickaxe"
        }
        
        data = comp.to_dict()
        assert data["loot_table_id"] == "gold"
        assert data["max_quantity"] == 10
        assert data["current_quantity"] == 5
        assert data["respawn_interval"] == 500
        assert data["last_update_tick"] == 1000
        assert data["required_tool_category"] == "special_pickaxe"
