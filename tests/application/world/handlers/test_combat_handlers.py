import pytest
import logging
from typing import Dict, List, Optional, Set
from unittest.mock import MagicMock, patch

from ai_rpg_world.application.world.handlers.hit_box_damage_handler import HitBoxDamageHandler
from ai_rpg_world.application.world.handlers.combat_aggro_handler import CombatAggroHandler
from ai_rpg_world.application.world.aggro_store import AggroStore
from ai_rpg_world.infrastructure.aggro.in_memory_aggro_store import InMemoryAggroStore
from ai_rpg_world.application.world.handlers.monster_death_reward_handler import MonsterDeathRewardHandler
from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    PlayerNotFoundException,
)
from ai_rpg_world.application.world.handlers.monster_spawned_map_placement_handler import (
    MonsterSpawnedMapPlacementHandler,
)
from ai_rpg_world.application.world.services.world_simulation_service import (
    WorldSimulationApplicationService,
)
from ai_rpg_world.domain.skill.service.skill_execution_service import SkillExecutionDomainService
from ai_rpg_world.domain.skill.service.skill_to_hitbox_service import SkillToHitBoxDomainService
from ai_rpg_world.domain.skill.service.skill_targeting_service import SkillTargetingDomainService
from ai_rpg_world.domain.combat.service.hit_box_factory import HitBoxFactory
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate
from ai_rpg_world.domain.combat.event.combat_events import HitBoxHitRecordedEvent
from ai_rpg_world.domain.combat.service.hit_box_collision_service import HitBoxCollisionDomainService
from ai_rpg_world.domain.combat.service.hit_box_config_service import DefaultHitBoxConfigService
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.combat.value_object.hit_box_velocity import HitBoxVelocity
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.event.monster_events import MonsterDiedEvent
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    AutonomousBehaviorComponent,
)
from ai_rpg_world.domain.world.enum.world_enum import (
    BehaviorStateEnum,
    DirectionEnum,
    ObjectTypeEnum,
)
from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.service.behavior_service import BehaviorService
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.service.weather_config_service import DefaultWeatherConfigService
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.aggro_memory_policy import AggroMemoryPolicy
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException
from ai_rpg_world.infrastructure.events.combat_event_handler_registry import CombatEventHandlerRegistry
from ai_rpg_world.infrastructure.events.map_interaction_event_handler_registry import MapInteractionEventHandlerRegistry
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_hit_box_repository import InMemoryHitBoxRepository
from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import (
    InMemoryMonsterAggregateRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_loot_table_repository import (
    InMemoryLootTableRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_item_spec_repository import (
    InMemoryItemSpecRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_weather_zone_repository import (
    InMemoryWeatherZoneRepository,
)
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import InMemoryGameTimeProvider
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import LootTableAggregate, LootEntry
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository


# --- Test Helpers ---

def _create_player_status(
    player_id: int,
    *,
    max_hp: int = 100,
    attack: int = 20,
    defense: int = 10,
    critical_rate: float = 0.0,
    evasion_rate: float = 0.0,
) -> PlayerStatusAggregate:
    base_stats = BaseStats(
        max_hp=max_hp,
        max_mp=100,
        attack=attack,
        defense=defense,
        speed=10,
        critical_rate=critical_rate,
        evasion_rate=evasion_rate,
    )
    return PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=base_stats,
        stat_growth_factor=StatGrowthFactor.for_level(1),
        exp_table=ExpTable(100, 2.0),
        growth=Growth(1, 0, ExpTable(100, 2.0)),
        gold=Gold(0),
        hp=Hp.create(max_hp, max_hp),
        mp=Mp.create(100, 100),
        stamina=Stamina.create(100, 100),
    )


def _create_monster(monster_id: int, world_object_id: int, coordinate: Coordinate, max_hp: int = 120, attack: int = 15, loot_table_id: str = None) -> MonsterAggregate:
    template = MonsterTemplate(
        template_id=MonsterTemplateId(monster_id),
        name=f"monster-{monster_id}",
        base_stats=BaseStats(
            max_hp=max_hp,
            max_mp=20,
            attack=attack,
            defense=8,
            speed=8,
            critical_rate=0.0,
            evasion_rate=0.0,
        ),
        reward_info=RewardInfo(exp=10, gold=5, loot_table_id=loot_table_id),
        respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True),
        race=Race.BEAST,
        faction=MonsterFactionEnum.ENEMY,
        description="test monster",
    )
    loadout = SkillLoadoutAggregate.create(
        SkillLoadoutId(monster_id + 1000),
        owner_id=world_object_id,
        normal_capacity=10,
        awakened_capacity=10,
    )
    monster = MonsterAggregate.create(
        monster_id=MonsterId(monster_id),
        template=template,
        world_object_id=WorldObjectId(world_object_id),
        skill_loadout=loadout,
    )
    monster.clear_events()
    monster.spawn(coordinate, SpotId(1), WorldTick(0))
    monster.clear_events()
    return monster


def _create_actor_object(world_object_id: int, coordinate: Coordinate, player_id: int | None = None) -> WorldObject:
    component = ActorComponent(
        direction=DirectionEnum.SOUTH,
        player_id=PlayerId(player_id) if player_id is not None else None,
    )
    object_type = ObjectTypeEnum.PLAYER if player_id is not None else ObjectTypeEnum.NPC
    return WorldObject(
        object_id=WorldObjectId(world_object_id),
        coordinate=coordinate,
        object_type=object_type,
        component=component,
    )


def _create_map(spot_id: int = 1) -> PhysicalMapAggregate:
    tiles = [Tile(Coordinate(x, y, 0), TerrainType.grass()) for x in range(5) for y in range(5)]
    return PhysicalMapAggregate.create(SpotId(spot_id), tiles)


class FakeItemRepository(ItemRepository):
    def __init__(self):
        self.aggregates = {}
        self._next_id = 1
    def generate_item_instance_id(self) -> ItemInstanceId:
        res = ItemInstanceId(self._next_id)
        self._next_id += 1
        return res
    def save(self, aggregate):
        self.aggregates[aggregate.item_instance_id] = aggregate
        return aggregate
    def find_by_id(self, id): return self.aggregates.get(id)
    def find_all(self): return list(self.aggregates.values())
    def find_by_ids(self, ids): return [self.aggregates[i] for i in ids if i in self.aggregates]
    def delete(self, id): 
        if id in self.aggregates: del self.aggregates[id]; return True
        return False
    def find_by_spec_id(self, spec_id): return []
    def find_by_type(self, type): return []
    def find_by_rarity(self, rarity): return []
    def find_broken_items(self): return []
    def find_tradeable_items(self): return []
    def find_by_owner_id(self, owner_id): return []


# --- Test Classes ---

class TestHitBoxDamageHandler:
    @pytest.fixture
    def setup(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)
        uow, _ = InMemoryUnitOfWork.create_with_event_publisher(unit_of_work_factory=create_uow, data_store=data_store)
        
        time_provider = InMemoryGameTimeProvider(initial_tick=10)
        map_repo = InMemoryPhysicalMapRepository(data_store, uow)
        player_repo = InMemoryPlayerStatusRepository(data_store, uow)
        monster_repo = InMemoryMonsterAggregateRepository(data_store, uow)
        hit_box_repo = InMemoryHitBoxRepository(data_store, uow)
        
        handler = HitBoxDamageHandler(
            hit_box_repository=hit_box_repo,
            physical_map_repository=map_repo,
            player_status_repository=player_repo,
            monster_repository=monster_repo,
            time_provider=time_provider,
            unit_of_work=uow,
        )
        return locals()

    def _create_hit_box(self, hit_box_repo, owner_id, stats=None):
        hb_id = HitBoxId.create(1)
        hb = HitBoxAggregate.create(
            hit_box_id=hb_id,
            spot_id=SpotId(1),
            owner_id=owner_id,
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(1, 1, 0),
            start_tick=WorldTick(10),
            duration=5,
            power_multiplier=1.0,
            velocity=HitBoxVelocity.zero(),
            attacker_stats=stats
        )
        hit_box_repo.save(hb)
        return hb

    def test_apply_damage_with_snapshot_stats(self, setup):
        # Given
        s = setup
        pmap = _create_map()
        pmap.add_object(_create_actor_object(100, Coordinate(0, 1, 0), player_id=100))
        pmap.add_object(_create_actor_object(200, Coordinate(1, 1, 0), player_id=200))
        s["map_repo"].save(pmap)

        # アタッカーのステータススナップショット (攻撃力 50)
        attacker_stats = BaseStats(100, 100, 50, 10, 10, 0, 0)
        hb = self._create_hit_box(s["hit_box_repo"], WorldObjectId(100), attacker_stats)
        
        # 実際のプレイヤーのステータスは攻撃力 10 (スナップショットが優先されるはず)
        s["player_repo"].save(_create_player_status(100, attack=10))
        # ディフェンダー (防御力 10)
        s["player_repo"].save(_create_player_status(200, defense=10))

        event = HitBoxHitRecordedEvent.create(
            aggregate_id=hb.hit_box_id,
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId(100),
            target_id=WorldObjectId(200),
            hit_coordinate=Coordinate(1, 1, 0),
        )

        # When
        with s["uow"]:
            s["handler"].handle(event)

        # Then
        target = s["player_repo"].find_by_id(PlayerId(200))
        # ダメージ = 50 - (10 / 2) = 45. 100 - 45 = 55
        assert target.hp.value == 55

    def test_apply_damage_filters_expired_buffs(self, setup):
        # Given
        s = setup
        pmap = _create_map()
        pmap.add_object(_create_actor_object(100, Coordinate(0, 1, 0), player_id=100))
        pmap.add_object(_create_actor_object(200, Coordinate(1, 1, 0), player_id=200))
        s["map_repo"].save(pmap)

        # ディフェンダーに期限切れの防御バフを付与
        defender = _create_player_status(200, defense=10)
        # Tick 5 で切れるバフを付与 (現在は Tick 10)
        defender.add_status_effect(StatusEffect(StatusEffectType.DEFENSE_UP, 10.0, WorldTick(5)))
        s["player_repo"].save(defender)

        # アタッカー (攻撃力 20)
        attacker_stats = BaseStats(100, 100, 20, 10, 10, 0, 0)
        hb = self._create_hit_box(s["hit_box_repo"], WorldObjectId(100), attacker_stats)

        event = HitBoxHitRecordedEvent.create(
            aggregate_id=hb.hit_box_id,
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId(100),
            target_id=WorldObjectId(200),
            hit_coordinate=Coordinate(1, 1, 0),
        )

        # When
        with s["uow"]:
            s["handler"].handle(event)

        # Then
        target = s["player_repo"].find_by_id(PlayerId(200))
        # 防御バフが効いていればダメージは 0 になるはずだが、期限切れなので 20 - (10/2) = 15 入る
        assert target.hp.value == 85
        assert len(target._active_effects) == 0 # クリーンアップされていること

    def test_monster_hp_synced_to_map_component(self, setup):
        """モンスターにダメージ適用後、同一マップ上の AutonomousBehaviorComponent.hp_percentage が同期されること"""
        s = setup
        pmap = _create_map()
        # プレイヤー（攻撃者）
        pmap.add_object(_create_actor_object(100, Coordinate(0, 1, 0), player_id=100))
        s["player_repo"].save(_create_player_status(100, attack=50))
        # モンスター（被弾者）: マップ上には AutonomousBehaviorComponent を持つ NPC として配置
        monster_world_object_id = WorldObjectId(300)
        monster_comp = AutonomousBehaviorComponent(hp_percentage=1.0)
        monster_obj = WorldObject(
            monster_world_object_id,
            Coordinate(1, 1, 0),
            ObjectTypeEnum.NPC,
            component=monster_comp,
        )
        pmap.add_object(monster_obj)
        s["map_repo"].save(pmap)

        monster = _create_monster(1, 300, Coordinate(1, 1, 0), max_hp=100, attack=5)
        s["monster_repo"].save(monster)

        attacker_stats = BaseStats(100, 100, 50, 10, 10, 0, 0)
        hb = self._create_hit_box(s["hit_box_repo"], WorldObjectId(100), attacker_stats)
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=hb.hit_box_id,
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId(100),
            target_id=monster_world_object_id,
            hit_coordinate=Coordinate(1, 1, 0),
        )

        with s["uow"]:
            s["handler"].handle(event)

        # 集約の HP が減っていること (50 - 8/2 = 46 ダメージ → 100 - 46 = 54)
        updated_monster = s["monster_repo"].find_by_world_object_id(monster_world_object_id)
        assert updated_monster.hp.value == 54
        # マップ上のコンポーネントの hp_percentage が同期されていること
        updated_map = s["map_repo"].find_by_spot_id(SpotId(1))
        target_obj = updated_map.get_object(monster_world_object_id)
        assert isinstance(target_obj.component, AutonomousBehaviorComponent)
        assert target_obj.component.hp_percentage == pytest.approx(0.54, rel=1e-5)

    def test_skip_damage_when_target_already_dead(self, setup):
        # Given
        s = setup
        pmap = _create_map()
        pmap.add_object(_create_actor_object(100, Coordinate(0, 1, 0), player_id=100))
        pmap.add_object(_create_actor_object(300, Coordinate(1, 1, 0), player_id=None))
        s["map_repo"].save(pmap)

        monster = _create_monster(1, 300, Coordinate(1, 1, 0))
        monster.apply_damage(999, WorldTick(10)) # 殺しておく
        s["monster_repo"].save(monster)

        hb = self._create_hit_box(s["hit_box_repo"], WorldObjectId(100), BaseStats(100, 100, 10, 10, 10, 0, 0))
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=hb.hit_box_id,
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId(100),
            target_id=WorldObjectId(300),
            hit_coordinate=Coordinate(1, 1, 0)
        )

        # When
        with s["uow"]:
            s["handler"].handle(event)

        # Then
        # 例外が発生せずに正常終了することを確認
        assert True

    def test_handle_hit_box_not_found(self, setup):
        # Given
        s = setup
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=HitBoxId.create(999), # 存在しないID
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId(100),
            target_id=WorldObjectId(200),
            hit_coordinate=Coordinate(1, 1, 0)
        )

        # When
        with s["uow"]:
            s["handler"].handle(event) # エラーにならずに終了することを確認

        # Then
        assert True

    def test_handle_map_not_found(self, setup):
        # Given
        s = setup
        hb = self._create_hit_box(s["hit_box_repo"], WorldObjectId(100))
        # マップを削除しておく（インメモリなのでクリア）
        s["data_store"].physical_maps.clear()

        event = HitBoxHitRecordedEvent.create(
            aggregate_id=hb.hit_box_id,
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId(100),
            target_id=WorldObjectId(200),
            hit_coordinate=Coordinate(1, 1, 0)
        )

        # When
        with s["uow"]:
            s["handler"].handle(event)

        # Then
        assert True

    def test_handle_defender_disappeared(self, setup):
        # Given
        s = setup
        pmap = _create_map()
        pmap.add_object(_create_actor_object(100, Coordinate(0, 1, 0), player_id=100))
        # ディフェンダーを配置しない
        s["map_repo"].save(pmap)

        hb = self._create_hit_box(s["hit_box_repo"], WorldObjectId(100))
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=hb.hit_box_id,
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId(100),
            target_id=WorldObjectId(200), # 存在しない
            hit_coordinate=Coordinate(1, 1, 0)
        )

        # When
        with s["uow"]:
            s["handler"].handle(event)

        # Then
        assert True


