import pytest
import unittest.mock as mock
from ai_rpg_world.application.skill.services.skill_command_service import SkillCommandService
from ai_rpg_world.application.skill.contracts.commands import (
    EquipPlayerSkillCommand,
    ActivatePlayerAwakenedModeCommand,
    UsePlayerSkillCommand,
    GrantSkillDeckExpCommand,
    AcceptSkillProposalCommand,
    RejectSkillProposalCommand
)
from ai_rpg_world.application.skill.exceptions.command.skill_command_exception import SkillCommandException
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.aggregate.skill_deck_progress_aggregate import SkillDeckProgressAggregate
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_deck_progress_id import SkillDeckProgressId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillHitPatternType, SkillProposalType
from ai_rpg_world.domain.skill.value_object.skill_hit_pattern import SkillHitPattern, SkillHitTimelineSegment
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape, RelativeCoordinate
from ai_rpg_world.domain.combat.value_object.hit_box_velocity import HitBoxVelocity
from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate
from ai_rpg_world.domain.player.enum.player_enum import Element
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.skill.value_object.skill_proposal import SkillProposal
from ai_rpg_world.domain.skill.service.skill_to_hitbox_service import SkillToHitBoxDomainService
from ai_rpg_world.domain.skill.service.skill_targeting_service import SkillTargetingDomainService
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, ObjectTypeEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.infrastructure.repository.in_memory_hit_box_repository import InMemoryHitBoxRepository
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import InMemoryPhysicalMapRepository
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork

class _FakeUow(UnitOfWork):
    def __init__(self):
        self.events = []
    def begin(self): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def commit(self): pass
    def rollback(self): pass
    def add_events(self, events): self.events.extend(events)
    def process_sync_events(self): pass

class _InMemoryRepo:
    def __init__(self): self.data = {}
    def find_by_id(self, id): return self.data.get(id)
    def save(self, entity): self.data[getattr(entity, list(entity.__dict__.keys())[0])] = entity

class _LoadoutRepo(_InMemoryRepo):
    def save(self, entity): self.data[entity.loadout_id] = entity
    def find_by_owner_id(self, owner_id: int):
        for loadout in self.data.values():
            if loadout.owner_id == owner_id: return loadout
        return None

class _SpecRepo(_InMemoryRepo):
    def save(self, entity): self.data[entity.skill_id] = entity

class _ProgressRepo(_InMemoryRepo):
    def save(self, entity): self.data[entity.progress_id] = entity
    def find_by_owner_id(self, owner_id: int):
        for progress in self.data.values():
            if progress.owner_id == owner_id: return progress
        return None

class _PlayerRepo(_InMemoryRepo):
    def save(self, entity): self.data[entity.player_id] = entity

def _sample_skill(skill_id: int, mp_cost=0, hp_cost=0, stamina_cost=0) -> SkillSpec:
    return SkillSpec(
        skill_id=SkillId(skill_id),
        name=f"skill-{skill_id}",
        element=Element.NEUTRAL,
        deck_cost=1,
        cast_lock_ticks=1,
        cooldown_ticks=5,
        power_multiplier=1.2,
        hit_pattern=SkillHitPattern.single_pulse(SkillHitPatternType.MELEE, HitBoxShape.single_cell()),
        mp_cost=mp_cost,
        hp_cost=hp_cost,
        stamina_cost=stamina_cost
    )

def _sample_status(player_id: int) -> PlayerStatusAggregate:
    return PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=BaseStats(100, 100, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor.for_level(1),
        exp_table=ExpTable(100, 2.0),
        growth=Growth(1, 0, ExpTable(100, 2.0)),
        gold=Gold(0),
        hp=Hp.create(100, 100),
        mp=Mp.create(100, 100),
        stamina=Stamina.create(100, 100)
    )

def _create_sample_map(spot_id_int: int) -> PhysicalMapAggregate:
    tiles = []
    for x in range(20):
        for y in range(20):
            tiles.append(Tile(Coordinate(x, y, 0), TerrainType.road()))
    return PhysicalMapAggregate.create(SpotId(spot_id_int), tiles)

def _create_sample_actor(actor_id_int: int, coord: Coordinate, direction: DirectionEnum) -> WorldObject:
    component = ActorComponent(direction=direction, player_id=PlayerId(actor_id_int))
    return WorldObject(WorldObjectId(actor_id_int), coord, ObjectTypeEnum.PLAYER, component=component)

