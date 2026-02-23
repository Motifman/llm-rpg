import pytest

from ai_rpg_world.application.monster.services.monster_spawn_application_service import MonsterSpawnApplicationService
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum, MonsterStatusEnum
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import InMemoryPhysicalMapRepository
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.application.monster.exceptions import (
    MonsterNotFoundException,
    MonsterAlreadySpawnedApplicationException,
    MapNotFoundForMonsterSkillException,
)
from ai_rpg_world.domain.monster.event.monster_events import MonsterSpawnedEvent


class _FakeUow(UnitOfWork):
    def __init__(self):
        self.events = []

    def begin(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def commit(self):
        pass

    def rollback(self):
        pass

    def add_events(self, events):
        self.events.extend(events)

    def register_aggregate(self, aggregate):
        pass

    def process_sync_events(self):
        pass


class _InMemoryMonsterRepo:
    def __init__(self):
        self.data = {}

    def find_by_id(self, entity_id: MonsterId):
        return self.data.get(entity_id)

    def save(self, entity: MonsterAggregate):
        self.data[entity.monster_id] = entity
        return entity


def _sample_monster_template(template_id: int) -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId(template_id),
        name="Slime",
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        reward_info=RewardInfo(10, 5, 1),
        respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.ENEMY,
        description="A sample monster",
    )


def _create_sample_map(spot_id_int: int) -> PhysicalMapAggregate:
    tiles = [Tile(Coordinate(x, y, 0), TerrainType.grass()) for x in range(10) for y in range(10)]
    return PhysicalMapAggregate.create(SpotId(spot_id_int), tiles)


class TestMonsterSpawnApplicationService:
    @pytest.fixture
    def setup(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()
        monster_repo = _InMemoryMonsterRepo()
        map_repo = InMemoryPhysicalMapRepository(data_store)
        uow = _FakeUow()
        service = MonsterSpawnApplicationService(
            monster_repository=monster_repo,
            physical_map_repository=map_repo,
            unit_of_work=uow,
        )
        return service, monster_repo, map_repo, uow

    class TestSpawnMonsterSuccess:
        def test_spawn_monster_success(self, setup):
            """正常にスポーンできること"""
            service, monster_repo, map_repo, uow = setup
            monster_id = MonsterId(1)
            spot_id = SpotId(1)
            coordinate = Coordinate(5, 5, 0)

            loadout = SkillLoadoutAggregate.create(
                SkillLoadoutId(1),
                owner_id=1001,
                normal_capacity=10,
                awakened_capacity=10,
            )
            monster = MonsterAggregate.create(
                monster_id=monster_id,
                template=_sample_monster_template(1),
                world_object_id=WorldObjectId(1001),
                skill_loadout=loadout,
            )
            monster_repo.save(monster)

            pmap = _create_sample_map(1)
            map_repo.save(pmap)

            current_tick = WorldTick(0)
            service.spawn_monster(monster_id, spot_id, coordinate, current_tick)

            updated = monster_repo.find_by_id(monster_id)
            assert updated is not None
            assert updated.coordinate == coordinate
            assert updated.spawned_at_tick == current_tick
            assert updated.spot_id == spot_id
            assert updated.status == MonsterStatusEnum.ALIVE
            assert updated.hp.value == 100

        def test_spawn_monster_emits_spawned_event_after_commit(self, setup):
            """スポーン後にコミットすると MonsterSpawnedEvent が発行されること（UoW がイベントを収集する場合）"""
            service, monster_repo, map_repo, uow = setup
            monster_id = MonsterId(1)
            spot_id = SpotId(1)
            coordinate = Coordinate(3, 4, 0)

            loadout = SkillLoadoutAggregate.create(
                SkillLoadoutId(1),
                owner_id=1001,
                normal_capacity=10,
                awakened_capacity=10,
            )
            monster = MonsterAggregate.create(
                monster_id=monster_id,
                template=_sample_monster_template(1),
                world_object_id=WorldObjectId(1001),
                skill_loadout=loadout,
            )
            monster_repo.save(monster)
            map_repo.save(_create_sample_map(1))

            service.spawn_monster(monster_id, spot_id, coordinate, WorldTick(0))

            updated = monster_repo.find_by_id(monster_id)
            assert updated is not None
            events = updated.get_events()
            assert any(isinstance(e, MonsterSpawnedEvent) for e in events)
            spawn_event = next(e for e in events if isinstance(e, MonsterSpawnedEvent))
            assert spawn_event.coordinate == {"x": 3, "y": 4, "z": 0}
            assert spawn_event.spot_id == spot_id
            assert spawn_event.aggregate_id == monster_id

    class TestSpawnMonsterExceptions:
        def test_spawn_monster_not_found_raises(self, setup):
            """モンスターが存在しない場合 MonsterNotFoundException を投げること"""
            service, monster_repo, map_repo, uow = setup
            map_repo.save(_create_sample_map(1))

            with pytest.raises(MonsterNotFoundException) as excinfo:
                service.spawn_monster(
                    MonsterId(999),
                    SpotId(1),
                    Coordinate(0, 0, 0),
                    WorldTick(0),
                )
            assert "999" in str(excinfo.value)
            assert "モンスターが見つかりません" in str(excinfo.value)

        def test_spawn_monster_map_not_found_raises(self, setup):
            """マップが存在しない場合 MapNotFoundForMonsterSkillException を投げること"""
            service, monster_repo, map_repo, uow = setup
            monster_id = MonsterId(1)
            loadout = SkillLoadoutAggregate.create(
                SkillLoadoutId(1),
                owner_id=1001,
                normal_capacity=10,
                awakened_capacity=10,
            )
            monster = MonsterAggregate.create(
                monster_id=monster_id,
                template=_sample_monster_template(1),
                world_object_id=WorldObjectId(1001),
                skill_loadout=loadout,
            )
            monster_repo.save(monster)
            # マップは保存しない（SpotId(99) のマップがない）

            with pytest.raises(MapNotFoundForMonsterSkillException) as excinfo:
                service.spawn_monster(monster_id, SpotId(99), Coordinate(0, 0, 0), WorldTick(0))
            assert "99" in str(excinfo.value)

        def test_spawn_monster_already_spawned_raises(self, setup):
            """既に出現済みのモンスターをスポーンすると MonsterAlreadySpawnedApplicationException を投げること"""
            service, monster_repo, map_repo, uow = setup
            monster_id = MonsterId(1)
            spot_id = SpotId(1)
            loadout = SkillLoadoutAggregate.create(
                SkillLoadoutId(1),
                owner_id=1001,
                normal_capacity=10,
                awakened_capacity=10,
            )
            monster = MonsterAggregate.create(
                monster_id=monster_id,
                template=_sample_monster_template(1),
                world_object_id=WorldObjectId(1001),
                skill_loadout=loadout,
            )
            monster.spawn(Coordinate(1, 1, 0), spot_id, WorldTick(0))
            monster.clear_events()
            monster_repo.save(monster)
            map_repo.save(_create_sample_map(1))

            with pytest.raises(MonsterAlreadySpawnedApplicationException) as excinfo:
                service.spawn_monster(monster_id, spot_id, Coordinate(2, 2, 0), WorldTick(1))
            assert "1" in str(excinfo.value)
            assert "既に出現済み" in str(excinfo.value)