class TestCombatAggroHandler:
    @pytest.fixture
    def setup(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)
        uow, _ = InMemoryUnitOfWork.create_with_event_publisher(create_uow, data_store)
        
        map_repo = InMemoryPhysicalMapRepository(data_store, uow)
        hit_box_repo = InMemoryHitBoxRepository(data_store, uow)
        handler = CombatAggroHandler(hit_box_repo, map_repo, uow)
        return locals()

    def test_aggro_skipped_when_attacker_not_actor(self, setup):
        # Given
        s = setup
        pmap = _create_map()
        # アタッカーは単なるオブジェクト（設置物など）
        attacker_obj = WorldObject(WorldObjectId(500), Coordinate(0, 0, 0), ObjectTypeEnum.SIGN)
        # ターゲットは自律モンスター
        monster_obj = WorldObject(
            WorldObjectId(300), Coordinate(1, 1, 0), ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(state=BehaviorStateEnum.IDLE)
        )
        pmap.add_object(attacker_obj)
        pmap.add_object(monster_obj)
        s["map_repo"].save(pmap)

        hb = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(1),
            spot_id=SpotId(1),
            owner_id=WorldObjectId(500),
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0,0,0),
            start_tick=WorldTick(10),
            duration=5
        )
        s["hit_box_repo"].save(hb)

        event = HitBoxHitRecordedEvent.create(
            aggregate_id=hb.hit_box_id,
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId(500),
            target_id=WorldObjectId(300),
            hit_coordinate=Coordinate(1, 1, 0)
        )

        # When
        with s["uow"]:
            s["handler"].handle(event)

        # Then
        updated_map = s["map_repo"].find_by_spot_id(SpotId(1))
        target = updated_map.get_object(WorldObjectId(300))
        assert target.component.target_id is None # ターゲットが設定されていないこと

    def test_aggro_skipped_when_target_not_actor(self, setup):
        # Given
        s = setup
        pmap = _create_map()
        # アタッカーはプレイヤー
        attacker_obj = _create_actor_object(100, Coordinate(0, 0, 0), player_id=100)
        # ターゲットはアクターでないオブジェクト（チェスト）
        target_obj = WorldObject(WorldObjectId(200), Coordinate(1, 1, 0), ObjectTypeEnum.CHEST)
        pmap.add_object(attacker_obj)
        pmap.add_object(target_obj)
        s["map_repo"].save(pmap)

        hb = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(1),
            spot_id=SpotId(1),
            owner_id=WorldObjectId(100),
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0,0,0),
            start_tick=WorldTick(10),
            duration=5
        )
        s["hit_box_repo"].save(hb)

        event = HitBoxHitRecordedEvent.create(
            aggregate_id=hb.hit_box_id,
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId(100),
            target_id=WorldObjectId(200),
            hit_coordinate=Coordinate(1, 1, 0)
        )

        # When
        with s["uow"]:
            s["handler"].handle(event)

        # Then
        # エラーにならずに終了することを確認
        assert True

    def test_aggro_store_receives_aggro_when_target_is_autonomous(self, setup):
        # Given: アタッカーと被弾者ともにアクター、被弾者は AutonomousBehaviorComponent、aggro_store を注入
        s = setup
        aggro_store = InMemoryAggroStore()
        handler = CombatAggroHandler(
            s["hit_box_repo"], s["map_repo"], s["uow"], aggro_store=aggro_store
        )
        pmap = _create_map()
        attacker_id = WorldObjectId(100)
        target_id = WorldObjectId(300)
        attacker_obj = _create_actor_object(100, Coordinate(0, 0, 0), player_id=100)
        monster_obj = WorldObject(
            target_id, Coordinate(1, 1, 0), ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(state=BehaviorStateEnum.IDLE),
        )
        pmap.add_object(attacker_obj)
        pmap.add_object(monster_obj)
        s["map_repo"].save(pmap)

        hb = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(1),
            spot_id=SpotId(1),
            owner_id=attacker_id,
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=WorldTick(10),
            duration=5,
        )
        s["hit_box_repo"].save(hb)

        event = HitBoxHitRecordedEvent.create(
            aggregate_id=hb.hit_box_id,
            aggregate_type="HitBoxAggregate",
            owner_id=attacker_id,
            target_id=target_id,
            hit_coordinate=Coordinate(1, 1, 0),
        )

        # When
        with s["uow"]:
            handler.handle(event)

        # Then: 被弾者側のコンポーネントに spot_target が呼ばれ、aggro_store にヘイトが加算されている
        updated_map = s["map_repo"].find_by_spot_id(SpotId(1))
        target = updated_map.get_object(target_id)
        assert target.component.target_id == attacker_id
        threat = aggro_store.get_threat_by_attacker(SpotId(1), attacker_id)
        assert threat == {target_id: 1}

    def test_aggro_stored_with_current_tick_when_game_time_provider_injected(self, setup):
        """game_time_provider を注入した場合、add_aggro にその時点の tick が渡され last_seen_tick として記録されること"""
        s = setup
        aggro_store = InMemoryAggroStore()
        time_provider = InMemoryGameTimeProvider(initial_tick=50)
        handler = CombatAggroHandler(
            s["hit_box_repo"], s["map_repo"], s["uow"],
            aggro_store=aggro_store,
            game_time_provider=time_provider,
        )
        pmap = _create_map()
        attacker_id = WorldObjectId(100)
        target_id = WorldObjectId(300)
        pmap.add_object(_create_actor_object(100, Coordinate(0, 0, 0), player_id=100))
        pmap.add_object(WorldObject(
            target_id, Coordinate(1, 1, 0), ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(state=BehaviorStateEnum.IDLE),
        ))
        s["map_repo"].save(pmap)
        hb = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(1),
            spot_id=SpotId(1),
            owner_id=attacker_id,
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=WorldTick(10),
            duration=5,
        )
        s["hit_box_repo"].save(hb)
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=hb.hit_box_id,
            aggregate_type="HitBoxAggregate",
            owner_id=attacker_id,
            target_id=target_id,
            hit_coordinate=Coordinate(1, 1, 0),
        )
        with s["uow"]:
            handler.handle(event)
        policy = AggroMemoryPolicy(forget_after_ticks=10)
        threat_within = aggro_store.get_threat_by_attacker(
            SpotId(1), attacker_id, current_tick=59, memory_policy=policy
        )
        threat_after = aggro_store.get_threat_by_attacker(
            SpotId(1), attacker_id, current_tick=61, memory_policy=policy
        )
        assert threat_within == {target_id: 1}
        assert threat_after == {}

    def test_aggro_store_not_called_when_aggro_store_none(self, setup):
        # Given: aggro_store なしでハンドラを構築
        s = setup
        pmap = _create_map()
        attacker_obj = _create_actor_object(100, Coordinate(0, 0, 0), player_id=100)
        monster_obj = WorldObject(
            WorldObjectId(300), Coordinate(1, 1, 0), ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(state=BehaviorStateEnum.IDLE),
        )
        pmap.add_object(attacker_obj)
        pmap.add_object(monster_obj)
        s["map_repo"].save(pmap)

        hb = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(1),
            spot_id=SpotId(1),
            owner_id=WorldObjectId(100),
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=WorldTick(10),
            duration=5,
        )
        s["hit_box_repo"].save(hb)
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=hb.hit_box_id,
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId(100),
            target_id=WorldObjectId(300),
            hit_coordinate=Coordinate(1, 1, 0),
        )

        # When: aggro_store なしのハンドラで handle
        with s["uow"]:
            s["handler"].handle(event)

        # Then: エラーにならず、spot_target は反映されている（既存の test と同様）
        updated_map = s["map_repo"].find_by_spot_id(SpotId(1))
        target = updated_map.get_object(WorldObjectId(300))
        assert target.component.target_id == WorldObjectId(100)

    def test_handle_hit_box_not_found(self, setup):
        """HitBox が存在しないイベントの場合は例外を出さずに return する"""
        s = setup
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=HitBoxId.create(999),
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId(100),
            target_id=WorldObjectId(200),
            hit_coordinate=Coordinate(1, 1, 0),
        )
        with s["uow"]:
            s["handler"].handle(event)
        assert True

    def test_handle_map_not_found(self, setup):
        """HitBox の spot_id に対応するマップが存在しない場合は例外を出さずに return する"""
        s = setup
        hb = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(1),
            spot_id=SpotId(1),
            owner_id=WorldObjectId(100),
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=WorldTick(10),
            duration=5,
        )
        s["hit_box_repo"].save(hb)
        s["data_store"].physical_maps.clear()
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=hb.hit_box_id,
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId(100),
            target_id=WorldObjectId(200),
            hit_coordinate=Coordinate(1, 1, 0),
        )
        with s["uow"]:
            s["handler"].handle(event)
        assert True

    def test_handle_combatant_disappeared(self, setup):
        """Owner または Target がマップに存在しない（ObjectNotFoundException）場合は例外を出さずに return する"""
        s = setup
        pmap = _create_map()
        pmap.add_object(_create_actor_object(100, Coordinate(0, 0, 0), player_id=100))
        s["map_repo"].save(pmap)
        hb = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(1),
            spot_id=SpotId(1),
            owner_id=WorldObjectId(100),
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=WorldTick(10),
            duration=5,
        )
        s["hit_box_repo"].save(hb)
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=hb.hit_box_id,
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId(100),
            target_id=WorldObjectId(200),
            hit_coordinate=Coordinate(1, 1, 0),
        )
        with s["uow"]:
            s["handler"].handle(event)
        assert True

    def test_handle_unexpected_exception_raises_system_error_exception(self, setup):
        """想定外の例外が _handle_impl 内で発生した場合、handle() は SystemErrorException を送出する"""
        s = setup
        pmap = _create_map()
        pmap.add_object(_create_actor_object(100, Coordinate(0, 0, 0), player_id=100))
        pmap.add_object(
            WorldObject(
                WorldObjectId(300),
                Coordinate(1, 1, 0),
                ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(state=BehaviorStateEnum.IDLE),
            )
        )
        s["map_repo"].save(pmap)
        hb = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(1),
            spot_id=SpotId(1),
            owner_id=WorldObjectId(100),
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=WorldTick(10),
            duration=5,
        )
        s["hit_box_repo"].save(hb)
        event = HitBoxHitRecordedEvent.create(
            aggregate_id=hb.hit_box_id,
            aggregate_type="HitBoxAggregate",
            owner_id=WorldObjectId(100),
            target_id=WorldObjectId(300),
            hit_coordinate=Coordinate(1, 1, 0),
        )
        with patch.object(
            s["map_repo"],
            "find_by_spot_id",
            side_effect=RuntimeError("unexpected repo error"),
        ):
            with pytest.raises(SystemErrorException) as excinfo:
                with s["uow"]:
                    s["handler"].handle(event)
        assert "Combat aggro handling failed" in str(excinfo.value)
        assert excinfo.value.original_exception is not None
        assert isinstance(excinfo.value.original_exception, RuntimeError)