class TestSkillCommandService:
    @pytest.fixture
    def setup(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()
        
        loadout_repo = _LoadoutRepo()
        spec_repo = _SpecRepo()
        progress_repo = _ProgressRepo()
        player_repo = _PlayerRepo()
        map_repo = InMemoryPhysicalMapRepository(data_store)
        hitbox_repo = InMemoryHitBoxRepository(data_store)
        skill_to_hitbox_service = SkillToHitBoxDomainService()
        skill_targeting_service = SkillTargetingDomainService()
        uow = _FakeUow()
        
        service = SkillCommandService(
            loadout_repo, 
            spec_repo, 
            progress_repo, 
            player_repo,
            map_repo,
            hitbox_repo,
            skill_to_hitbox_service,
            skill_targeting_service,
            uow
        )
        return service, loadout_repo, spec_repo, progress_repo, player_repo, map_repo, hitbox_repo, uow

    class TestEquipPlayerSkill:
        def test_equip_success(self, setup):
            service, loadout_repo, spec_repo, _, _, _, _, _ = setup
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), 100, 10, 10)
            skill = _sample_skill(1)
            loadout_repo.save(loadout)
            spec_repo.save(skill)

            service.equip_player_skill(EquipPlayerSkillCommand(100, 1, DeckTier.NORMAL, 0, 1))
            assert loadout_repo.find_by_id(SkillLoadoutId(1)).normal_deck.get_skill(0) == skill

        def test_equip_fails_when_owner_mismatch(self, setup):
            service, loadout_repo, spec_repo, _, _, _, _, _ = setup
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), 100, 10, 10)
            loadout_repo.save(loadout)
            
            with pytest.raises(SkillCommandException, match="owner mismatch"):
                service.equip_player_skill(EquipPlayerSkillCommand(999, 1, DeckTier.NORMAL, 0, 1))

        def test_equip_fails_when_spec_not_found(self, setup):
            service, loadout_repo, _, _, _, _, _, _ = setup
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), 100, 10, 10)
            loadout_repo.save(loadout)
            
            with pytest.raises(SkillCommandException, match="skill spec not found"):
                service.equip_player_skill(EquipPlayerSkillCommand(100, 1, DeckTier.NORMAL, 0, 999))

    class TestUsePlayerSkill:
        def test_use_skill_success_and_creates_hitbox(self, setup):
            service, loadout_repo, spec_repo, _, player_repo, map_repo, hitbox_repo, _ = setup
            player_id = 100
            spot_id = 1
            
            # 準備
            map_repo.save(_create_sample_map(spot_id))
            pmap = map_repo.find_by_id(SpotId(spot_id))
            actor = _create_sample_actor(player_id, Coordinate(5, 5, 0), DirectionEnum.NORTH)
            pmap.add_object(actor)
            map_repo.save(pmap)
            
            player_repo.save(_sample_status(player_id))
            
            skill = _sample_skill(1, mp_cost=10)
            spec_repo.save(skill)
            
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), player_id, 10, 10)
            loadout.equip_skill(DeckTier.NORMAL, 0, skill)
            loadout_repo.save(loadout)

            # 実行
            service.use_player_skill(UsePlayerSkillCommand(player_id, 1, 0, 10, spot_id=spot_id))
            
            # 検証: リソース消費
            status = player_repo.find_by_id(PlayerId(player_id))
            assert status.mp.value == 90
            
            # 検証: クールダウン
            assert loadout_repo.find_by_id(SkillLoadoutId(1)).can_use_skill(0, 10) is False
            
            # 検証: ヒットボックス生成
            hitboxes = hitbox_repo.find_active_by_spot_id(SpotId(spot_id))
            assert len(hitboxes) == 1
            assert hitboxes[0].owner_id == WorldObjectId(player_id)
            assert hitboxes[0].skill_id == "1"

        def test_use_skill_with_auto_aim_success(self, setup):
            service, loadout_repo, spec_repo, _, player_repo, map_repo, hitbox_repo, _ = setup
            player_id = 100
            enemy_id = 200
            spot_id = 1
            
            # 準備: プレイヤー(5,5,NORTH), 敵(7,5,SOUTH) -> EAST方向
            pmap = _create_sample_map(spot_id)
            actor = _create_sample_actor(player_id, Coordinate(5, 5, 0), DirectionEnum.NORTH)
            enemy = _create_sample_actor(enemy_id, Coordinate(7, 5, 0), DirectionEnum.SOUTH)
            pmap.add_object(actor)
            pmap.add_object(enemy)
            map_repo.save(pmap)
            
            player_repo.save(_sample_status(player_id))
            
            skill = SkillSpec(
                skill_id=SkillId(1),
                name="Fireball",
                element=Element.FIRE,
                deck_cost=1,
                cast_lock_ticks=1,
                cooldown_ticks=5,
                power_multiplier=1.0,
                hit_pattern=SkillHitPattern.projectile(HitBoxShape.single_cell(), HitBoxVelocity(0, 1), 5) # 前方(SOUTH方向)へ飛ぶ
            )
            spec_repo.save(skill)
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), player_id, 10, 10)
            loadout.equip_skill(DeckTier.NORMAL, 0, skill)
            loadout_repo.save(loadout)

            # 実行: オートエイム
            service.use_player_skill(UsePlayerSkillCommand(player_id, 1, 0, 0, spot_id=spot_id, auto_aim=True))
            
            # 検証: ヒットボックスがEAST(1,0)に飛んでいる
            hitboxes = hitbox_repo.find_active_by_spot_id(SpotId(spot_id))
            hb = hitboxes[0]
            assert hb.velocity.dx == 1.0
            assert hb.velocity.dy == 0.0
            
            # 検証: プレイヤーの向きがEASTに変わっている
            updated_pmap = map_repo.find_by_id(SpotId(spot_id))
            assert updated_pmap.get_actor(WorldObjectId(player_id)).direction == DirectionEnum.EAST

        def test_use_skill_multi_segment_with_delay(self, setup):
            service, loadout_repo, spec_repo, _, player_repo, map_repo, hitbox_repo, _ = setup
            player_id = 100
            spot_id = 1
            pmap = _create_sample_map(spot_id)
            pmap.add_object(_create_sample_actor(player_id, Coordinate(5, 5, 0), DirectionEnum.SOUTH))
            map_repo.save(pmap)
            player_repo.save(_sample_status(player_id))
            
            # 2段攻撃: 即座に足元、10ティック後に前方2マス
            pattern = SkillHitPattern(
                pattern_type=SkillHitPatternType.MELEE,
                timeline_segments=(
                    SkillHitTimelineSegment(0, 5, HitBoxShape.single_cell()),
                    SkillHitTimelineSegment(10, 5, HitBoxShape.single_cell(), spawn_offset=RelativeCoordinate(0, 2, 0))
                )
            )
            skill = _sample_skill(1)
            # hit_pattern はイミュータブルなので再作成
            skill = SkillSpec(
                skill_id=skill.skill_id, name=skill.name, element=skill.element,
                deck_cost=skill.deck_cost, cast_lock_ticks=skill.cast_lock_ticks,
                cooldown_ticks=skill.cooldown_ticks, power_multiplier=skill.power_multiplier,
                hit_pattern=pattern
            )
            spec_repo.save(skill)
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), player_id, 10, 10)
            loadout.equip_skill(DeckTier.NORMAL, 0, skill)
            loadout_repo.save(loadout)

            # 実行
            service.use_player_skill(UsePlayerSkillCommand(player_id, 1, 0, 100, spot_id=spot_id))

            # 検証: 2つのヒットボックス
            hitboxes = hitbox_repo.find_active_by_spot_id(SpotId(spot_id))
            assert len(hitboxes) == 2
            hbs = sorted(hitboxes, key=lambda h: h.activation_tick)
            
            assert hbs[0].activation_tick == 100
            assert hbs[0].current_coordinate == Coordinate(5, 5, 0)
            
            assert hbs[1].activation_tick == 110
            assert hbs[1].current_coordinate == Coordinate(5, 7, 0) # (5,5) + SOUTH(0,2)

        def test_use_skill_fails_when_insufficient_mp(self, setup):
            service, loadout_repo, spec_repo, _, player_repo, map_repo, _, _ = setup
            player_id = 100
            spot_id = 1
            pmap = _create_sample_map(spot_id)
            pmap.add_object(_create_sample_actor(player_id, Coordinate(5, 5, 0), DirectionEnum.SOUTH))
            map_repo.save(pmap)
            
            player_repo.save(_sample_status(player_id))
            skill = _sample_skill(1, mp_cost=999)
            spec_repo.save(skill)
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), player_id, 10, 10)
            loadout.equip_skill(DeckTier.NORMAL, 0, skill)
            loadout_repo.save(loadout)

            with pytest.raises(SkillCommandException, match="MPが不足しています"):
                service.use_player_skill(UsePlayerSkillCommand(player_id, 1, 0, 10, spot_id=spot_id))

        def test_use_skill_fails_when_insufficient_stamina(self, setup):
            service, loadout_repo, spec_repo, _, player_repo, map_repo, _, _ = setup
            player_id = 100
            spot_id = 1
            pmap = _create_sample_map(spot_id)
            pmap.add_object(_create_sample_actor(player_id, Coordinate(5, 5, 0), DirectionEnum.SOUTH))
            map_repo.save(pmap)
            
            player_repo.save(_sample_status(player_id))
            skill = _sample_skill(1, stamina_cost=999)
            spec_repo.save(skill)
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), player_id, 10, 10)
            loadout.equip_skill(DeckTier.NORMAL, 0, skill)
            loadout_repo.save(loadout)

            with pytest.raises(SkillCommandException, match="スタミナが不足しています"):
                service.use_player_skill(UsePlayerSkillCommand(player_id, 1, 0, 10, spot_id=spot_id))

        def test_use_skill_fails_when_insufficient_hp(self, setup):
            service, loadout_repo, spec_repo, _, player_repo, map_repo, _, _ = setup
            player_id = 100
            spot_id = 1
            pmap = _create_sample_map(spot_id)
            pmap.add_object(_create_sample_actor(player_id, Coordinate(5, 5, 0), DirectionEnum.SOUTH))
            map_repo.save(pmap)
            
            player_repo.save(_sample_status(player_id))
            skill = _sample_skill(1, hp_cost=999)
            spec_repo.save(skill)
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), player_id, 10, 10)
            loadout.equip_skill(DeckTier.NORMAL, 0, skill)
            loadout_repo.save(loadout)

            with pytest.raises(SkillCommandException, match="HPが不足しています"):
                service.use_player_skill(UsePlayerSkillCommand(player_id, 1, 0, 10, spot_id=spot_id))

        def test_use_skill_fails_when_on_cooldown(self, setup):
            service, loadout_repo, spec_repo, _, player_repo, map_repo, _, _ = setup
            player_id = 100
            spot_id = 1
            pmap = _create_sample_map(spot_id)
            pmap.add_object(_create_sample_actor(player_id, Coordinate(5, 5, 0), DirectionEnum.SOUTH))
            map_repo.save(pmap)
            player_repo.save(_sample_status(player_id))
            
            skill = _sample_skill(1) # cooldown = 5
            spec_repo.save(skill)
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), player_id, 10, 10)
            loadout.equip_skill(DeckTier.NORMAL, 0, skill)
            loadout_repo.save(loadout)

            # 1回目使用 (Tick 0)
            service.use_player_skill(UsePlayerSkillCommand(player_id, 1, 0, 0, spot_id=spot_id))
            
            # 2回目使用 (Tick 3) -> 失敗
            with pytest.raises(SkillCommandException, match="cooldown"):
                service.use_player_skill(UsePlayerSkillCommand(player_id, 1, 0, 3, spot_id=spot_id))

        def test_use_skill_fails_when_map_not_found(self, setup):
            service, loadout_repo, spec_repo, _, player_repo, _, _, _ = setup
            player_id = 100
            player_repo.save(_sample_status(player_id))
            skill = _sample_skill(1)
            spec_repo.save(skill)
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), player_id, 10, 10)
            loadout.equip_skill(DeckTier.NORMAL, 0, skill)
            loadout_repo.save(loadout)

            with pytest.raises(SkillCommandException, match="map not found"):
                service.use_player_skill(UsePlayerSkillCommand(player_id, 1, 0, 10, spot_id=999))

        def test_use_skill_fails_when_actor_not_on_map(self, setup):
            service, loadout_repo, spec_repo, _, player_repo, map_repo, _, _ = setup
            player_id = 100
            spot_id = 1
            # マップはあるがアクターがいない
            map_repo.save(_create_sample_map(spot_id))
            player_repo.save(_sample_status(player_id))
            skill = _sample_skill(1)
            spec_repo.save(skill)
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), player_id, 10, 10)
            loadout.equip_skill(DeckTier.NORMAL, 0, skill)
            loadout_repo.save(loadout)

            with pytest.raises(SkillCommandException, match="actor not found on map"):
                service.use_player_skill(UsePlayerSkillCommand(player_id, 1, 0, 10, spot_id=spot_id))

        def test_use_skill_auto_aim_no_target_uses_current_direction(self, setup):
            service, loadout_repo, spec_repo, _, player_repo, map_repo, hitbox_repo, _ = setup
            player_id = 100
            spot_id = 1
            # 準備: プレイヤーのみ(5,5,NORTH)、他に敵はいない
            pmap = _create_sample_map(spot_id)
            actor = _create_sample_actor(player_id, Coordinate(5, 5, 0), DirectionEnum.NORTH)
            pmap.add_object(actor)
            map_repo.save(pmap)
            player_repo.save(_sample_status(player_id))
            
            # プロジェクタイルスキルを使用（前方SOUTHへ飛ぶ設定）
            skill = _sample_skill(1)
            skill = SkillSpec(
                skill_id=skill.skill_id, name=skill.name, element=skill.element,
                deck_cost=skill.deck_cost, cast_lock_ticks=skill.cast_lock_ticks,
                cooldown_ticks=skill.cooldown_ticks, power_multiplier=skill.power_multiplier,
                hit_pattern=SkillHitPattern.projectile(HitBoxShape.single_cell(), HitBoxVelocity(0, 1), 5)
            )
            spec_repo.save(skill)
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), player_id, 10, 10)
            loadout.equip_skill(DeckTier.NORMAL, 0, skill)
            loadout_repo.save(loadout)

            # 実行: オートエイムをONにするがターゲットはいない -> 現在の向き(NORTH)を維持
            service.use_player_skill(UsePlayerSkillCommand(player_id, 1, 0, 0, spot_id=spot_id, auto_aim=True))

            # 検証: NORTH(0,-1)方向にエイムされている
            hitboxes = hitbox_repo.find_active_by_spot_id(SpotId(spot_id))
            assert len(hitboxes) == 1
            assert hitboxes[0].velocity.dy == -1.0 # NORTH方向
            
        def test_use_skill_auto_aim_boundary_max_range(self, setup):
            service, loadout_repo, spec_repo, _, player_repo, map_repo, hitbox_repo, _ = setup
            player_id = 100
            enemy_id = 200
            spot_id = 1
            
            # 準備: プレイヤー(5,5), 敵(15,5) -> 距離 10 (境界値)
            pmap = _create_sample_map(spot_id)
            actor = _create_sample_actor(player_id, Coordinate(5, 5, 0), DirectionEnum.NORTH)
            enemy = _create_sample_actor(enemy_id, Coordinate(15, 5, 0), DirectionEnum.SOUTH)
            pmap.add_object(actor)
            pmap.add_object(enemy)
            map_repo.save(pmap)
            
            player_repo.save(_sample_status(player_id))
            
            # プロジェクタイルスキルを使用
            skill = _sample_skill(1)
            skill = SkillSpec(
                skill_id=skill.skill_id, name=skill.name, element=skill.element,
                deck_cost=skill.deck_cost, cast_lock_ticks=skill.cast_lock_ticks,
                cooldown_ticks=skill.cooldown_ticks, power_multiplier=skill.power_multiplier,
                hit_pattern=SkillHitPattern.projectile(HitBoxShape.single_cell(), HitBoxVelocity(0, 1), 5)
            )
            spec_repo.save(skill)
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), player_id, 10, 10)
            loadout.equip_skill(DeckTier.NORMAL, 0, skill)
            loadout_repo.save(loadout)

            # 実行: 距離10の敵をオートエイム
            service.use_player_skill(UsePlayerSkillCommand(player_id, 1, 0, 0, spot_id=spot_id, auto_aim=True))

            # 検証: EAST(1,0)方向にエイムされている
            hitboxes = hitbox_repo.find_active_by_spot_id(SpotId(spot_id))
            assert hitboxes[0].velocity.dx == 1.0

        def test_use_skill_auto_aim_out_of_range(self, setup):
            service, loadout_repo, spec_repo, _, player_repo, map_repo, hitbox_repo, _ = setup
            player_id = 100
            enemy_id = 200
            spot_id = 1
            
            # 準備: プレイヤー(5,5,NORTH), 敵(16,5) -> 距離 11 (範囲外)
            pmap = _create_sample_map(spot_id)
            actor = _create_sample_actor(player_id, Coordinate(5, 5, 0), DirectionEnum.NORTH)
            enemy = _create_sample_actor(enemy_id, Coordinate(16, 5, 0), DirectionEnum.SOUTH)
            pmap.add_object(actor)
            pmap.add_object(enemy)
            map_repo.save(pmap)
            
            player_repo.save(_sample_status(player_id))
            
            # プロジェクタイルスキルを使用
            skill = _sample_skill(1)
            skill = SkillSpec(
                skill_id=skill.skill_id, name=skill.name, element=skill.element,
                deck_cost=skill.deck_cost, cast_lock_ticks=skill.cast_lock_ticks,
                cooldown_ticks=skill.cooldown_ticks, power_multiplier=skill.power_multiplier,
                hit_pattern=SkillHitPattern.projectile(HitBoxShape.single_cell(), HitBoxVelocity(0, 1), 5)
            )
            spec_repo.save(skill)
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), player_id, 10, 10)
            loadout.equip_skill(DeckTier.NORMAL, 0, skill)
            loadout_repo.save(loadout)

            # 実行: 距離11の敵は無視され、現在の向き(NORTH)を使用
            service.use_player_skill(UsePlayerSkillCommand(player_id, 1, 0, 0, spot_id=spot_id, auto_aim=True))

            # 検証: NORTH(0,-1)方向にエイムされている
            hitboxes = hitbox_repo.find_active_by_spot_id(SpotId(spot_id))
            assert hitboxes[0].velocity.dy == -1.0

    class TestAcceptSkillProposal:
        def test_accept_proposal_updates_loadout(self, setup):
            service, loadout_repo, spec_repo, progress_repo, _, _, _, _ = setup
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(100), 100, 10, 10)
            loadout_repo.save(loadout)
            
            progress = SkillDeckProgressAggregate(SkillDeckProgressId(1), 100)
            proposal = SkillProposal(1, SkillProposalType.ADD, SkillId(2), deck_tier=DeckTier.NORMAL, target_slot_index=0)
            progress.register_proposals([proposal])
            progress_repo.save(progress)
            
            skill = _sample_skill(2)
            spec_repo.save(skill)

            service.accept_skill_proposal(AcceptSkillProposalCommand(1, 1))
            
            assert loadout_repo.find_by_id(SkillLoadoutId(100)).normal_deck.get_skill(0) == skill
            assert len(progress_repo.find_by_id(SkillDeckProgressId(1)).pending_proposals) == 0

    class TestActivatePlayerAwakenedMode:
        def test_activate_awakened_mode_success(self, setup):
            service, loadout_repo, _, _, player_repo, _, _, _ = setup
            player_id = 100
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), player_id, 10, 10)
            loadout_repo.save(loadout)
            player_repo.save(_sample_status(player_id))

            command = ActivatePlayerAwakenedModeCommand(
                player_id=player_id, loadout_id=1, current_tick=10, 
                duration_ticks=50, cooldown_reduction_rate=0.5,
                mp_cost=20, stamina_cost=30, hp_cost=0
            )
            service.activate_player_awakened_mode(command)

            assert player_repo.find_by_id(PlayerId(player_id)).mp.value == 80
            assert loadout_repo.find_by_id(SkillLoadoutId(1)).awaken_state.is_active is True

    class TestErrorHandling:
        def test_handle_domain_exception(self, setup):
            service, _, _, _, _, _, _, _ = setup
            with pytest.raises(SkillCommandException, match="skill loadout not found"):
                service.equip_player_skill(EquipPlayerSkillCommand(100, 999, DeckTier.NORMAL, 0, 1))

        def test_handle_unexpected_exception(self, setup):
            service, _, _, _, _, _, _, _ = setup
            from ai_rpg_world.application.skill.exceptions.base_exception import SkillSystemErrorException
            
            # command が None の場合に AttributeError 等が発生するはず
            # _execute_with_error_handling の外側で発生する可能性があるため、サービスメソッドを直接叩く
            with pytest.raises(Exception):
                service.equip_player_skill(None)
