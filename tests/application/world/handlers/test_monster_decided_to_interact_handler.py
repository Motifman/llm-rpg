"""MonsterDecidedToInteractEvent を購読し interact_with を実行する MonsterDecidedToInteractHandler のテスト。"""

import pytest
from ai_rpg_world.application.world.handlers.monster_decided_to_interact_handler import (
    MonsterDecidedToInteractHandler,
)
from ai_rpg_world.domain.monster.event.monster_events import MonsterDecidedToInteractEvent
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    AutonomousBehaviorComponent,
    HarvestableComponent,
)
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore


class TestMonsterDecidedToInteractHandler:
    """MonsterDecidedToInteractHandler の正常・スキップ・例外ケース"""

    @pytest.fixture
    def handler_deps(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()
        uow = InMemoryUnitOfWork(unit_of_work_factory=lambda: None, data_store=data_store)
        map_repo = InMemoryPhysicalMapRepository(data_store, uow)
        handler = MonsterDecidedToInteractHandler(physical_map_repository=map_repo)
        return {"handler": handler, "map_repo": map_repo, "uow": uow}

    def test_handle_interact_success(self, handler_deps):
        """正常: マップが存在し actor と target が同一マスなら interact_with が実行され資源が1消費されること"""
        s = handler_deps
        tiles = [Tile(Coordinate(0, 0, 0), TerrainType.grass())]
        pmap = PhysicalMapAggregate.create(SpotId(1), tiles)
        monster_comp = AutonomousBehaviorComponent(vision_range=5)
        monster = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=monster_comp,
        )
        harvestable = WorldObject(
            object_id=WorldObjectId(2),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.RESOURCE,
            is_blocking=False,
            component=HarvestableComponent(loot_table_id=1, max_quantity=2, initial_quantity=2),
        )
        pmap.add_object(monster)
        pmap.add_object(harvestable)
        s["map_repo"].save(pmap)

        event = MonsterDecidedToInteractEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            spot_id=SpotId(1),
            current_tick=WorldTick(10),
        )
        with s["uow"]:
            s["handler"].handle(event)

        loaded = s["map_repo"].find_by_spot_id(SpotId(1))
        assert loaded is not None
        target_obj = loaded.get_object(WorldObjectId(2))
        assert target_obj.component.get_available_quantity(WorldTick(10)) == 1

    def test_handle_map_not_found_skips(self, handler_deps):
        """マップが存在しない場合はスキップし例外を出さないこと"""
        s = handler_deps
        event = MonsterDecidedToInteractEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            spot_id=SpotId(999),
            current_tick=WorldTick(10),
        )
        with s["uow"]:
            s["handler"].handle(event)
        assert s["map_repo"].find_by_spot_id(SpotId(999)) is None

    def test_handle_domain_exception_skips(self, handler_deps):
        """interact_with がドメイン例外（例: ターゲット不在）の場合はログのみでスキップすること"""
        s = handler_deps
        tiles = [Tile(Coordinate(0, 0, 0), TerrainType.grass())]
        pmap = PhysicalMapAggregate.create(SpotId(1), tiles)
        monster = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=AutonomousBehaviorComponent(vision_range=5),
        )
        pmap.add_object(monster)
        s["map_repo"].save(pmap)

        event = MonsterDecidedToInteractEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(999),
            spot_id=SpotId(1),
            current_tick=WorldTick(10),
        )
        with s["uow"]:
            s["handler"].handle(event)
        # ターゲットがマップにいないので get_object で例外になるか、interact で NotInteractable 等になる。いずれにせよスキップされ例外は外に出ない
        loaded = s["map_repo"].find_by_spot_id(SpotId(1))
        assert loaded is not None
        assert loaded.get_object(WorldObjectId(1)).coordinate == Coordinate(0, 0, 0)