class TestMonsterDeathRewardHandler:
    @pytest.fixture
    def setup(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)
        uow, _ = InMemoryUnitOfWork.create_with_event_publisher(create_uow, data_store)
        
        player_repo = InMemoryPlayerStatusRepository(data_store, uow)
        inventory_repo = InMemoryPlayerInventoryRepository(data_store, uow)
        loot_repo = InMemoryLootTableRepository()
        item_spec_repo = InMemoryItemSpecRepository()
        item_repo = FakeItemRepository()
        
        handler = MonsterDeathRewardHandler(
            player_status_repository=player_repo,
            player_inventory_repository=inventory_repo,
            loot_table_repository=loot_repo,
            item_spec_repository=item_spec_repo,
            item_repository=item_repo,
            unit_of_work=uow,
        )
        return locals()

    def test_grant_rewards_and_loot(self, setup):
        # Given
        s = setup
        player_id = PlayerId(100)
        s["player_repo"].save(_create_player_status(100))
        s["inventory_repo"].save(PlayerInventoryAggregate.create_new_inventory(player_id))

        # ドロップテーブルの設定 (100%で鉄の剣が出る)
        spec = s["item_spec_repo"].find_by_id(ItemSpecId(1)) # 鉄の剣
        loot_table = LootTableAggregate.create("test_table", [LootEntry(spec.item_spec_id, 100, 1, 1)])
        s["loot_repo"].save(loot_table)

        event = MonsterDiedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            respawn_tick=100,
            exp=50,
            gold=20,
            loot_table_id="test_table",
            killer_player_id=player_id
        )

        # When
        with s["uow"]:
            s["handler"].handle(event)

        # Then
        # 経験値とゴールド
        status = s["player_repo"].find_by_id(player_id)
        assert status.growth.total_exp == 50
        assert status.gold.value == 20

        # アイテム入手
        inv = s["inventory_repo"].find_by_id(player_id)
        # スロット0に何か入っているはず
        item_id = inv.get_item_instance_id_by_slot(SlotId(0))
        assert item_id is not None
        
        instance = s["item_repo"].find_by_id(item_id)
        assert instance.item_spec.item_spec_id == spec.item_spec_id

    def test_skip_rewards_when_no_killer(self, setup):
        # Given
        s = setup
        event = MonsterDiedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            respawn_tick=100,
            exp=50,
            gold=20,
            loot_table_id="table",
            killer_player_id=None
        )

        # When
        with s["uow"]:
            s["handler"].handle(event)

        # Then
        # エラーにならずに終了することを確認
        assert True

    def test_handle_player_status_not_found(self, setup):
        """キラーのプレイヤー状態が存在しない場合は PlayerNotFoundException を投げること"""
        s = setup
        player_id = PlayerId(100)
        event = MonsterDiedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            respawn_tick=100,
            exp=50,
            gold=20,
            loot_table_id="table",
            killer_player_id=player_id,
        )

        with pytest.raises(PlayerNotFoundException):
            with s["uow"]:
                s["handler"].handle(event)

    def test_handle_loot_table_not_found(self, setup):
        """存在しないドロップテーブル指定時は ApplicationException を投げること"""
        s = setup
        player_id = PlayerId(100)
        s["player_repo"].save(_create_player_status(100))
        s["inventory_repo"].save(PlayerInventoryAggregate.create_new_inventory(player_id))
        event = MonsterDiedEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            respawn_tick=100,
            exp=50,
            gold=20,
            loot_table_id="missing_table",
            killer_player_id=player_id,
        )

        with pytest.raises(ApplicationException) as excinfo:
            with s["uow"]:
                s["handler"].handle(event)
        assert "missing_table" in str(excinfo.value) or "LootTable" in str(excinfo.value)


