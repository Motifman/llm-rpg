import pytest
import unittest.mock as mock
from ai_rpg_world.application.monster.services.monster_skill_application_service import MonsterSkillApplicationService
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.monster_hp import MonsterHp
from ai_rpg_world.domain.monster.value_object.monster_mp import MonsterMp
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterStatusEnum, MonsterFactionEnum
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.repository.skill_repository import SkillLoadoutRepository, SkillSpecRepository
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillHitPatternType
from ai_rpg_world.domain.skill.value_object.skill_hit_pattern import SkillHitPattern
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.combat.repository.hit_box_repository import HitBoxRepository
from ai_rpg_world.domain.combat.service.hit_box_factory import HitBoxFactory
from ai_rpg_world.domain.skill.service.skill_execution_service import SkillExecutionDomainService
from ai_rpg_world.domain.skill.service.skill_to_hitbox_service import SkillToHitBoxDomainService
from ai_rpg_world.domain.skill.service.skill_targeting_service import SkillTargetingDomainService
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent, AutonomousBehaviorComponent
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, ObjectTypeEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.infrastructure.repository.in_memory_hit_box_repository import InMemoryHitBoxRepository
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import InMemoryPhysicalMapRepository
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.player.enum.player_enum import Race, Element
from ai_rpg_world.application.common.exceptions import ApplicationException
from ai_rpg_world.application.monster.exceptions import (
    MonsterNotFoundForSkillException,
    MonsterSkillNotFoundInSlotException,
    MapNotFoundForMonsterSkillException,
    MonsterNotOnMapException,
)
from ai_rpg_world.domain.skill.constants import MAX_SKILL_SLOTS

class _FakeUow(UnitOfWork):
    def __init__(self): self.events = []
    def begin(self): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def commit(self): pass
    def rollback(self): pass
    def add_events(self, events): self.events.extend(events)
    def register_aggregate(self, aggregate): pass
    def process_sync_events(self): pass

class _InMemoryRepo:
    def __init__(self): self.data = {}
    def find_by_id(self, id): return self.data.get(id)
    def save(self, entity): self.data[getattr(entity, list(entity.__dict__.keys())[0])] = entity

class _MonsterRepo(_InMemoryRepo):
    def save(self, entity): self.data[entity.monster_id] = entity
    def find_by_world_object_id(self, world_object_id):
        for m in self.data.values():
            if m.world_object_id == world_object_id: return m
        return None

class _LoadoutRepo(_InMemoryRepo):
    def save(self, entity): self.data[entity.loadout_id] = entity

class _SpecRepo(_InMemoryRepo):
    def save(self, entity): self.data[entity.skill_id] = entity

def _sample_monster_template(template_id: int) -> MonsterTemplate:
    return MonsterTemplate(
        template_id=MonsterTemplateId(template_id),
        name=f"monster-{template_id}",
        base_stats=BaseStats(100, 100, 10, 10, 10, 0.05, 0.05),
        reward_info=RewardInfo(10, 10, "loot-1"),
        respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
        race=Race.HUMAN,
        faction=MonsterFactionEnum.ENEMY,
        description="A sample monster",
        skill_ids=[SkillId(1)]
    )

def _sample_skill(skill_id: int, mp_cost=0) -> SkillSpec:
    return SkillSpec(
        skill_id=SkillId(skill_id),
        name=f"skill-{skill_id}",
        element=Element.NEUTRAL,
        deck_cost=1,
        cast_lock_ticks=1,
        cooldown_ticks=5,
        power_multiplier=1.2,
        hit_pattern=SkillHitPattern.single_pulse(SkillHitPatternType.MELEE, HitBoxShape.single_cell()),
        mp_cost=mp_cost
    )

def _create_sample_map(spot_id_int: int) -> PhysicalMapAggregate:
    tiles = []
    for x in range(20):
        for y in range(20):
            tiles.append(Tile(Coordinate(x, y, 0), TerrainType.road()))
    return PhysicalMapAggregate.create(SpotId(spot_id_int), tiles)

