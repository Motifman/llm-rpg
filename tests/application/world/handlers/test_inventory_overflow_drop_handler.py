"""InventoryOverflowDropHandler のテスト"""

import pytest
from ai_rpg_world.application.world.handlers.inventory_overflow_drop_handler import InventoryOverflowDropHandler
from ai_rpg_world.domain.player.event.inventory_events import InventorySlotOverflowEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import InMemoryPlayerStatusRepository
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import InMemoryPhysicalMapRepository
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


def _create_map(spot_id_int: int = 1) -> PhysicalMapAggregate:
    tiles = [Tile(Coordinate(x, y, 0), TerrainType.road()) for x in range(5) for y in range(5)]
    return PhysicalMapAggregate.create(SpotId(spot_id_int), tiles)


class TestInventoryOverflowDropHandler:
    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def unit_of_work(self, data_store):
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)
        return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)

    @pytest.fixture
    def handler(self, data_store, unit_of_work):
        status_repo = InMemoryPlayerStatusRepository(data_store, unit_of_work)
        map_repo = InMemoryPhysicalMapRepository(data_store, unit_of_work)
        return InventoryOverflowDropHandler(
            player_status_repository=status_repo,
            physical_map_repository=map_repo,
        )

    @pytest.fixture
    def player_at_spot(self, data_store, unit_of_work):
        status_repo = InMemoryPlayerStatusRepository(data_store, unit_of_work)
        map_repo = InMemoryPhysicalMapRepository(data_store, unit_of_work)
        spot_id = SpotId(1)
        coord = Coordinate(2, 2, 0)
        pmap = _create_map(1)
        map_repo.save(pmap)
        exp_table = ExpTable(100, 1.5)
        status = PlayerStatusAggregate(
            player_id=PlayerId(1),
            base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
            stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
            exp_table=exp_table,
            growth=Growth(1, 0, exp_table),
            gold=Gold(1000),
            hp=Hp.create(100, 100),
            mp=Mp.create(50, 50),
            stamina=Stamina.create(100, 100),
            current_spot_id=spot_id,
            current_coordinate=coord,
        )
        status_repo.save(status)
        return map_repo, status_repo, PlayerId(1), coord

    def test_overflow_drop_creates_ground_item_at_player_position(self, handler, player_at_spot):
        """満杯溢れ時にプレイヤー座標に GROUND_ITEM が追加されること"""
        map_repo, status_repo, player_id, coord = player_at_spot
        overflowed_id = ItemInstanceId(999)
        event = InventorySlotOverflowEvent.create(
            aggregate_id=player_id,
            aggregate_type="PlayerInventoryAggregate",
            overflowed_item_instance_id=overflowed_id,
            reason="inventory_full_on_acquire",
        )
        handler.handle(event)
        pmap = map_repo.find_by_spot_id(SpotId(1))
        objs = pmap.get_objects_at(coord)
        assert len(objs) == 1
        assert objs[0].object_type == ObjectTypeEnum.GROUND_ITEM
        assert objs[0].component.item_instance_id == overflowed_id
        assert objs[0].is_blocking is False


class TestInventoryOverflowEventHandlerRegistry:
    """InventoryOverflowEventHandlerRegistry で同期ハンドラが登録されること"""

    def test_register_handlers_registers_sync_handler(self):
        from unittest.mock import MagicMock
        from ai_rpg_world.infrastructure.events.inventory_overflow_event_handler_registry import (
            InventoryOverflowEventHandlerRegistry,
        )

        handler = MagicMock(spec=InventoryOverflowDropHandler)
        registry = InventoryOverflowEventHandlerRegistry(inventory_overflow_drop_handler=handler)
        event_publisher = MagicMock()

        registry.register_handlers(event_publisher)

        event_publisher.register_handler.assert_called_once()
        call_kw = event_publisher.register_handler.call_args
        assert call_kw[0][0] is InventorySlotOverflowEvent
        assert call_kw[1]["is_synchronous"] is True