class TestMonsterDecidedToMoveHandler:
    """MonsterDecidedToMoveHandler の単体テスト（正常・異常）"""

    @pytest.fixture
    def handler_deps(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()
        uow = InMemoryUnitOfWork(unit_of_work_factory=lambda: None, data_store=data_store)
        map_repo = InMemoryPhysicalMapRepository(data_store, uow)
        monster_repo = InMemoryMonsterAggregateRepository(data_store, uow)
        from ai_rpg_world.application.world.handlers.monster_decided_to_move_handler import (
            MonsterDecidedToMoveHandler,
        )
        handler = MonsterDecidedToMoveHandler(
            physical_map_repository=map_repo,
            monster_repository=monster_repo,
        )
        return {"handler": handler, "map_repo": map_repo, "monster_repo": monster_repo, "uow": uow}

    def test_handle_move_success(self, handler_deps):
        """イベント処理で move_object が呼ばれオブジェクトが移動すること"""
        from ai_rpg_world.domain.monster.event.monster_events import MonsterDecidedToMoveEvent
        s = handler_deps
        tiles = [Tile(Coordinate(x, y, 0), TerrainType.grass()) for x in range(5) for y in range(5)]
        pmap = PhysicalMapAggregate.create(SpotId(1), tiles)
        actor = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.NPC,
            component=ActorComponent(),
        )
        pmap.add_object(actor)
        s["map_repo"].save(pmap)
        event = MonsterDecidedToMoveEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            actor_id=WorldObjectId(1),
            coordinate={"x": 1, "y": 0, "z": 0},
            spot_id=SpotId(1),
            current_tick=WorldTick(10),
        )
        with s["uow"]:
            s["handler"].handle(event)
        loaded = s["map_repo"].find_by_spot_id(SpotId(1))
        obj = loaded.get_object(WorldObjectId(1))
        assert obj.coordinate == Coordinate(1, 0, 0)

    def test_handle_map_not_found_skips(self, handler_deps):
        """マップが存在しない場合は移動せずスキップすること（例外にしない）"""
        from ai_rpg_world.domain.monster.event.monster_events import MonsterDecidedToMoveEvent
        s = handler_deps
        event = MonsterDecidedToMoveEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            actor_id=WorldObjectId(1),
            coordinate={"x": 1, "y": 0, "z": 0},
            spot_id=SpotId(999),
            current_tick=WorldTick(10),
        )
        with s["uow"]:
            s["handler"].handle(event)
        assert s["map_repo"].find_by_spot_id(SpotId(999)) is None

    def test_handle_domain_exception_skips(self, handler_deps):
        """move_object がドメイン例外を投げた場合はログのみでスキップすること"""
        from ai_rpg_world.domain.monster.event.monster_events import MonsterDecidedToMoveEvent
        from ai_rpg_world.domain.world.exception.map_exception import InvalidMovementException
        s = handler_deps
        tiles = [Tile(Coordinate(x, y, 0), TerrainType.grass()) for x in range(5) for y in range(5)]
        pmap = PhysicalMapAggregate.create(SpotId(1), tiles)
        actor = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.NPC,
            component=ActorComponent(),
        )
        pmap.add_object(actor)
        s["map_repo"].save(pmap)
        event = MonsterDecidedToMoveEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            actor_id=WorldObjectId(1),
            coordinate={"x": 1, "y": 0, "z": 0},
            spot_id=SpotId(1),
            current_tick=WorldTick(10),
        )
        with patch.object(pmap, "move_object", side_effect=InvalidMovementException("blocked")):
            with patch.object(s["map_repo"], "find_by_spot_id", return_value=pmap):
                with s["uow"]:
                    s["handler"].handle(event)
        loaded = s["map_repo"].find_by_spot_id(SpotId(1))
        obj = loaded.get_object(WorldObjectId(1))
        assert obj.coordinate == Coordinate(0, 0, 0)