class TestMonsterSkillApplicationService:
    @pytest.fixture
    def setup(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()
        
        monster_repo = _MonsterRepo()
        loadout_repo = _LoadoutRepo()
        spec_repo = _SpecRepo()
        map_repo = InMemoryPhysicalMapRepository(data_store)
        hitbox_repo = InMemoryHitBoxRepository(data_store)
        skill_to_hitbox_service = SkillToHitBoxDomainService()
        skill_targeting_service = SkillTargetingDomainService()
        skill_execution_service = SkillExecutionDomainService(skill_targeting_service, skill_to_hitbox_service)
        hitbox_factory = HitBoxFactory()
        uow = _FakeUow()
        
        service = MonsterSkillApplicationService(
            monster_repo,
            loadout_repo,
            spec_repo,
            map_repo,
            hitbox_repo,
            skill_execution_service,
            hitbox_factory,
            uow
        )
        return service, monster_repo, loadout_repo, spec_repo, map_repo, hitbox_repo, uow

    def test_use_monster_skill_success(self, setup):
        service, monster_repo, loadout_repo, spec_repo, map_repo, hitbox_repo, _ = setup
        
        spot_id = SpotId(1)
        monster_id = MonsterId(100)
        world_object_id = WorldObjectId(1000)
        loadout_id = SkillLoadoutId(500)
        
        # 1. マップ準備
        pmap = _create_sample_map(1)
        component = AutonomousBehaviorComponent(direction=DirectionEnum.SOUTH)
        monster_obj = WorldObject(world_object_id, Coordinate(5, 5, 0), ObjectTypeEnum.NPC, component=component)
        pmap.add_object(monster_obj)
        map_repo.save(pmap)
        
        # 2. スキル準備
        skill = _sample_skill(1, mp_cost=10)
        spec_repo.save(skill)
        
        # 3. モンスター準備
        template = _sample_monster_template(1)
        loadout = SkillLoadoutAggregate.create(loadout_id, 1000, 10, 10)
        loadout.equip_skill(DeckTier.NORMAL, 0, skill)
        loadout_repo.save(loadout)
        
        monster = MonsterAggregate.create(monster_id, template, world_object_id, skill_loadout=loadout)
        monster.spawn(Coordinate(5, 5, 0), SpotId(1))
        monster_repo.save(monster)
        
        # 実行
        service.use_monster_skill(world_object_id, spot_id, 0, WorldTick(10))
        
        # 検証
        # MP消費
        updated_monster = monster_repo.find_by_id(monster_id)
        assert updated_monster.mp.value == 90
        
        # クールダウン
        assert updated_monster.skill_loadout.can_use_skill(0, 10) is False
        
        # ヒットボックス生成
        hitboxes = hitbox_repo.find_active_by_spot_id(spot_id)
        assert len(hitboxes) == 1
        assert hitboxes[0].owner_id == world_object_id
        assert hitboxes[0].skill_id == "1"

    def test_use_monster_skill_fails_insufficient_mp(self, setup):
        service, monster_repo, loadout_repo, spec_repo, map_repo, _, _ = setup
        
        spot_id = SpotId(1)
        monster_id = MonsterId(100)
        world_object_id = WorldObjectId(1000)
        
        pmap = _create_sample_map(1)
        monster_obj = WorldObject(world_object_id, Coordinate(5, 5, 0), ObjectTypeEnum.NPC, component=ActorComponent())
        pmap.add_object(monster_obj)
        map_repo.save(pmap)
        
        skill = _sample_skill(1, mp_cost=200) # 初期MP100より多い
        spec_repo.save(skill)
        
        loadout = SkillLoadoutAggregate.create(SkillLoadoutId(500), 1000, 10, 10)
        loadout.equip_skill(DeckTier.NORMAL, 0, skill)
        loadout_repo.save(loadout)
        
        monster = MonsterAggregate.create(monster_id, _sample_monster_template(1), world_object_id, skill_loadout=loadout)
        monster.spawn(Coordinate(5, 5, 0), SpotId(1))
        monster_repo.save(monster)
        
        with pytest.raises(ApplicationException, match="Insufficient MP"):
            service.use_monster_skill(world_object_id, spot_id, 0, WorldTick(10))

    def test_use_monster_skill_fails_on_cooldown(self, setup):
        service, monster_repo, loadout_repo, spec_repo, map_repo, _, _ = setup
        
        spot_id = SpotId(1)
        world_object_id = WorldObjectId(1000)
        
        pmap = _create_sample_map(1)
        monster_obj = WorldObject(world_object_id, Coordinate(5, 5, 0), ObjectTypeEnum.NPC, component=ActorComponent())
        pmap.add_object(monster_obj)
        map_repo.save(pmap)
        
        skill = _sample_skill(1) # cooldown 5
        spec_repo.save(skill)
        
        loadout = SkillLoadoutAggregate.create(SkillLoadoutId(500), 1000, 10, 10)
        loadout.equip_skill(DeckTier.NORMAL, 0, skill)
        loadout_repo.save(loadout)
        
        monster = MonsterAggregate.create(MonsterId(100), _sample_monster_template(1), world_object_id, skill_loadout=loadout)
        monster.spawn(Coordinate(5, 5, 0), SpotId(1))
        monster_repo.save(monster)
        
        # 1回目
        service.use_monster_skill(world_object_id, spot_id, 0, WorldTick(10))
        
        # 2回目 (Tick 12) -> 失敗
        with pytest.raises(ApplicationException, match="cooldown"):
            service.use_monster_skill(world_object_id, spot_id, 0, WorldTick(12))

    def test_use_monster_skill_monster_not_found_raises(self, setup):
        """モンスターが見つからない場合は MonsterNotFoundForSkillException を投げること"""
        service, _, _, _, _, _, _ = setup
        with pytest.raises(MonsterNotFoundForSkillException) as excinfo:
            service.use_monster_skill(WorldObjectId(999), SpotId(1), 0, WorldTick(10))
        assert "モンスターが見つかりません" in str(excinfo.value)
        assert "999" in str(excinfo.value)

    def test_use_monster_skill_map_not_found_raises(self, setup):
        """マップが存在しない場合は MapNotFoundForMonsterSkillException を投げること"""
        service, monster_repo, loadout_repo, spec_repo, map_repo, _, _ = setup
        spot_id = SpotId(1)
        world_object_id = WorldObjectId(1000)
        monster_id = MonsterId(100)
        # マップは保存しない（別の spot_id で呼ぶか、何も保存しない）
        pmap = _create_sample_map(99)
        map_repo.save(pmap)
        skill = _sample_skill(1)
        spec_repo.save(skill)
        loadout = SkillLoadoutAggregate.create(SkillLoadoutId(500), 1000, 10, 10)
        loadout.equip_skill(DeckTier.NORMAL, 0, skill)
        loadout_repo.save(loadout)
        monster = MonsterAggregate.create(monster_id, _sample_monster_template(1), world_object_id, skill_loadout=loadout)
        monster.spawn(Coordinate(5, 5, 0), SpotId(1))
        monster_repo.save(monster)
        with pytest.raises(MapNotFoundForMonsterSkillException) as excinfo:
            service.use_monster_skill(world_object_id, SpotId(1), 0, WorldTick(10))
        assert "マップが見つかりません" in str(excinfo.value)
        assert "1" in str(excinfo.value)

    def test_use_monster_skill_skill_not_in_slot_raises(self, setup):
        """指定スロットにスキルが装備されていない場合は MonsterSkillNotFoundInSlotException を投げること"""
        service, monster_repo, loadout_repo, spec_repo, map_repo, _, _ = setup
        spot_id = SpotId(1)
        world_object_id = WorldObjectId(1000)
        monster_id = MonsterId(100)
        pmap = _create_sample_map(1)
        monster_obj = WorldObject(world_object_id, Coordinate(5, 5, 0), ObjectTypeEnum.NPC, component=ActorComponent())
        pmap.add_object(monster_obj)
        map_repo.save(pmap)
        loadout = SkillLoadoutAggregate.create(SkillLoadoutId(500), 1000, 10, 10)
        loadout_repo.save(loadout)
        monster = MonsterAggregate.create(monster_id, _sample_monster_template(1), world_object_id, skill_loadout=loadout)
        monster.spawn(Coordinate(5, 5, 0), SpotId(1))
        monster_repo.save(monster)
        with pytest.raises(MonsterSkillNotFoundInSlotException) as excinfo:
            service.use_monster_skill(world_object_id, spot_id, 0, WorldTick(10))
        assert "スロット" in str(excinfo.value)
        assert "0" in str(excinfo.value)
        assert "100" in str(excinfo.value)

    def test_use_monster_skill_domain_exception_wrapped_as_application_exception(self, setup):
        """ドメイン例外（例: モンスター死亡）は ApplicationException に包まれて再送出されること"""
        service, monster_repo, loadout_repo, spec_repo, map_repo, _, _ = setup
        spot_id = SpotId(1)
        world_object_id = WorldObjectId(1000)
        monster_id = MonsterId(100)
        pmap = _create_sample_map(1)
        monster_obj = WorldObject(world_object_id, Coordinate(5, 5, 0), ObjectTypeEnum.NPC, component=ActorComponent())
        pmap.add_object(monster_obj)
        map_repo.save(pmap)
        skill = _sample_skill(1, mp_cost=10)
        spec_repo.save(skill)
        loadout = SkillLoadoutAggregate.create(SkillLoadoutId(500), 1000, 10, 10)
        loadout.equip_skill(DeckTier.NORMAL, 0, skill)
        loadout_repo.save(loadout)
        monster = MonsterAggregate.create(monster_id, _sample_monster_template(1), world_object_id, skill_loadout=loadout)
        monster.spawn(Coordinate(5, 5, 0), SpotId(1))
        monster_repo.save(monster)
        monster.apply_damage(1000, WorldTick(10))
        monster_repo.save(monster)
        with pytest.raises(ApplicationException) as excinfo:
            service.use_monster_skill(world_object_id, spot_id, 0, WorldTick(10))
        assert "not alive" in str(excinfo.value) or "Monster" in str(excinfo.value)

    def test_use_monster_skill_slot_index_out_of_range_raises_application_exception(self, setup):
        """slot_indexが範囲外の場合はSkillDeckの例外がApplicationExceptionとして送出されること"""
        service, monster_repo, loadout_repo, spec_repo, map_repo, _, _ = setup
        spot_id = SpotId(1)
        world_object_id = WorldObjectId(1000)
        monster_id = MonsterId(100)
        pmap = _create_sample_map(1)
        monster_obj = WorldObject(world_object_id, Coordinate(5, 5, 0), ObjectTypeEnum.NPC, component=ActorComponent())
        pmap.add_object(monster_obj)
        map_repo.save(pmap)
        skill = _sample_skill(1, mp_cost=10)
        spec_repo.save(skill)
        loadout = SkillLoadoutAggregate.create(SkillLoadoutId(500), 1000, 10, 10)
        loadout.equip_skill(DeckTier.NORMAL, 0, skill)
        loadout_repo.save(loadout)
        monster = MonsterAggregate.create(monster_id, _sample_monster_template(1), world_object_id, skill_loadout=loadout)
        monster.spawn(Coordinate(5, 5, 0), SpotId(1))
        monster_repo.save(monster)
        with pytest.raises(ApplicationException) as excinfo:
            service.use_monster_skill(world_object_id, spot_id, MAX_SKILL_SLOTS, WorldTick(10))
        assert "slot_index" in str(excinfo.value) or "range" in str(excinfo.value).lower()

    def test_use_monster_skill_monster_not_on_map_raises_monster_not_on_map_exception(self, setup):
        """モンスターは存在するがマップ上にオブジェクトがない場合MonsterNotOnMapExceptionが発生すること（あり得ない状況）"""
        service, monster_repo, loadout_repo, spec_repo, map_repo, _, _ = setup
        spot_id = SpotId(1)
        world_object_id = WorldObjectId(1000)
        monster_id = MonsterId(100)
        pmap = _create_sample_map(1)
        map_repo.save(pmap)
        skill = _sample_skill(1, mp_cost=10)
        spec_repo.save(skill)
        loadout = SkillLoadoutAggregate.create(SkillLoadoutId(500), 1000, 10, 10)
        loadout.equip_skill(DeckTier.NORMAL, 0, skill)
        loadout_repo.save(loadout)
        monster = MonsterAggregate.create(monster_id, _sample_monster_template(1), world_object_id, skill_loadout=loadout)
        monster.spawn(Coordinate(5, 5, 0), SpotId(1))
        monster_repo.save(monster)
        with pytest.raises(MonsterNotOnMapException) as excinfo:
            service.use_monster_skill(world_object_id, spot_id, 0, WorldTick(10))
        assert "1000" in str(excinfo.value)
        assert "1" in str(excinfo.value)
