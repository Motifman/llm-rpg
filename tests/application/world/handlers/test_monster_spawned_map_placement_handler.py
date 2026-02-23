import pytest

from ai_rpg_world.application.monster.exceptions import (
    MonsterNotFoundException,
    MapNotFoundForMonsterSkillException,
)
from ai_rpg_world.application.world.handlers.monster_spawned_map_placement_handler import (
    MonsterSpawnedMapPlacementHandler,
)
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.event.monster_events import (
    MonsterSpawnedEvent,
    MonsterRespawnedEvent,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent
from ai_rpg_world.domain.monster.value_object.monster_skill_info import MonsterSkillInfo
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillHitPatternType
from ai_rpg_world.domain.skill.value_object.skill_hit_pattern import SkillHitPattern
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.enum.player_enum import Race, Element
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import (
    InMemoryMonsterAggregateRepository,
)
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork


class _FakeUow(UnitOfWork):
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
        pass

    def register_aggregate(self, aggregate):
        pass

    def process_sync_events(self):
        pass


def _create_map(spot_id_int: int) -> PhysicalMapAggregate:
    tiles = [
        Tile(Coordinate(x, y, 0), TerrainType.grass())
        for x in range(10)
        for y in range(10)
    ]
    return PhysicalMapAggregate.create(SpotId(spot_id_int), tiles)


def _sample_template(
    template_id: int = 1,
    vision_range: int = 7,
    flee_threshold: float = 0.25,
) -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId(template_id),
        name="Goblin",
        base_stats=BaseStats(80, 30, 12, 8, 9, 0.05, 0.05),
        reward_info=RewardInfo(15, 8, 1),
        respawn_info=RespawnInfo(respawn_interval_ticks=80, is_auto_respawn=True),
        race=Race.GOBLIN,
        faction=MonsterFactionEnum.ENEMY,
        description="A goblin.",
        vision_range=vision_range,
        flee_threshold=flee_threshold,
    )


def _sample_skill_spec(skill_id: int = 1, targeting_range: int = 3, mp_cost: int = 5) -> SkillSpec:
    return SkillSpec(
        skill_id=SkillId(skill_id),
        name="Slash",
        element=Element.NEUTRAL,
        deck_cost=1,
        cast_lock_ticks=1,
        cooldown_ticks=5,
        power_multiplier=1.2,
        hit_pattern=SkillHitPattern.single_pulse(
            SkillHitPatternType.MELEE,
            HitBoxShape.single_cell(),
        ),
        targeting_range=targeting_range,
        mp_cost=mp_cost,
    )


