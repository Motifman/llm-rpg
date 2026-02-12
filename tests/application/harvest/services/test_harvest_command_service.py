import pytest
from unittest.mock import MagicMock
from ai_rpg_world.application.harvest.services.harvest_command_service import HarvestCommandService
from ai_rpg_world.application.harvest.contracts.commands import StartHarvestCommand, FinishHarvestCommand
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import HarvestableComponent, ActorComponent
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import LootTableAggregate, LootEntry, LootResult
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.service.harvest_domain_service import HarvestDomainService
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import InMemoryPhysicalMapRepository
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import InMemoryItemRepository
from ai_rpg_world.infrastructure.repository.in_memory_loot_table_repository import InMemoryLootTableRepository
from ai_rpg_world.infrastructure.repository.in_memory_item_spec_repository import InMemoryItemSpecRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import InMemoryPlayerInventoryRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import InMemoryPlayerStatusRepository
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork

class TestHarvestCommandService:
    @pytest.fixture
    def setup_service(self):
        data_store = InMemoryDataStore()
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow)
        
        unit_of_work, event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow
        )
        
        physical_map_repo = InMemoryPhysicalMapRepository(data_store, unit_of_work)
        loot_table_repo = InMemoryLootTableRepository()
        item_spec_repo = InMemoryItemSpecRepository()
        inventory_repo = InMemoryPlayerInventoryRepository(data_store, unit_of_work)
        status_repo = InMemoryPlayerStatusRepository(data_store, unit_of_work)
        
        # Item repository
        item_repo = InMemoryItemRepository(data_store, unit_of_work)
        
        harvest_domain_service = HarvestDomainService()
        
        service = HarvestCommandService(
            physical_map_repo,
            loot_table_repo,
            item_repo,
            item_spec_repo,
            inventory_repo,
            status_repo,
            harvest_domain_service,
            unit_of_work
        )
        
        return {
            "service": service,
            "physical_map_repo": physical_map_repo,
            "loot_table_repo": loot_table_repo,
            "item_spec_repo": item_spec_repo,
            "inventory_repo": inventory_repo,
            "status_repo": status_repo,
            "item_repo": item_repo,
            "uow": unit_of_work,
            "event_publisher": event_publisher
        }

    def test_harvest_flow_success(self, setup_service):
        """採集開始から完了までの正常系フローテスト"""
        s = setup_service
        service = s["service"]
        
        # 1. データのセットアップ
        spot_id = SpotId.create(1)
        actor_id = WorldObjectId(1)
        target_id = WorldObjectId(2)
        
        # 物理マップの作成
        from ai_rpg_world.domain.world.entity.tile import Tile
        from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
        from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
        tiles = [
            Tile(Coordinate(0, 0, 0), TerrainType.grass()),
            Tile(Coordinate(1, 0, 0), TerrainType.grass())
        ]
        
        harvestable = HarvestableComponent(loot_table_id="iron_loot", harvest_duration=5, stamina_cost=10)
        target_obj = WorldObject(target_id, Coordinate(1, 0, 0), ObjectTypeEnum.RESOURCE, component=harvestable)
        actor_comp = ActorComponent(direction=DirectionEnum.EAST) # ターゲットの方を向かせる
        actor_obj = WorldObject(actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.NPC, component=actor_comp)
        
        physical_map = PhysicalMapAggregate.create(spot_id, tiles, objects=[actor_obj, target_obj])
        s["physical_map_repo"].save(physical_map)
        
        # ドロップテーブルの作成
        loot_table = LootTableAggregate.create("iron_loot", [LootEntry(ItemSpecId(9), weight=100)]) # 鉄鉱石(ID:9)確定
        s["loot_table_repo"].save(loot_table)
        
        # プレイヤー状態の作成
        player_id = PlayerId(1)
        status = PlayerStatusAggregate(
            player_id=player_id,
            base_stats=MagicMock(),
            stat_growth_factor=MagicMock(),
            exp_table=MagicMock(),
            growth=MagicMock(),
            gold=MagicMock(),
            hp=MagicMock(),
            mp=MagicMock(),
            stamina=Stamina.create(100, 100)
        )
        s["status_repo"].save(status)
        
        inventory = PlayerInventoryAggregate.create_new_inventory(player_id)
        s["inventory_repo"].save(inventory)
        
        # 2. 採集開始
        # ItemSpecReadModel を保存しておく必要がある (鉄鉱石 ID:9)
        from ai_rpg_world.domain.item.read_model.item_spec_read_model import ItemSpecReadModel
        s["item_spec_repo"].save(ItemSpecReadModel(
            item_spec_id=ItemSpecId(9),
            name="鉄鉱石",
            item_type=ItemType.MATERIAL,
            rarity=Rarity.COMMON,
            description="鉄の素材",
            max_stack_size=MaxStackSize(64)
        ))

        start_cmd = StartHarvestCommand(actor_id="1", target_id="2", spot_id="1", current_tick=100)
        start_result = service.start_harvest(start_cmd)
        
        assert start_result.success is True
        assert start_result.data["finish_tick"] == 105
        
        # 物理マップの状態確認
        updated_map = s["physical_map_repo"].find_by_spot_id(spot_id)
        assert updated_map.get_object(actor_id).is_busy(WorldTick(100))
        
        # 3. 採集完了
        finish_cmd = FinishHarvestCommand(actor_id="1", target_id="2", spot_id="1", current_tick=105)
        finish_result = service.finish_harvest(finish_cmd)
        
        assert finish_result.success is True
        assert len(finish_result.data["acquired_items"]) == 1
        assert finish_result.data["acquired_items"][0]["item_name"] == "鉄鉱石"
        
        # 4. 状態の最終確認
        # スタミナが消費されているか
        updated_status = s["status_repo"].find_by_id(player_id)
        assert updated_status.stamina.value == 90
        
        # インベントリにアイテムが追加されているか
        updated_inv = s["inventory_repo"].find_by_id(player_id)
        assert updated_inv.get_item_instance_id_by_slot(SlotId(0)) == ItemInstanceId(1)
        
        # リソースが減少しているか
        updated_map = s["physical_map_repo"].find_by_spot_id(spot_id)
        assert updated_map.get_object(target_id).component.get_available_quantity(WorldTick(105)) == 0

    def test_start_harvest_insufficient_stamina(self, setup_service):
        """スタミナ不足で採集を開始できないテスト"""
        s = setup_service
        service = s["service"]
        
        # 1. データのセットアップ
        spot_id = SpotId.create(1)
        actor_id = WorldObjectId(1)
        target_id = WorldObjectId(2)
        
        from ai_rpg_world.domain.world.entity.tile import Tile
        from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
        from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
        tiles = [Tile(Coordinate(0, 0, 0), TerrainType.grass()), Tile(Coordinate(1, 0, 0), TerrainType.grass())]
        
        harvestable = HarvestableComponent(loot_table_id="iron_loot", stamina_cost=10)
        target_obj = WorldObject(target_id, Coordinate(1, 0, 0), ObjectTypeEnum.RESOURCE, component=harvestable)
        actor_obj = WorldObject(actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.NPC, component=ActorComponent(direction=DirectionEnum.EAST))
        
        physical_map = PhysicalMapAggregate.create(spot_id, tiles, objects=[actor_obj, target_obj])
        s["physical_map_repo"].save(physical_map)
        
        # スタミナが足りないプレイヤー
        player_id = PlayerId(1)
        status = PlayerStatusAggregate(
            player_id=player_id,
            base_stats=MagicMock(), stat_growth_factor=MagicMock(), exp_table=MagicMock(),
            growth=MagicMock(), gold=MagicMock(), hp=MagicMock(), mp=MagicMock(),
            stamina=Stamina.create(5, 100) # コスト10に対して5しかない
        )
        s["status_repo"].save(status)
        s["inventory_repo"].save(PlayerInventoryAggregate.create_new_inventory(player_id))
        
        from ai_rpg_world.application.harvest.exceptions.command.harvest_command_exception import HarvestCommandException
        with pytest.raises(HarvestCommandException, match="スタミナが不足しています"):
            service.start_harvest(StartHarvestCommand(actor_id="1", target_id="2", spot_id="1", current_tick=100))

    def test_start_harvest_inventory_full(self, setup_service):
        """インベントリが満杯で採集を開始できないテスト"""
        s = setup_service
        service = s["service"]
        
        # データのセットアップ
        spot_id = SpotId.create(1)
        actor_id = WorldObjectId(1)
        target_id = WorldObjectId(2)
        
        from ai_rpg_world.domain.world.entity.tile import Tile
        from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
        tiles = [Tile(Coordinate(0, 0, 0), TerrainType.grass()), Tile(Coordinate(1, 0, 0), TerrainType.grass())]
        
        harvestable = HarvestableComponent(loot_table_id="iron_loot", stamina_cost=10)
        target_obj = WorldObject(target_id, Coordinate(1, 0, 0), ObjectTypeEnum.RESOURCE, component=harvestable)
        from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
        actor_obj = WorldObject(actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.NPC, component=ActorComponent(direction=DirectionEnum.EAST))
        physical_map = PhysicalMapAggregate.create(spot_id, tiles, objects=[actor_obj, target_obj])
        s["physical_map_repo"].save(physical_map)
        
        # インベントリが満杯のプレイヤー (max_slots=1 で1つ埋める)
        player_id = PlayerId(1)
        inventory = PlayerInventoryAggregate.create_new_inventory(player_id, max_slots=1)
        inventory.acquire_item(ItemInstanceId(101))
        s["inventory_repo"].save(inventory)
        s["status_repo"].save(PlayerStatusAggregate(player_id=player_id, stamina=Stamina.create(100, 100), base_stats=MagicMock(), stat_growth_factor=MagicMock(), exp_table=MagicMock(), growth=MagicMock(), gold=MagicMock(), hp=MagicMock(), mp=MagicMock()))
        
        from ai_rpg_world.application.harvest.exceptions.command.harvest_command_exception import HarvestCommandException
        with pytest.raises(HarvestCommandException, match="インベントリが満杯です"):
            service.start_harvest(StartHarvestCommand(actor_id="1", target_id="2", spot_id="1", current_tick=100))

    def test_start_harvest_invalid_spot(self, setup_service):
        """存在しないスポットを指定した場合のテスト"""
        s = setup_service
        service = s["service"]
        
        from ai_rpg_world.application.harvest.exceptions.command.harvest_command_exception import HarvestCommandException
        with pytest.raises(HarvestCommandException, match="Spot not found"):
            service.start_harvest(StartHarvestCommand(actor_id="1", target_id="2", spot_id="999", current_tick=100))

    def test_start_harvest_invalid_target(self, setup_service):
        """スポット内に存在しないターゲットを指定した場合のテスト"""
        s = setup_service
        service = s["service"]
        
        spot_id = SpotId.create(1)
        from ai_rpg_world.domain.world.entity.tile import Tile
        from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
        tiles = [Tile(Coordinate(0, 0, 0), TerrainType.grass())]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles, objects=[])
        s["physical_map_repo"].save(physical_map)
        
        from ai_rpg_world.application.harvest.exceptions.command.harvest_command_exception import HarvestCommandException
        # _execute_with_error_handling によって DomainException が HarvestCommandException に変換される
        with pytest.raises(HarvestCommandException, match="not found in spot"):
            service.start_harvest(StartHarvestCommand(actor_id="1", target_id="99", spot_id="1", current_tick=100))

    def test_start_harvest_target_not_harvestable(self, setup_service):
        """採取不可能なオブジェクトを指定した場合のテスト"""
        s = setup_service
        service = s["service"]
        
        spot_id = SpotId.create(1)
        from ai_rpg_world.domain.world.entity.tile import Tile
        from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
        tiles = [Tile(Coordinate(0, 0, 0), TerrainType.grass())]
        # ターゲットをサインボード（採取不可）にする
        target_obj = WorldObject(WorldObjectId(2), Coordinate(0, 0, 0), ObjectTypeEnum.SIGN)
        physical_map = PhysicalMapAggregate.create(spot_id, tiles, objects=[target_obj])
        s["physical_map_repo"].save(physical_map)
        
        from ai_rpg_world.application.harvest.exceptions.command.harvest_command_exception import HarvestResourceNotFoundException
        with pytest.raises(HarvestResourceNotFoundException):
            service.start_harvest(StartHarvestCommand(actor_id="1", target_id="2", spot_id="1", current_tick=100))

    def test_finish_harvest_too_early(self, setup_service):
        """時間が経過する前に完了しようとして失敗するテスト"""
        s = setup_service
        service = s["service"]
        
        # セットアップ
        from ai_rpg_world.domain.world.entity.tile import Tile
        from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
        from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
        tiles = [
            Tile(Coordinate(0, 0, 0), TerrainType.grass()),
            Tile(Coordinate(1, 0, 0), TerrainType.grass())
        ]
        
        spot_id = SpotId.create(1)
        actor_id = WorldObjectId(1)
        target_id = WorldObjectId(2)
        harvestable = HarvestableComponent(loot_table_id="iron_loot", harvest_duration=5)
        target_obj = WorldObject(target_id, Coordinate(1, 0, 0), ObjectTypeEnum.RESOURCE, component=harvestable)
        actor_comp = ActorComponent(direction=DirectionEnum.EAST)
        actor_obj = WorldObject(actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.NPC, component=actor_comp)
        physical_map = PhysicalMapAggregate.create(spot_id, tiles, objects=[actor_obj, target_obj])
        s["physical_map_repo"].save(physical_map)
        s["status_repo"].save(PlayerStatusAggregate(player_id=PlayerId(1), stamina=Stamina.create(100, 100), base_stats=MagicMock(), stat_growth_factor=MagicMock(), exp_table=MagicMock(), growth=MagicMock(), gold=MagicMock(), hp=MagicMock(), mp=MagicMock()))
        s["inventory_repo"].save(PlayerInventoryAggregate.create_new_inventory(PlayerId(1)))
        
        # 開始
        service.start_harvest(StartHarvestCommand(actor_id="1", target_id="2", spot_id="1", current_tick=100))
        
        # 早すぎる完了リクエスト (104ティック目)
        from ai_rpg_world.application.harvest.exceptions.command.harvest_command_exception import HarvestCommandException
        with pytest.raises(HarvestCommandException, match="採集はまだ完了していません"):
            service.finish_harvest(FinishHarvestCommand(actor_id="1", target_id="2", spot_id="1", current_tick=104))

    def test_finish_harvest_missing_loot_table(self, setup_service):
        """完了時にドロップテーブルが見つからない場合のテスト"""
        s = setup_service
        service = s["service"]
        
        # セットアップ (ドロップテーブルを保存しない)
        from ai_rpg_world.domain.world.entity.tile import Tile
        from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
        spot_id = SpotId.create(1)
        actor_id = WorldObjectId(1)
        target_id = WorldObjectId(2)
        harvestable = HarvestableComponent(loot_table_id="missing_loot", harvest_duration=5)
        target_obj = WorldObject(target_id, Coordinate(1, 0, 0), ObjectTypeEnum.RESOURCE, component=harvestable)
        from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
        actor_obj = WorldObject(actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.NPC, component=ActorComponent(direction=DirectionEnum.EAST))
        tiles = [Tile(Coordinate(0, 0, 0), TerrainType.grass()), Tile(Coordinate(1, 0, 0), TerrainType.grass())]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles, objects=[actor_obj, target_obj])
        s["physical_map_repo"].save(physical_map)
        s["status_repo"].save(PlayerStatusAggregate(player_id=PlayerId(1), stamina=Stamina.create(100, 100), base_stats=MagicMock(), stat_growth_factor=MagicMock(), exp_table=MagicMock(), growth=MagicMock(), gold=MagicMock(), hp=MagicMock(), mp=MagicMock()))
        s["inventory_repo"].save(PlayerInventoryAggregate.create_new_inventory(PlayerId(1)))
        
        # 開始 (開始しないと完了チェックで「採集はまだ完了していません」になる)
        service.start_harvest(StartHarvestCommand(actor_id="1", target_id="2", spot_id="1", current_tick=100))

        # 完了試行
        from ai_rpg_world.application.harvest.exceptions.command.harvest_command_exception import HarvestCommandException
        with pytest.raises(HarvestCommandException, match="Loot table missing_loot not found"):
            service.finish_harvest(FinishHarvestCommand(actor_id="1", target_id="2", spot_id="1", current_tick=105))

    def test_finish_harvest_missing_item_spec(self, setup_service):
        """完了時にアイテム仕様が見つからない場合のテスト"""
        s = setup_service
        service = s["service"]
        
        # セットアップ
        from ai_rpg_world.domain.world.entity.tile import Tile
        from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
        spot_id = SpotId.create(1)
        actor_id = WorldObjectId(1)
        target_id = WorldObjectId(2)
        harvestable = HarvestableComponent(loot_table_id="iron_loot", harvest_duration=5)
        target_obj = WorldObject(target_id, Coordinate(1, 0, 0), ObjectTypeEnum.RESOURCE, component=harvestable)
        from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
        actor_obj = WorldObject(actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.NPC, component=ActorComponent(direction=DirectionEnum.EAST))
        tiles = [Tile(Coordinate(0, 0, 0), TerrainType.grass()), Tile(Coordinate(1, 0, 0), TerrainType.grass())]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles, objects=[actor_obj, target_obj])
        s["physical_map_repo"].save(physical_map)
        s["status_repo"].save(PlayerStatusAggregate(player_id=PlayerId(1), stamina=Stamina.create(100, 100), base_stats=MagicMock(), stat_growth_factor=MagicMock(), exp_table=MagicMock(), growth=MagicMock(), gold=MagicMock(), hp=MagicMock(), mp=MagicMock()))
        s["inventory_repo"].save(PlayerInventoryAggregate.create_new_inventory(PlayerId(1)))
        
        # 開始
        service.start_harvest(StartHarvestCommand(actor_id="1", target_id="2", spot_id="1", current_tick=100))

        # ドロップテーブルはあるが、その中のアイテムIDに対応する仕様がない
        loot_table = LootTableAggregate.create("iron_loot", [LootEntry(ItemSpecId(999), weight=100)])
        s["loot_table_repo"].save(loot_table)
        # item_spec_repo には ID 999 を登録しない
        
        from ai_rpg_world.application.harvest.exceptions.command.harvest_command_exception import HarvestCommandException
        with pytest.raises(HarvestCommandException, match="Item spec 999 not found"):
            service.finish_harvest(FinishHarvestCommand(actor_id="1", target_id="2", spot_id="1", current_tick=105))

    def test_finish_harvest_inventory_full_at_finish(self, setup_service):
        """完了時にインベントリが満杯になっている場合のテスト（オーバーフローイベントが発行されることを確認）"""
        s = setup_service
        service = s["service"]
        
        # 正常なセットアップ
        from ai_rpg_world.domain.world.entity.tile import Tile
        from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
        from ai_rpg_world.domain.item.read_model.item_spec_read_model import ItemSpecReadModel
        spot_id = SpotId.create(1)
        actor_id = WorldObjectId(1)
        target_id = WorldObjectId(2)
        harvestable = HarvestableComponent(loot_table_id="iron_loot", harvest_duration=5)
        target_obj = WorldObject(target_id, Coordinate(1, 0, 0), ObjectTypeEnum.RESOURCE, component=harvestable)
        from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
        actor_obj = WorldObject(actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.NPC, component=ActorComponent(direction=DirectionEnum.EAST))
        tiles = [Tile(Coordinate(0, 0, 0), TerrainType.grass()), Tile(Coordinate(1, 0, 0), TerrainType.grass())]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles, objects=[actor_obj, target_obj])
        s["physical_map_repo"].save(physical_map)
        player_id = PlayerId(1)
        s["status_repo"].save(PlayerStatusAggregate(player_id=player_id, stamina=Stamina.create(100, 100), base_stats=MagicMock(), stat_growth_factor=MagicMock(), exp_table=MagicMock(), growth=MagicMock(), gold=MagicMock(), hp=MagicMock(), mp=MagicMock()))
        s["inventory_repo"].save(PlayerInventoryAggregate.create_new_inventory(player_id))
        
        # 開始
        service.start_harvest(StartHarvestCommand(actor_id="1", target_id="2", spot_id="1", current_tick=100))

        loot_table = LootTableAggregate.create("iron_loot", [LootEntry(ItemSpecId(9), weight=100)])
        s["loot_table_repo"].save(loot_table)
        
        # ItemSpecReadModel を保存する
        s["item_spec_repo"].save(ItemSpecReadModel(
            item_spec_id=ItemSpecId(9), 
            name="鉄鉱石", 
            item_type=ItemType.MATERIAL, 
            rarity=Rarity.COMMON, 
            description="鉄の鉱石", 
            max_stack_size=MaxStackSize(99)
        ))
        
        # 開始時は空きがあったが、完了までに埋まった状況を再現
        player_id = PlayerId(1)
        inventory = PlayerInventoryAggregate.create_new_inventory(player_id, max_slots=1)
        inventory.acquire_item(ItemInstanceId(101)) # 1つしかないスロットを埋める
        s["inventory_repo"].save(inventory)
        
        # 完了実行
        result = service.finish_harvest(FinishHarvestCommand(actor_id="1", target_id="2", spot_id="1", current_tick=105))
        
        assert result.success is True
        # サービス内部ではエラーにならず、イベントが発行されているはず
        # Event Publisher にイベントが追加されているか確認
        events = s["event_publisher"].get_published_events()
        from ai_rpg_world.domain.player.event.inventory_events import InventorySlotOverflowEvent
        assert any(isinstance(e, InventorySlotOverflowEvent) for e in events)
        
        # 永続化されているか確認
        updated_inv = s["inventory_repo"].find_by_id(player_id)
        assert updated_inv.is_inventory_full()
        # 取得を試みたアイテムは入っていない
        assert updated_inv.get_item_instance_id_by_slot(SlotId(0)) == ItemInstanceId(101)

    def test_start_harvest_distance_too_far(self, setup_service):
        """ターゲットが遠すぎて採取を開始できないテスト"""
        s = setup_service
        service = s["service"]
        
        spot_id = SpotId.create(1)
        actor_id = WorldObjectId(1)
        target_id = WorldObjectId(2)
        
        from ai_rpg_world.domain.world.entity.tile import Tile
        from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
        from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
        # 距離2の場所に配置
        tiles = [Tile(Coordinate(0, 0, 0), TerrainType.grass()), Tile(Coordinate(1, 0, 0), TerrainType.grass()), Tile(Coordinate(2, 0, 0), TerrainType.grass())]
        
        harvestable = HarvestableComponent(loot_table_id="iron_loot")
        target_obj = WorldObject(target_id, Coordinate(2, 0, 0), ObjectTypeEnum.RESOURCE, component=harvestable)
        actor_obj = WorldObject(actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.NPC, component=ActorComponent(direction=DirectionEnum.EAST))
        
        physical_map = PhysicalMapAggregate.create(spot_id, tiles, objects=[actor_obj, target_obj])
        s["physical_map_repo"].save(physical_map)
        s["status_repo"].save(PlayerStatusAggregate(player_id=PlayerId(1), stamina=Stamina.create(100, 100), base_stats=MagicMock(), stat_growth_factor=MagicMock(), exp_table=MagicMock(), growth=MagicMock(), gold=MagicMock(), hp=MagicMock(), mp=MagicMock()))
        s["inventory_repo"].save(PlayerInventoryAggregate.create_new_inventory(PlayerId(1)))
        
        from ai_rpg_world.application.harvest.exceptions.command.harvest_command_exception import HarvestCommandException
        with pytest.raises(HarvestCommandException, match="too far"):
            service.start_harvest(StartHarvestCommand(actor_id="1", target_id="2", spot_id="1", current_tick=100))

    def test_start_harvest_not_facing_target(self, setup_service):
        """ターゲットの方を向いていなくて採取を開始できないテスト"""
        s = setup_service
        service = s["service"]
        
        spot_id = SpotId.create(1)
        actor_id = WorldObjectId(1)
        target_id = WorldObjectId(2)
        
        from ai_rpg_world.domain.world.entity.tile import Tile
        from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
        from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
        tiles = [Tile(Coordinate(0, 0, 0), TerrainType.grass()), Tile(Coordinate(1, 0, 0), TerrainType.grass())]
        
        harvestable = HarvestableComponent(loot_table_id="iron_loot")
        target_obj = WorldObject(target_id, Coordinate(1, 0, 0), ObjectTypeEnum.RESOURCE, component=harvestable)
        # ターゲットはEASTだが、アクターはWESTを向いている
        actor_obj = WorldObject(actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.NPC, component=ActorComponent(direction=DirectionEnum.WEST))
        
        physical_map = PhysicalMapAggregate.create(spot_id, tiles, objects=[actor_obj, target_obj])
        s["physical_map_repo"].save(physical_map)
        s["status_repo"].save(PlayerStatusAggregate(player_id=PlayerId(1), stamina=Stamina.create(100, 100), base_stats=MagicMock(), stat_growth_factor=MagicMock(), exp_table=MagicMock(), growth=MagicMock(), gold=MagicMock(), hp=MagicMock(), mp=MagicMock()))
        s["inventory_repo"].save(PlayerInventoryAggregate.create_new_inventory(PlayerId(1)))
        
        from ai_rpg_world.application.harvest.exceptions.command.harvest_command_exception import HarvestCommandException
        with pytest.raises(HarvestCommandException, match="not facing"):
            service.start_harvest(StartHarvestCommand(actor_id="1", target_id="2", spot_id="1", current_tick=100))

    def test_start_harvest_already_in_progress(self, setup_service):
        """既に他の誰かが採取中のターゲットに対して採取を開始できないテスト"""
        s = setup_service
        service = s["service"]
        
        spot_id = SpotId.create(1)
        actor1_id = WorldObjectId(1)
        actor2_id = WorldObjectId(3)
        target_id = WorldObjectId(2)
        
        from ai_rpg_world.domain.world.entity.tile import Tile
        from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
        from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
        tiles = [Tile(Coordinate(0, 0, 0), TerrainType.grass()), Tile(Coordinate(1, 0, 0), TerrainType.grass()), Tile(Coordinate(1, 1, 0), TerrainType.grass())]
        
        harvestable = HarvestableComponent(loot_table_id="iron_loot")
        target_obj = WorldObject(target_id, Coordinate(1, 0, 0), ObjectTypeEnum.RESOURCE, component=harvestable)
        actor1_obj = WorldObject(actor1_id, Coordinate(0, 0, 0), ObjectTypeEnum.NPC, component=ActorComponent(direction=DirectionEnum.EAST))
        actor2_obj = WorldObject(actor2_id, Coordinate(1, 1, 0), ObjectTypeEnum.NPC, component=ActorComponent(direction=DirectionEnum.NORTH)) 
        
        physical_map = PhysicalMapAggregate.create(spot_id, tiles, objects=[actor1_obj, target_obj, actor2_obj])
        s["physical_map_repo"].save(physical_map)
        
        # プレイヤー1と2のデータ
        s["status_repo"].save(PlayerStatusAggregate(player_id=PlayerId(1), stamina=Stamina.create(100, 100), base_stats=MagicMock(), stat_growth_factor=MagicMock(), exp_table=MagicMock(), growth=MagicMock(), gold=MagicMock(), hp=MagicMock(), mp=MagicMock()))
        s["inventory_repo"].save(PlayerInventoryAggregate.create_new_inventory(PlayerId(1)))
        s["status_repo"].save(PlayerStatusAggregate(player_id=PlayerId(3), stamina=Stamina.create(100, 100), base_stats=MagicMock(), stat_growth_factor=MagicMock(), exp_table=MagicMock(), growth=MagicMock(), gold=MagicMock(), hp=MagicMock(), mp=MagicMock()))
        s["inventory_repo"].save(PlayerInventoryAggregate.create_new_inventory(PlayerId(3)))
        
        # プレイヤー1が開始
        service.start_harvest(StartHarvestCommand(actor_id="1", target_id="2", spot_id="1", current_tick=100))
        
        # プレイヤー2が開始を試みる
        from ai_rpg_world.application.harvest.exceptions.command.harvest_command_exception import HarvestCommandException
        with pytest.raises(HarvestCommandException, match="already being harvested"):
            service.start_harvest(StartHarvestCommand(actor_id="3", target_id="2", spot_id="1", current_tick=100))

    def test_start_harvest_actor_busy(self, setup_service):
        """アクターがビジー状態（移動中など）で採取を開始できないテスト"""
        s = setup_service
        service = s["service"]
        
        spot_id = SpotId.create(1)
        actor_id = WorldObjectId(1)
        target_id = WorldObjectId(2)
        
        from ai_rpg_world.domain.world.entity.tile import Tile
        from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
        from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
        tiles = [Tile(Coordinate(0, 0, 0), TerrainType.grass()), Tile(Coordinate(1, 0, 0), TerrainType.grass())]
        
        harvestable = HarvestableComponent(loot_table_id="iron_loot")
        target_obj = WorldObject(target_id, Coordinate(1, 0, 0), ObjectTypeEnum.RESOURCE, component=harvestable)
        actor_obj = WorldObject(actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.NPC, component=ActorComponent(direction=DirectionEnum.EAST))
        # アクターをビジーにする
        actor_obj.set_busy(WorldTick(110))
        
        physical_map = PhysicalMapAggregate.create(spot_id, tiles, objects=[actor_obj, target_obj])
        s["physical_map_repo"].save(physical_map)
        s["status_repo"].save(PlayerStatusAggregate(player_id=PlayerId(1), stamina=Stamina.create(100, 100), base_stats=MagicMock(), stat_growth_factor=MagicMock(), exp_table=MagicMock(), growth=MagicMock(), gold=MagicMock(), hp=MagicMock(), mp=MagicMock()))
        s["inventory_repo"].save(PlayerInventoryAggregate.create_new_inventory(PlayerId(1)))
        
        from ai_rpg_world.application.harvest.exceptions.command.harvest_command_exception import HarvestCommandException
        with pytest.raises(HarvestCommandException, match="busy until"):
            service.start_harvest(StartHarvestCommand(actor_id="1", target_id="2", spot_id="1", current_tick=105))

    def test_start_harvest_non_player_actor(self, setup_service):
        """プレイヤーデータが存在しないアクター（NPCなど）が採取を開始できないテスト"""
        s = setup_service
        service = s["service"]
        
        spot_id = SpotId.create(1)
        actor_id = WorldObjectId(99) # プレイヤーデータがないID
        target_id = WorldObjectId(2)
        
        from ai_rpg_world.domain.world.entity.tile import Tile
        from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
        from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
        tiles = [Tile(Coordinate(0, 0, 0), TerrainType.grass()), Tile(Coordinate(1, 0, 0), TerrainType.grass())]
        
        harvestable = HarvestableComponent(loot_table_id="iron_loot")
        target_obj = WorldObject(target_id, Coordinate(1, 0, 0), ObjectTypeEnum.RESOURCE, component=harvestable)
        actor_obj = WorldObject(actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.NPC, component=ActorComponent(direction=DirectionEnum.EAST))
        
        physical_map = PhysicalMapAggregate.create(spot_id, tiles, objects=[actor_obj, target_obj])
        s["physical_map_repo"].save(physical_map)
        # s["status_repo"] には何も保存しない
        
        from ai_rpg_world.application.harvest.exceptions.command.harvest_command_exception import HarvestActorNotFoundException
        with pytest.raises(HarvestActorNotFoundException):
            service.start_harvest(StartHarvestCommand(actor_id="99", target_id="2", spot_id="1", current_tick=100))

    def test_spot_id_create_invalid_format(self):
        """SpotId.create に不正な形式を渡した場合のテスト"""
        from ai_rpg_world.domain.world.exception.map_exception import SpotIdValidationException
        with pytest.raises(SpotIdValidationException, match="Invalid Spot ID format"):
            SpotId.create("invalid")