class TestMonsterDecidedToUseSkillHandler:
    """MonsterDecidedToUseSkillHandler の単体テスト（正常・異常）"""

    @pytest.fixture
    def handler_deps(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()
        uow = InMemoryUnitOfWork(unit_of_work_factory=lambda: None, data_store=data_store)
        map_repo = InMemoryPhysicalMapRepository(data_store, uow)
        monster_repo = InMemoryMonsterAggregateRepository(data_store, uow)
        hit_box_repo = InMemoryHitBoxRepository(data_store, uow)
        skill_loadout_repo = MagicMock()
        from ai_rpg_world.domain.monster.service.monster_skill_execution_domain_service import (
            MonsterSkillExecutionDomainService,
        )
        from ai_rpg_world.domain.skill.service.skill_execution_service import SkillExecutionDomainService
        from ai_rpg_world.domain.skill.service.skill_targeting_service import SkillTargetingDomainService
        from ai_rpg_world.domain.skill.service.skill_to_hitbox_service import SkillToHitBoxDomainService
        skill_exec = SkillExecutionDomainService(
            SkillTargetingDomainService(),
            SkillToHitBoxDomainService(),
        )
        monster_skill_exec = MonsterSkillExecutionDomainService(skill_exec)
        from ai_rpg_world.application.world.handlers.monster_decided_to_use_skill_handler import (
            MonsterDecidedToUseSkillHandler,
        )
        handler = MonsterDecidedToUseSkillHandler(
            physical_map_repository=map_repo,
            monster_repository=monster_repo,
            monster_skill_execution_domain_service=monster_skill_exec,
            hit_box_factory=HitBoxFactory(),
            hit_box_repository=hit_box_repo,
            skill_loadout_repository=skill_loadout_repo,
        )
        return {
            "handler": handler,
            "map_repo": map_repo,
            "monster_repo": monster_repo,
            "uow": uow,
        }

    def test_handle_map_not_found_skips(self, handler_deps):
        """マップが存在しない場合はスキル実行せずスキップすること"""
        from ai_rpg_world.domain.monster.event.monster_events import MonsterDecidedToUseSkillEvent
        s = handler_deps
        event = MonsterDecidedToUseSkillEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            actor_id=WorldObjectId(1),
            skill_slot_index=0,
            target_id=None,
            spot_id=SpotId(999),
            current_tick=WorldTick(10),
        )
        with s["uow"]:
            s["handler"].handle(event)

    def test_handle_monster_not_found_skips(self, handler_deps):
        """モンスターが存在しない場合はスキル実行せずスキップすること"""
        from ai_rpg_world.domain.monster.event.monster_events import MonsterDecidedToUseSkillEvent
        s = handler_deps
        tiles = [Tile(Coordinate(x, y, 0), TerrainType.grass()) for x in range(5) for y in range(5)]
        pmap = PhysicalMapAggregate.create(SpotId(1), tiles)
        s["map_repo"].save(pmap)
        event = MonsterDecidedToUseSkillEvent.create(
            aggregate_id=MonsterId(1),
            aggregate_type="MonsterAggregate",
            actor_id=WorldObjectId(999),
            skill_slot_index=0,
            target_id=None,
            spot_id=SpotId(1),
            current_tick=WorldTick(10),
        )
        with s["uow"]:
            s["handler"].handle(event)