class TestMonsterSpawnedMapPlacementHandler:
    @pytest.fixture
    def setup(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()
        monster_repo = InMemoryMonsterAggregateRepository(data_store=data_store)
        map_repo = InMemoryPhysicalMapRepository(data_store=data_store)
        uow = _FakeUow()
        handler = MonsterSpawnedMapPlacementHandler(
            monster_repository=monster_repo,
            physical_map_repository=map_repo,
            unit_of_work=uow,
        )
        return handler, monster_repo, map_repo

    class TestHandleMonsterSpawnedEvent:
        def test_places_object_on_map_with_component(self, setup):
            """MonsterSpawnedEvent でマップに WorldObject が配置され、テンプレートの vision_range / flee_threshold が反映されること"""
            handler, monster_repo, map_repo = setup
            monster_id = MonsterId(1)
            spot_id = SpotId(1)
            world_object_id = WorldObjectId(100)

            loadout = SkillLoadoutAggregate.create(
                SkillLoadoutId(1),
                owner_id=world_object_id.value,
                normal_capacity=10,
                awakened_capacity=10,
            )
            skill = _sample_skill_spec(1, targeting_range=4, mp_cost=10)
            loadout.equip_skill(DeckTier.NORMAL, 0, skill)

            monster = MonsterAggregate.create(
                monster_id=monster_id,
                template=_sample_template(1, vision_range=8, flee_threshold=0.3),
                world_object_id=world_object_id,
                skill_loadout=loadout,
            )
            monster_repo.save(monster)
            map_repo.save(_create_map(1))

            event = MonsterSpawnedEvent.create(
                aggregate_id=monster_id,
                aggregate_type="MonsterAggregate",
                coordinate={"x": 3, "y": 4, "z": 0},
                spot_id=spot_id,
            )

            handler.handle(event)

            physical_map = map_repo.find_by_spot_id(spot_id)
            assert physical_map is not None
            obj = physical_map.get_object(world_object_id)
            assert obj is not None
            assert obj.coordinate == Coordinate(3, 4, 0)
            assert obj.object_type == ObjectTypeEnum.NPC
            assert isinstance(obj.component, AutonomousBehaviorComponent)
            assert obj.component.vision_range == 8
            assert len(obj.component.available_skills) == 1
            assert obj.component.available_skills[0].slot_index == 0
            assert obj.component.available_skills[0].range == 4
            assert obj.component.available_skills[0].mp_cost == 10

        def test_handles_respawned_event_same_as_spawned(self, setup):
            """MonsterRespawnedEvent でも同様にマップに配置されること"""
            handler, monster_repo, map_repo = setup
            monster_id = MonsterId(2)
            spot_id = SpotId(2)
            world_object_id = WorldObjectId(200)

            loadout = SkillLoadoutAggregate.create(
                SkillLoadoutId(2),
                owner_id=world_object_id.value,
                normal_capacity=10,
                awakened_capacity=10,
            )
            monster = MonsterAggregate.create(
                monster_id=monster_id,
                template=_sample_template(2),
                world_object_id=world_object_id,
                skill_loadout=loadout,
            )
            monster_repo.save(monster)
            map_repo.save(_create_map(2))

            event = MonsterRespawnedEvent.create(
                aggregate_id=monster_id,
                aggregate_type="MonsterAggregate",
                coordinate={"x": 1, "y": 2, "z": 0},
                spot_id=spot_id,
            )

            handler.handle(event)

            physical_map = map_repo.find_by_spot_id(spot_id)
            assert physical_map is not None
            obj = physical_map.get_object(world_object_id)
            assert obj is not None
            assert obj.coordinate == Coordinate(1, 2, 0)
            assert isinstance(obj.component, AutonomousBehaviorComponent)
            assert obj.component.vision_range == 7  # from template

        def test_monster_not_found_raises(self, setup):
            """モンスターが存在しない場合は MonsterNotFoundException を投げること"""
            handler, monster_repo, map_repo = setup
            map_repo.save(_create_map(1))

            event = MonsterSpawnedEvent.create(
                aggregate_id=MonsterId(999),
                aggregate_type="MonsterAggregate",
                coordinate={"x": 0, "y": 0, "z": 0},
                spot_id=SpotId(1),
            )

            with pytest.raises(MonsterNotFoundException) as excinfo:
                handler.handle(event)
            assert "999" in str(excinfo.value)

        def test_map_not_found_raises(self, setup):
            """マップが存在しない場合は MapNotFoundForMonsterSkillException を投げること"""
            handler, monster_repo, map_repo = setup
            monster_id = MonsterId(1)
            loadout = SkillLoadoutAggregate.create(
                SkillLoadoutId(1),
                owner_id=1001,
                normal_capacity=10,
                awakened_capacity=10,
            )
            monster = MonsterAggregate.create(
                monster_id=monster_id,
                template=_sample_template(1),
                world_object_id=WorldObjectId(1001),
                skill_loadout=loadout,
            )
            monster_repo.save(monster)

            event = MonsterSpawnedEvent.create(
                aggregate_id=monster_id,
                aggregate_type="MonsterAggregate",
                coordinate={"x": 0, "y": 0, "z": 0},
                spot_id=SpotId(99),
            )

            with pytest.raises(MapNotFoundForMonsterSkillException) as excinfo:
                handler.handle(event)
            assert "99" in str(excinfo.value)