class TestCombatIntegration:
    @pytest.fixture
    def setup_service(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()
        time_provider = InMemoryGameTimeProvider(initial_tick=10)

        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)

        uow, event_publisher = InMemoryUnitOfWork.create_with_event_publisher(create_uow, data_store)

        map_repo = InMemoryPhysicalMapRepository(data_store, uow)
        player_repo = InMemoryPlayerStatusRepository(data_store, uow)
        inventory_repo = InMemoryPlayerInventoryRepository(data_store, uow)
        monster_repo = InMemoryMonsterAggregateRepository(data_store, uow)
        hit_box_repo = InMemoryHitBoxRepository(data_store, uow)
        loot_repo = InMemoryLootTableRepository()
        item_spec_repo = InMemoryItemSpecRepository()
        item_repo = FakeItemRepository()
        weather_zone_repo = InMemoryWeatherZoneRepository(data_store, uow)

        damage_handler = HitBoxDamageHandler(hit_box_repo, map_repo, player_repo, monster_repo, time_provider, uow)
        aggro_handler = CombatAggroHandler(hit_box_repo, map_repo, uow)
        reward_handler = MonsterDeathRewardHandler(player_repo, inventory_repo, loot_repo, item_spec_repo, item_repo, uow)
        from ai_rpg_world.application.world.handlers.monster_death_hunger_handler import MonsterDeathHungerHandler
        from ai_rpg_world.application.world.handlers.monster_died_map_removal_handler import MonsterDiedMapRemovalHandler
        hunger_handler = MonsterDeathHungerHandler(map_repo, monster_repo, uow)
        map_removal_handler = MonsterDiedMapRemovalHandler(map_repo, monster_repo, uow)
        monster_spawned_map_placement_handler = MonsterSpawnedMapPlacementHandler(
            monster_repository=monster_repo,
            physical_map_repository=map_repo,
            unit_of_work=uow,
        )
        from ai_rpg_world.application.world.handlers.item_stored_in_chest_handler import ItemStoredInChestHandler
        from ai_rpg_world.application.world.handlers.item_taken_from_chest_handler import ItemTakenFromChestHandler
        from ai_rpg_world.application.world.handlers.monster_decided_to_move_handler import MonsterDecidedToMoveHandler
        from ai_rpg_world.application.world.handlers.monster_decided_to_use_skill_handler import MonsterDecidedToUseSkillHandler
        from ai_rpg_world.domain.monster.service.monster_skill_execution_domain_service import MonsterSkillExecutionDomainService
        from ai_rpg_world.domain.combat.service.hit_box_factory import HitBoxFactory
        from ai_rpg_world.domain.skill.service.skill_execution_service import SkillExecutionDomainService
        from ai_rpg_world.domain.skill.service.skill_targeting_service import SkillTargetingDomainService
        from ai_rpg_world.domain.skill.service.skill_to_hitbox_service import SkillToHitBoxDomainService

        item_stored_handler = ItemStoredInChestHandler(inventory_repo, uow)
        item_taken_handler = ItemTakenFromChestHandler(inventory_repo, uow)
        monster_decided_to_move_handler = MonsterDecidedToMoveHandler(
            physical_map_repository=map_repo,
            monster_repository=monster_repo,
        )
        skill_loadout_repo = MagicMock()
        skill_execution_service = SkillExecutionDomainService(
            SkillTargetingDomainService(),
            SkillToHitBoxDomainService(),
        )
        monster_skill_execution_domain_service = MonsterSkillExecutionDomainService(skill_execution_service)
        monster_decided_to_use_skill_handler = MonsterDecidedToUseSkillHandler(
            physical_map_repository=map_repo,
            monster_repository=monster_repo,
            monster_skill_execution_domain_service=monster_skill_execution_domain_service,
            hit_box_factory=HitBoxFactory(),
            hit_box_repository=hit_box_repo,
            skill_loadout_repository=skill_loadout_repo,
        )
        CombatEventHandlerRegistry(
            damage_handler,
            aggro_handler,
            reward_handler,
            hunger_handler,
            map_removal_handler,
            monster_spawned_map_placement_handler,
        ).register_handlers(event_publisher)
        from ai_rpg_world.infrastructure.events.monster_event_handler_registry import (
            MonsterEventHandlerRegistry,
        )
        MonsterEventHandlerRegistry(
            monster_decided_to_move_handler,
            monster_decided_to_use_skill_handler,
        ).register_handlers(event_publisher)
        MapInteractionEventHandlerRegistry(
            item_stored_in_chest_handler=item_stored_handler,
            item_taken_from_chest_handler=item_taken_handler,
        ).register_handlers(event_publisher)

        from ai_rpg_world.application.world.services.caching_pathfinding_service import CachingPathfindingService
        from ai_rpg_world.application.world.services.monster_action_resolver import create_monster_action_resolver_factory
        from ai_rpg_world.domain.world.service.skill_selection_policy import FirstInRangeSkillPolicy

        pathfinding_service = PathfindingService(None)
        caching_pathfinding = CachingPathfindingService(
            pathfinding_service,
            time_provider=time_provider,
            ttl_ticks=5,
        )
        monster_action_resolver_factory = create_monster_action_resolver_factory(
            caching_pathfinding,
            FirstInRangeSkillPolicy(),
        )
        behavior_service = BehaviorService(caching_pathfinding)
        service = WorldSimulationApplicationService(
            time_provider=time_provider,
            physical_map_repository=map_repo,
            weather_zone_repository=weather_zone_repo,
            player_status_repository=player_repo,
            hit_box_repository=hit_box_repo,
            behavior_service=behavior_service,
            weather_config_service=DefaultWeatherConfigService(1),
            unit_of_work=uow,
            monster_repository=monster_repo,
            skill_loadout_repository=skill_loadout_repo,
            monster_skill_execution_domain_service=monster_skill_execution_domain_service,
            hit_box_factory=HitBoxFactory(),
            hit_box_config_service=DefaultHitBoxConfigService(4),
            hit_box_collision_service=HitBoxCollisionDomainService(),
            monster_action_resolver_factory=monster_action_resolver_factory,
        )

        return locals()

    def test_full_combat_to_reward_flow(self, setup_service):
        # Given
        s = setup_service
        pmap = _create_map()
        player_obj = _create_actor_object(100, Coordinate(0, 0, 0), player_id=100)
        monster_obj = _create_actor_object(300, Coordinate(1, 0, 0), player_id=None)
        pmap.add_object(player_obj)
        pmap.add_object(monster_obj)
        s["map_repo"].save(pmap)

        player_id = PlayerId(100)
        s["player_repo"].save(_create_player_status(100, attack=500)) # 確定1パン
        s["inventory_repo"].save(PlayerInventoryAggregate.create_new_inventory(player_id))
        s["monster_repo"].save(_create_monster(1, 300, Coordinate(1, 0, 0)))

        # 攻撃者のステータスを込めてHitBox生成
        hb = HitBoxAggregate.create(
            HitBoxId.create(1), SpotId(1), WorldObjectId(100), HitBoxShape.single_cell(),
            Coordinate(0, 0, 0), WorldTick(10), 5, velocity=HitBoxVelocity(1, 0, 0),
            attacker_stats=s["player_repo"].find_by_id(player_id).get_effective_stats(WorldTick(10))
        )
        s["hit_box_repo"].save(hb)

        # When
        s["service"].tick() # Tick 11

        # Then
        # モンスター死亡確認
        monster = s["monster_repo"].find_by_id(MonsterId(1))
        assert monster.hp.value <= 0
        
        # 報酬確認
        player = s["player_repo"].find_by_id(player_id)
        assert player.growth.total_exp == 10
        assert player.gold.value == 5
