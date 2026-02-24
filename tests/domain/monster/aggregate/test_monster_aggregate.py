import pytest
from unittest.mock import patch

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import (
    MonsterAggregate,
    MAX_FEED_MEMORIES,
)
from ai_rpg_world.domain.monster.value_object.feed_memory_entry import FeedMemoryEntry
from ai_rpg_world.domain.monster.enum.monster_enum import (
    DeathCauseEnum,
    MonsterFactionEnum,
    MonsterStatusEnum,
)
from ai_rpg_world.domain.monster.event.monster_events import (
    MonsterCreatedEvent,
    MonsterDamagedEvent,
    MonsterDiedEvent,
    MonsterEvadedEvent,
    MonsterHealedEvent,
    MonsterMpRecoveredEvent,
    MonsterRespawnedEvent,
    MonsterSpawnedEvent,
    MonsterDecidedToMoveEvent,
    MonsterDecidedToUseSkillEvent,
    MonsterDecidedToInteractEvent,
    ActorStateChangedEvent,
    TargetSpottedEvent,
)
from ai_rpg_world.domain.monster.service.behavior_state_transition_service import (
    StateTransitionResult,
)
from ai_rpg_world.domain.monster.exception.monster_exceptions import (
    MonsterAlreadyDeadException,
    MonsterAlreadySpawnedException,
    MonsterInsufficientMpException,
    MonsterNotDeadException,
    MonsterNotSpawnedException,
    MonsterRespawnIntervalNotMetException,
)
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.value_object.growth_stage import GrowthStage
from ai_rpg_world.domain.combat.service.combat_logic_service import CombatLogicService
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.pack_id import PackId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum, EcologyTypeEnum
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.common.service.effective_stats_domain_service import compute_effective_stats


class TestMonsterAggregate:
    """MonsterAggregateのテスト"""

    @pytest.fixture
    def base_stats(self) -> BaseStats:
        return BaseStats(
            max_hp=100,
            max_mp=50,
            attack=20,
            defense=15,
            speed=10,
            critical_rate=0.05,
            evasion_rate=0.03,
        )

    @pytest.fixture
    def reward_info(self) -> RewardInfo:
        return RewardInfo(exp=100, gold=50, loot_table_id=1)

    @pytest.fixture
    def respawn_info(self) -> RespawnInfo:
        return RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True)

    @pytest.fixture
    def monster_template(self, base_stats: BaseStats, reward_info: RewardInfo, respawn_info: RespawnInfo) -> MonsterTemplate:
        return MonsterTemplate(
            template_id=MonsterTemplateId.create(1),
            name="Slime",
            base_stats=base_stats,
            reward_info=reward_info,
            respawn_info=respawn_info,
            race=Race.BEAST,
            faction=MonsterFactionEnum.ENEMY,
            description="A weak blue slime.",
        )

    @pytest.fixture
    def skill_loadout(self) -> SkillLoadoutAggregate:
        return SkillLoadoutAggregate.create(
            SkillLoadoutId(1),
            owner_id=1001,
            normal_capacity=10,
            awakened_capacity=10,
        )

    @pytest.fixture
    def spot_id(self) -> SpotId:
        return SpotId(1)

    @pytest.fixture
    def monster(self, monster_template: MonsterTemplate, skill_loadout: SkillLoadoutAggregate) -> MonsterAggregate:
        return MonsterAggregate.create(
            monster_id=MonsterId.create(1),
            template=monster_template,
            world_object_id=WorldObjectId.create(1001),
            skill_loadout=skill_loadout,
        )

    class TestCreate:
        def test_create_success(self, monster: MonsterAggregate, monster_template: MonsterTemplate):
            # Then
            assert monster.monster_id.value == 1
            assert monster.template == monster_template
            assert monster.status == MonsterStatusEnum.DEAD
            assert monster.coordinate is None

            events = monster.get_events()
            assert len(events) == 1
            event = events[0]
            assert isinstance(event, MonsterCreatedEvent)
            assert event.aggregate_id == monster.monster_id
            assert event.aggregate_type == "MonsterAggregate"
            assert event.template_id == monster_template.template_id.value
            assert hasattr(event, "event_id")
            assert hasattr(event, "occurred_at")

    class TestSpawn:
        def test_spawn_success(self, monster: MonsterAggregate, spot_id: SpotId):
            # Given
            coordinate = Coordinate(10, 20, 0)
            current_tick = WorldTick(0)

            # When
            monster.spawn(coordinate, spot_id, current_tick)

            # Then
            assert monster.coordinate == coordinate
            assert monster.spot_id == spot_id
            assert monster.status == MonsterStatusEnum.ALIVE
            assert monster.spawned_at_tick == current_tick
            assert monster.hp.value == monster.template.base_stats.max_hp
            assert monster.mp.value == monster.template.base_stats.max_mp

            events = monster.get_events()
            assert any(isinstance(e, MonsterSpawnedEvent) for e in events)
            spawn_event = next(e for e in events if isinstance(e, MonsterSpawnedEvent))
            assert spawn_event.coordinate == {"x": 10, "y": 20, "z": 0}
            assert spawn_event.spot_id == spot_id

        def test_spawn_already_spawned_raises_error(self, monster: MonsterAggregate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))

            # When & Then
            with pytest.raises(MonsterAlreadySpawnedException):
                monster.spawn(Coordinate(1, 1, 0), spot_id, WorldTick(1))

        def test_spawn_with_pack_id_sets_pack_and_leader(self, monster: MonsterAggregate, spot_id: SpotId):
            """spawn に pack_id / is_pack_leader を渡すとインスタンスに設定されること"""
            pack_id = PackId.create("goblin_pack_1")
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0), pack_id=pack_id, is_pack_leader=True)
            assert monster.pack_id == pack_id
            assert monster.is_pack_leader is True

        def test_spawn_without_pack_keeps_none(self, monster: MonsterAggregate, spot_id: SpotId):
            """pack を渡さない場合 pack_id は None、is_pack_leader は False のままであること"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            assert monster.pack_id is None
            assert monster.is_pack_leader is False

        def test_get_respawn_coordinate_before_spawn_returns_none(self, monster: MonsterAggregate):
            """スポーン前に get_respawn_coordinate は None を返すこと"""
            assert monster.get_respawn_coordinate() is None

        def test_get_respawn_coordinate_after_spawn_returns_initial_position(
            self, monster: MonsterAggregate, spot_id: SpotId
        ):
            """スポーン後に get_respawn_coordinate は初期スポーン座標を返すこと"""
            coordinate = Coordinate(10, 20, 0)
            monster.spawn(coordinate, spot_id, WorldTick(0))
            assert monster.get_respawn_coordinate() == coordinate

        def test_get_respawn_coordinate_after_respawn_unchanged(
            self, monster: MonsterAggregate, spot_id: SpotId
        ):
            """リスポーン後も get_respawn_coordinate は最初のスポーン座標のままであること"""
            initial = Coordinate(0, 0, 0)
            monster.spawn(initial, spot_id, WorldTick(0))
            monster.apply_damage(100, WorldTick(100))
            monster.respawn(Coordinate(5, 5, 0), WorldTick(200), spot_id)
            assert monster.get_respawn_coordinate() == initial

        def test_respawn_preserves_pack_id_and_leader(self, monster: MonsterAggregate, spot_id: SpotId):
            """リスポーン後も pack_id / is_pack_leader が維持されること"""
            pack_id = PackId.create("pack_a")
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0), pack_id=pack_id, is_pack_leader=False)
            monster.apply_damage(100, WorldTick(100))
            monster.respawn(Coordinate(5, 5, 0), WorldTick(200), spot_id)
            assert monster.pack_id == pack_id
            assert monster.is_pack_leader is False

        def test_respawn_sets_spawned_at_tick(self, monster: MonsterAggregate, spot_id: SpotId):
            """リスポーン時に spawned_at_tick が current_tick で更新されること"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            assert monster.spawned_at_tick == WorldTick(0)
            monster.apply_damage(100, WorldTick(100))
            monster.respawn(Coordinate(5, 5, 0), WorldTick(200), spot_id)
            assert monster.spawned_at_tick == WorldTick(200)

    class TestApplyDamage:
        def test_apply_damage_success(self, monster: MonsterAggregate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.clear_events()

            # When
            monster.apply_damage(30, WorldTick(10))

            # Then
            assert monster.hp.value == 70
            events = monster.get_events()
            assert len(events) == 1
            event = events[0]
            assert isinstance(event, MonsterDamagedEvent)
            assert event.aggregate_id == monster.monster_id
            assert event.aggregate_type == "MonsterAggregate"
            assert event.damage == 30
            assert event.current_hp == 70

        def test_apply_damage_not_spawned_raises_error(self, monster: MonsterAggregate):
            with pytest.raises(MonsterNotSpawnedException):
                monster.apply_damage(10, WorldTick(10))

        def test_apply_damage_already_dead_raises_error(self, monster: MonsterAggregate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(100, WorldTick(10))

            # When & Then
            with pytest.raises(MonsterAlreadyDeadException):
                monster.apply_damage(1, WorldTick(11))

    class TestCombatOrchestration:
        def test_application_style_damage_flow_success(self, monster: MonsterAggregate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            attacker_stats = BaseStats(
                max_hp=100,
                max_mp=30,
                attack=50,
                defense=5,
                speed=12,
                critical_rate=0.0,
                evasion_rate=0.0,
            )
            monster.clear_events()

            # When (アプリケーション層の責務を模した流れ)
            with patch("random.random", return_value=0.9):
                damage = CombatLogicService.calculate_damage(
                    attacker_stats=attacker_stats,
                    defender_stats=monster.template.base_stats,
                )
            if damage.is_evaded:
                monster.record_evasion()
            else:
                monster.apply_damage(damage.value, WorldTick(10))

            # Then
            assert monster.hp.value == 58  # (50 - 15/2) => int(42.5) = 42
            events = monster.get_events()
            assert len(events) == 1
            event = events[0]
            assert isinstance(event, MonsterDamagedEvent)
            assert event.damage == 42
            assert event.current_hp == 58

        def test_application_style_damage_flow_evaded(self, monster: MonsterAggregate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(1, 1, 0), spot_id, WorldTick(0))
            attacker_stats = BaseStats(
                max_hp=100,
                max_mp=30,
                attack=50,
                defense=5,
                speed=12,
                critical_rate=0.0,
                evasion_rate=0.0,
            )
            monster.clear_events()

            # When (アプリケーション層の責務を模した流れ)
            with patch("random.random", return_value=0.0):
                damage = CombatLogicService.calculate_damage(
                    attacker_stats=attacker_stats,
                    defender_stats=monster.template.base_stats,
                )
            if damage.is_evaded:
                monster.record_evasion()
            else:
                monster.apply_damage(damage.value, WorldTick(10))

            # Then
            assert monster.hp.value == 100
            events = monster.get_events()
            assert len(events) == 1
            event = events[0]
            assert isinstance(event, MonsterEvadedEvent)
            assert event.coordinate == {"x": 1, "y": 1, "z": 0}
            assert event.current_hp == 100

    class TestRecordEvasion:
        def test_record_evasion_success(self, monster: MonsterAggregate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(2, 3, 0), spot_id, WorldTick(0))
            monster.apply_damage(20, WorldTick(1))
            monster.clear_events()

            # When
            monster.record_evasion()

            # Then
            events = monster.get_events()
            assert len(events) == 1
            event = events[0]
            assert isinstance(event, MonsterEvadedEvent)
            assert event.aggregate_id == monster.monster_id
            assert event.aggregate_type == "MonsterAggregate"
            assert event.coordinate == {"x": 2, "y": 3, "z": 0}
            assert event.current_hp == 80
            assert hasattr(event, "event_id")
            assert hasattr(event, "occurred_at")

        def test_record_evasion_not_spawned_raises_error(self, monster: MonsterAggregate):
            with pytest.raises(MonsterNotSpawnedException):
                monster.record_evasion()

        def test_record_evasion_dead_raises_error(self, monster: MonsterAggregate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(100, WorldTick(10))

            # When & Then
            with pytest.raises(MonsterAlreadyDeadException):
                monster.record_evasion()

    class TestUpdateMapPlacement:
        """update_map_placement（ゲートウェイ等によるマップ間移動）のテスト"""

        def test_update_map_placement_success(self, monster: MonsterAggregate, spot_id: SpotId):
            """出現済みモンスターの座標・スポットを更新できること"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            new_spot = SpotId(2)
            new_coord = Coordinate(5, 10, 0)

            monster.update_map_placement(new_spot, new_coord)

            assert monster.spot_id == new_spot
            assert monster.coordinate == new_coord

        def test_update_map_placement_not_spawned_raises_error(self, monster: MonsterAggregate):
            """未出現のモンスターで update_map_placement すると MonsterAlreadyDeadException となること"""
            with pytest.raises(MonsterAlreadyDeadException):
                monster.update_map_placement(SpotId(1), Coordinate(0, 0, 0))

        def test_update_map_placement_after_death_raises_error(
            self, monster: MonsterAggregate, spot_id: SpotId
        ):
            """死亡済みのモンスターで update_map_placement すると MonsterAlreadyDeadException となること"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(100, WorldTick(10))

            with pytest.raises(MonsterAlreadyDeadException):
                monster.update_map_placement(SpotId(2), Coordinate(1, 1, 0))

    class TestDeathAndRespawn:
        def test_death_by_damage_adds_reward_event(self, monster: MonsterAggregate, monster_template: MonsterTemplate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(1, 2, 3), spot_id, WorldTick(0))
            current_tick = WorldTick(100)
            attacker_id = WorldObjectId.create(999)

            # When
            monster.apply_damage(100, current_tick, attacker_id=attacker_id)

            # Then
            assert monster.status == MonsterStatusEnum.DEAD
            assert monster.coordinate is None
            assert monster.last_death_tick == current_tick

            events = monster.get_events()
            die_event = next(e for e in events if isinstance(e, MonsterDiedEvent))
            assert die_event.respawn_tick == 200
            assert die_event.exp == monster_template.reward_info.exp
            assert die_event.gold == monster_template.reward_info.gold
            assert die_event.loot_table_id == monster_template.reward_info.loot_table_id
            assert die_event.killer_world_object_id == attacker_id
            assert die_event.cause == DeathCauseEnum.KILLED_BY_MONSTER

        def test_death_by_player_sets_cause_killed_by_player(
            self, monster: MonsterAggregate, spot_id: SpotId
        ):
            """プレイヤーが倒した場合 cause が KILLED_BY_PLAYER になること"""
            from ai_rpg_world.domain.player.value_object.player_id import PlayerId

            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(
                100,
                WorldTick(10),
                attacker_id=WorldObjectId.create(1),
                killer_player_id=PlayerId.create(1),
            )
            events = monster.get_events()
            die_event = next(e for e in events if isinstance(e, MonsterDiedEvent))
            assert die_event.cause == DeathCauseEnum.KILLED_BY_PLAYER
            assert die_event.killer_player_id == PlayerId.create(1)

        def test_starve_success(self, monster: MonsterAggregate, spot_id: SpotId):
            """飢餓で死亡させると STARVATION 原因でイベントが発行されること"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            current_tick = WorldTick(100)
            monster.starve(current_tick)
            assert monster.status == MonsterStatusEnum.DEAD
            events = monster.get_events()
            die_event = next(e for e in events if isinstance(e, MonsterDiedEvent))
            assert die_event.cause == DeathCauseEnum.STARVATION
            assert die_event.killer_player_id is None
            assert die_event.killer_world_object_id is None

        def test_starve_when_not_spawned_raises(self, monster: MonsterAggregate):
            """未スポーンのモンスターで starve すると MonsterNotSpawnedException"""
            with pytest.raises(MonsterNotSpawnedException):
                monster.starve(WorldTick(10))

        def test_starve_when_already_dead_raises(self, monster: MonsterAggregate, spot_id: SpotId):
            """既に死亡しているモンスターで starve すると MonsterAlreadyDeadException"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(100, WorldTick(10))
            with pytest.raises(MonsterAlreadyDeadException):
                monster.starve(WorldTick(20))

    class TestTickHunger:
        """tick_hunger のテスト"""

        def test_tick_hunger_returns_false_when_disabled(self, monster: MonsterAggregate, spot_id: SpotId):
            """飢餓無効（starvation_ticks=0）のとき False"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            result = monster.tick_hunger(WorldTick(1))
            assert result is False
            assert monster.hunger == 0.0

        def test_tick_hunger_increases_hunger_and_returns_true_when_starving(
            self, monster_template: MonsterTemplate, respawn_info: RespawnInfo, skill_loadout: SkillLoadoutAggregate, spot_id: SpotId
        ):
            """飢餓有効で閾値超過持続で True、STARVATION 死亡"""
            template = MonsterTemplate(
                template_id=monster_template.template_id,
                name=monster_template.name,
                base_stats=monster_template.base_stats,
                reward_info=monster_template.reward_info,
                respawn_info=respawn_info,
                race=monster_template.race,
                faction=monster_template.faction,
                description=monster_template.description,
                hunger_increase_per_tick=0.5,
                hunger_starvation_threshold=0.8,
                starvation_ticks=2,
            )
            monster = MonsterAggregate.create(
                MonsterId.create(1), template, WorldObjectId.create(1001), skill_loadout
            )
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0), initial_hunger=0.0)
            assert monster.tick_hunger(WorldTick(1)) is False
            assert monster.hunger == 0.5
            monster.tick_hunger(WorldTick(2))
            assert monster.hunger == 1.0
            # tick(3): hunger>=threshold で starvation_timer=2 に達し True を返す
            assert monster.tick_hunger(WorldTick(3)) is True
            monster.starve(WorldTick(3))
            assert monster.status == MonsterStatusEnum.DEAD

        def test_tick_hunger_returns_false_when_not_spawned(self, monster: MonsterAggregate):
            """未スポーンでは False"""
            assert monster.tick_hunger(WorldTick(1)) is False

    class TestRecordPreyKill:
        """record_prey_kill のテスト"""

        def test_record_prey_kill_reduces_hunger(self, monster_template: MonsterTemplate, respawn_info: RespawnInfo, skill_loadout: SkillLoadoutAggregate, spot_id: SpotId):
            """獲物撃破で飢餓が減る"""
            template = MonsterTemplate(
                template_id=monster_template.template_id,
                name=monster_template.name,
                base_stats=monster_template.base_stats,
                reward_info=monster_template.reward_info,
                respawn_info=respawn_info,
                race=monster_template.race,
                faction=monster_template.faction,
                description=monster_template.description,
                starvation_ticks=10,
                hunger_decrease_on_prey_kill=0.3,
            )
            monster = MonsterAggregate.create(
                MonsterId.create(1), template, WorldObjectId.create(1001), skill_loadout
            )
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0), initial_hunger=0.8)
            monster.record_prey_kill(0.3)
            assert monster.hunger == pytest.approx(0.5)

        def test_record_prey_kill_when_dead_raises(self, monster_template: MonsterTemplate, respawn_info: RespawnInfo, skill_loadout: SkillLoadoutAggregate, spot_id: SpotId):
            """死亡時は MonsterAlreadyDeadException"""
            template = MonsterTemplate(
                template_id=monster_template.template_id,
                name=monster_template.name,
                base_stats=monster_template.base_stats,
                reward_info=monster_template.reward_info,
                respawn_info=respawn_info,
                race=monster_template.race,
                faction=monster_template.faction,
                description=monster_template.description,
                starvation_ticks=10,
            )
            monster = MonsterAggregate.create(
                MonsterId.create(1), template, WorldObjectId.create(1001), skill_loadout
            )
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(999, WorldTick(10))
            with pytest.raises(MonsterAlreadyDeadException):
                monster.record_prey_kill(0.2)

    class TestRecordFeed:
        """record_feed（採食時の飢餓減少）のテスト"""

        def test_record_feed_success(self, monster_template: MonsterTemplate, respawn_info: RespawnInfo, skill_loadout: SkillLoadoutAggregate, spot_id: SpotId):
            """ALIVE 時に record_feed で飢餓が減少する"""
            template = MonsterTemplate(
                template_id=monster_template.template_id,
                name=monster_template.name,
                base_stats=monster_template.base_stats,
                reward_info=monster_template.reward_info,
                respawn_info=respawn_info,
                race=monster_template.race,
                faction=monster_template.faction,
                description=monster_template.description,
                starvation_ticks=10,
                hunger_decrease_on_feed=0.3,
            )
            monster = MonsterAggregate.create(
                MonsterId.create(1), template, WorldObjectId.create(1001), skill_loadout
            )
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0), initial_hunger=0.8)
            monster.record_feed(0.3)
            assert monster.hunger == pytest.approx(0.5)

        def test_record_feed_when_dead_raises(self, monster_template: MonsterTemplate, respawn_info: RespawnInfo, skill_loadout: SkillLoadoutAggregate, spot_id: SpotId):
            """死亡時は record_feed で MonsterAlreadyDeadException"""
            template = MonsterTemplate(
                template_id=monster_template.template_id,
                name=monster_template.name,
                base_stats=monster_template.base_stats,
                reward_info=monster_template.reward_info,
                respawn_info=respawn_info,
                race=monster_template.race,
                faction=monster_template.faction,
                description=monster_template.description,
                starvation_ticks=10,
                hunger_decrease_on_feed=0.3,
            )
            monster = MonsterAggregate.create(
                MonsterId.create(1), template, WorldObjectId.create(1001), skill_loadout
            )
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(999, WorldTick(10))
            with pytest.raises(MonsterAlreadyDeadException):
                monster.record_feed(0.2)

        def test_record_feed_when_not_spawned_raises(self, monster_template: MonsterTemplate, skill_loadout: SkillLoadoutAggregate):
            """未スポーン（DEAD 状態）では record_feed で MonsterAlreadyDeadException"""
            template = MonsterTemplate(
                template_id=monster_template.template_id,
                name=monster_template.name,
                base_stats=monster_template.base_stats,
                reward_info=monster_template.reward_info,
                respawn_info=monster_template.respawn_info,
                race=monster_template.race,
                faction=monster_template.faction,
                description=monster_template.description,
                starvation_ticks=10,
                hunger_decrease_on_feed=0.3,
            )
            monster = MonsterAggregate.create(
                MonsterId.create(1), template, WorldObjectId.create(1001), skill_loadout
            )
            with pytest.raises(MonsterAlreadyDeadException):
                monster.record_feed(0.2)

    class TestRememberFeed:
        """餌場記憶（remember_feed / behavior_last_known_feed）のテスト"""

        def test_remember_feed_adds_entry(self, monster: MonsterAggregate, spot_id: SpotId):
            """ALIVE 時に remember_feed で記憶が 1 件追加される"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            assert monster.behavior_last_known_feed == []
            monster.remember_feed(WorldObjectId.create(100), Coordinate(1, 2, 0))
            assert len(monster.behavior_last_known_feed) == 1
            assert monster.behavior_last_known_feed[0].object_id == WorldObjectId.create(100)
            assert monster.behavior_last_known_feed[0].coordinate == Coordinate(1, 2, 0)

        def test_remember_feed_lru_evicts_oldest(self, monster: MonsterAggregate, spot_id: SpotId):
            """MAX_FEED_MEMORIES を超えると古い記憶が追い出される"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            for i in range(MAX_FEED_MEMORIES + 1):
                monster.remember_feed(
                    WorldObjectId.create(100 + i),
                    Coordinate(i, i, 0),
                )
            assert len(monster.behavior_last_known_feed) == MAX_FEED_MEMORIES
            # 最初の 1 件（object_id=100）が追い出され、100+1, 100+2, 100+3 が残る
            ids = [e.object_id for e in monster.behavior_last_known_feed]
            assert WorldObjectId.create(100) not in ids
            assert WorldObjectId.create(101) in ids
            assert WorldObjectId.create(102) in ids
            assert WorldObjectId.create(103) in ids

        def test_remember_feed_same_object_id_moves_to_end(self, monster: MonsterAggregate, spot_id: SpotId):
            """同じ object_id で remember_feed すると末尾に移動（更新）"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.remember_feed(WorldObjectId.create(100), Coordinate(1, 0, 0))
            monster.remember_feed(WorldObjectId.create(101), Coordinate(2, 0, 0))
            monster.remember_feed(WorldObjectId.create(100), Coordinate(1, 1, 0))  # 更新
            assert len(monster.behavior_last_known_feed) == 2
            assert monster.behavior_last_known_feed[0].object_id == WorldObjectId.create(101)
            assert monster.behavior_last_known_feed[1].object_id == WorldObjectId.create(100)
            assert monster.behavior_last_known_feed[1].coordinate == Coordinate(1, 1, 0)

        def test_remember_feed_when_dead_does_nothing(self, monster: MonsterAggregate, spot_id: SpotId):
            """死亡時は remember_feed で何も追加されない（例外なし）"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(999, WorldTick(10))
            monster.remember_feed(WorldObjectId.create(100), Coordinate(1, 0, 0))
            assert monster.behavior_last_known_feed == []

        def test_behavior_last_known_feed_cleared_on_spawn(self, monster: MonsterAggregate, spot_id: SpotId, respawn_info: RespawnInfo):
            """spawn 時 _initialize_status で餌場記憶がクリアされる"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.remember_feed(WorldObjectId.create(100), Coordinate(1, 0, 0))
            assert len(monster.behavior_last_known_feed) == 1
            monster.apply_damage(999, WorldTick(10))
            # respawn_interval を満たす tick でリスポーン
            respawn_tick = 10 + respawn_info.respawn_interval_ticks
            monster.respawn(Coordinate(5, 5, 0), WorldTick(respawn_tick), spot_id)
            assert monster.behavior_last_known_feed == []

    class TestRecordAttackedBy:
        """record_attacked_by のテスト"""

        def test_record_attacked_by_sets_chase(self, monster: MonsterAggregate, spot_id: SpotId):
            """攻撃者を記録すると CHASE に遷移（NORMAL・HP十分）"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            attacker_id = WorldObjectId.create(200)
            attacker_coord = Coordinate(5, 5, 0)
            monster.record_attacked_by(attacker_id, attacker_coord, WorldTick(1))
            assert monster.behavior_target_id == attacker_id
            assert monster.behavior_last_known_position == attacker_coord
            assert monster.behavior_state == BehaviorStateEnum.CHASE

        def test_record_attacked_by_flee_only_sets_flee(self, monster_template: MonsterTemplate, respawn_info: RespawnInfo, skill_loadout: SkillLoadoutAggregate, spot_id: SpotId):
            """FLEE_ONLY のとき FLEE に遷移"""
            template = MonsterTemplate(
                template_id=monster_template.template_id,
                name=monster_template.name,
                base_stats=monster_template.base_stats,
                reward_info=monster_template.reward_info,
                respawn_info=respawn_info,
                race=monster_template.race,
                faction=monster_template.faction,
                description=monster_template.description,
                ecology_type=EcologyTypeEnum.FLEE_ONLY,
            )
            monster = MonsterAggregate.create(
                MonsterId.create(1), template, WorldObjectId.create(1001), skill_loadout
            )
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.record_attacked_by(WorldObjectId.create(99), Coordinate(1, 1, 0), WorldTick(1))
            assert monster.behavior_state == BehaviorStateEnum.FLEE
            assert monster.behavior_target_id == WorldObjectId.create(99)

        def test_record_attacked_by_when_not_spawned_raises(self, monster: MonsterAggregate):
            """未スポーン（DEAD 状態）では MonsterAlreadyDeadException"""
            with pytest.raises(MonsterAlreadyDeadException):
                monster.record_attacked_by(
                    WorldObjectId.create(99), Coordinate(1, 1, 0), WorldTick(1)
                )

        def test_record_attacked_by_when_dead_raises(self, monster: MonsterAggregate, spot_id: SpotId):
            """死亡時は MonsterAlreadyDeadException"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(999, WorldTick(10))
            with pytest.raises(MonsterAlreadyDeadException):
                monster.record_attacked_by(
                    WorldObjectId.create(99), Coordinate(1, 1, 0), WorldTick(20)
                )

    class TestDieFromOldAge:
        """die_from_old_age のテスト"""

        def test_die_from_old_age_success(self, monster_template: MonsterTemplate, spot_id: SpotId):
            """経過ティックが max_age_ticks 以上で NATURAL 死亡し True を返す"""
            template_with_age = MonsterTemplate(
                template_id=monster_template.template_id,
                name=monster_template.name,
                base_stats=monster_template.base_stats,
                reward_info=monster_template.reward_info,
                respawn_info=monster_template.respawn_info,
                race=monster_template.race,
                faction=monster_template.faction,
                description=monster_template.description,
                max_age_ticks=50,
            )
            loadout = SkillLoadoutAggregate.create(
                SkillLoadoutId(1), owner_id=1001, normal_capacity=10, awakened_capacity=10
            )
            monster = MonsterAggregate.create(
                MonsterId.create(1),
                template_with_age,
                WorldObjectId.create(1001),
                skill_loadout=loadout,
            )
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.clear_events()

            result = monster.die_from_old_age(WorldTick(50))

            assert result is True
            assert monster.status == MonsterStatusEnum.DEAD
            events = monster.get_events()
            die_event = next(e for e in events if isinstance(e, MonsterDiedEvent))
            assert die_event.cause == DeathCauseEnum.NATURAL

        def test_die_from_old_age_returns_false_when_elapsed_under(
            self, monster_template: MonsterTemplate, spot_id: SpotId
        ):
            """経過ティックが max_age_ticks 未満のときは何もせず False"""
            template_with_age = MonsterTemplate(
                template_id=monster_template.template_id,
                name=monster_template.name,
                base_stats=monster_template.base_stats,
                reward_info=monster_template.reward_info,
                respawn_info=monster_template.respawn_info,
                race=monster_template.race,
                faction=monster_template.faction,
                description=monster_template.description,
                max_age_ticks=100,
            )
            loadout = SkillLoadoutAggregate.create(
                SkillLoadoutId(1), owner_id=1001, normal_capacity=10, awakened_capacity=10
            )
            monster = MonsterAggregate.create(
                MonsterId.create(1),
                template_with_age,
                WorldObjectId.create(1001),
                skill_loadout=loadout,
            )
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))

            result = monster.die_from_old_age(WorldTick(50))

            assert result is False
            assert monster.status == MonsterStatusEnum.ALIVE

        def test_die_from_old_age_returns_false_when_not_spawned(self, monster: MonsterAggregate):
            """未スポーンのときは False（spawned_at_tick が None）"""
            result = monster.die_from_old_age(WorldTick(1000))
            assert result is False
            assert monster.status == MonsterStatusEnum.DEAD

        def test_die_from_old_age_returns_false_when_already_dead(
            self, monster_template: MonsterTemplate, spot_id: SpotId
        ):
            """既に DEAD のときは False"""
            template_with_age = MonsterTemplate(
                template_id=monster_template.template_id,
                name=monster_template.name,
                base_stats=monster_template.base_stats,
                reward_info=monster_template.reward_info,
                respawn_info=monster_template.respawn_info,
                race=monster_template.race,
                faction=monster_template.faction,
                description=monster_template.description,
                max_age_ticks=10,
            )
            loadout = SkillLoadoutAggregate.create(
                SkillLoadoutId(1), owner_id=1001, normal_capacity=10, awakened_capacity=10
            )
            monster = MonsterAggregate.create(
                MonsterId.create(1),
                template_with_age,
                WorldObjectId.create(1001),
                skill_loadout=loadout,
            )
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(100, WorldTick(5))

            result = monster.die_from_old_age(WorldTick(20))

            assert result is False
            assert monster.status == MonsterStatusEnum.DEAD

        def test_die_from_old_age_returns_false_when_max_age_ticks_none(
            self, monster: MonsterAggregate, spot_id: SpotId
        ):
            """max_age_ticks が None のときは False"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            result = monster.die_from_old_age(WorldTick(100000))
            assert result is False
            assert monster.status == MonsterStatusEnum.ALIVE

        def test_die_from_old_age_returns_false_when_max_age_ticks_zero(
            self, monster_template: MonsterTemplate, spot_id: SpotId
        ):
            """max_age_ticks が 0 のときは False"""
            template_zero = MonsterTemplate(
                template_id=monster_template.template_id,
                name=monster_template.name,
                base_stats=monster_template.base_stats,
                reward_info=monster_template.reward_info,
                respawn_info=monster_template.respawn_info,
                race=monster_template.race,
                faction=monster_template.faction,
                description=monster_template.description,
                max_age_ticks=0,
            )
            loadout = SkillLoadoutAggregate.create(
                SkillLoadoutId(1), owner_id=1001, normal_capacity=10, awakened_capacity=10
            )
            monster = MonsterAggregate.create(
                MonsterId.create(1),
                template_zero,
                WorldObjectId.create(1001),
                skill_loadout=loadout,
            )
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            result = monster.die_from_old_age(WorldTick(100000))
            assert result is False
            assert monster.status == MonsterStatusEnum.ALIVE

    class TestRespawn:
        def test_respawn_success(self, monster: MonsterAggregate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(100, WorldTick(100))
            monster.clear_events()

            # When
            new_coordinate = Coordinate(5, 5, 0)
            monster.respawn(new_coordinate, WorldTick(200), spot_id)

            # Then
            assert monster.status == MonsterStatusEnum.ALIVE
            assert monster.hp.value == 100
            assert monster.mp.value == 50
            assert monster.coordinate == new_coordinate
            assert monster.last_death_tick is None

            events = monster.get_events()
            assert len(events) == 1
            event = events[0]
            assert isinstance(event, MonsterRespawnedEvent)
            assert event.coordinate == {"x": 5, "y": 5, "z": 0}
            assert event.spot_id == spot_id

        def test_respawn_too_early_raises_error(self, monster: MonsterAggregate, spot_id: SpotId):
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(100, WorldTick(100))

            with pytest.raises(MonsterRespawnIntervalNotMetException):
                monster.respawn(Coordinate(0, 0, 0), WorldTick(150), spot_id)

        def test_respawn_not_dead_raises_error(self, monster: MonsterAggregate, spot_id: SpotId):
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            with pytest.raises(MonsterNotDeadException):
                monster.respawn(Coordinate(0, 0, 0), WorldTick(200), spot_id)

    class TestShouldRespawn:
        def test_should_respawn_conditions(self, monster: MonsterAggregate, spot_id: SpotId):
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(100, WorldTick(100))
            assert monster.should_respawn(WorldTick(150)) is False
            assert monster.should_respawn(WorldTick(200)) is True

        def test_should_respawn_no_auto_respawn(self, monster_template: MonsterTemplate, spot_id: SpotId):
            # Given
            no_auto_respawn_template = MonsterTemplate(
                template_id=monster_template.template_id,
                name=monster_template.name,
                base_stats=monster_template.base_stats,
                reward_info=monster_template.reward_info,
                respawn_info=RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=False),
                race=monster_template.race,
                faction=monster_template.faction,
                description=monster_template.description,
            )
            loadout_200 = SkillLoadoutAggregate.create(
                SkillLoadoutId(2),
                owner_id=200,
                normal_capacity=10,
                awakened_capacity=10,
            )
            monster = MonsterAggregate.create(
                monster_id=MonsterId.create(10),
                template=no_auto_respawn_template,
                world_object_id=WorldObjectId.create(200),
                skill_loadout=loadout_200,
            )
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(100, WorldTick(100))

            # Then
            assert monster.should_respawn(WorldTick(1000)) is False

    class TestRecoveryAndRegeneration:
        def test_heal_hp_success(self, monster: MonsterAggregate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(50, WorldTick(10))
            monster.clear_events()

            # When
            monster.heal_hp(30)

            # Then
            assert monster.hp.value == 80
            events = monster.get_events()
            assert len(events) == 1
            event = events[0]
            assert isinstance(event, MonsterHealedEvent)
            assert event.amount == 30
            assert event.current_hp == 80

        def test_recover_mp_success(self, monster: MonsterAggregate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.use_mp(40)
            monster.clear_events()

            # When
            monster.recover_mp(20)

            # Then
            assert monster.mp.value == 30
            events = monster.get_events()
            assert len(events) == 1
            event = events[0]
            assert isinstance(event, MonsterMpRecoveredEvent)
            assert event.amount == 20
            assert event.current_mp == 30

        def test_on_tick_regeneration(self, monster: MonsterAggregate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(50, WorldTick(10))
            monster.use_mp(40)
            monster.clear_events()

            # When（実効ステータスはアプリ層で算出して渡す）
            tick_11 = WorldTick(11)
            regen_stats = compute_effective_stats(
                monster.get_base_stats_with_growth(tick_11), monster.active_effects, tick_11
            )
            monster.on_tick(tick_11, regen_stats=regen_stats, regen_rate=0.01)

            # Then（1% で回復。100 * 0.01 = 1）
            assert monster.hp.value == 51
            assert monster.mp.value == 11
            events = monster.get_events()
            assert any(isinstance(e, MonsterHealedEvent) for e in events)
            assert any(isinstance(e, MonsterMpRecoveredEvent) for e in events)

        def test_on_tick_custom_regen_rate(self, monster: MonsterAggregate, spot_id: SpotId):
            """回復率を値で渡した場合にその率で回復すること"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(50, WorldTick(10))
            monster.clear_events()

            tick_11 = WorldTick(11)
            regen_stats = compute_effective_stats(
                monster.get_base_stats_with_growth(tick_11), monster.active_effects, tick_11
            )
            monster.on_tick(tick_11, regen_stats=regen_stats, regen_rate=0.1)

            assert monster.hp.value == 60  # 50 + 100 * 0.1

        def test_on_tick_no_regen_when_rate_none(self, monster: MonsterAggregate, spot_id: SpotId):
            """regen_rate を渡さない場合は回復しないこと"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(50, WorldTick(10))
            monster.use_mp(40)
            monster.clear_events()

            tick_11 = WorldTick(11)
            regen_stats = compute_effective_stats(
                monster.get_base_stats_with_growth(tick_11), monster.active_effects, tick_11
            )
            monster.on_tick(tick_11, regen_stats=regen_stats, regen_rate=None)

            assert monster.hp.value == 50
            assert monster.mp.value == 10
            events = monster.get_events()
            assert not any(isinstance(e, MonsterHealedEvent) for e in events)
            assert not any(isinstance(e, MonsterMpRecoveredEvent) for e in events)

    class TestMpUsage:
        def test_use_mp_success(self, monster: MonsterAggregate, spot_id: SpotId):
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.use_mp(20)
            assert monster.mp.value == 30

        def test_use_mp_insufficient_raises_error(self, monster: MonsterAggregate, spot_id: SpotId):
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            with pytest.raises(MonsterInsufficientMpException):
                monster.use_mp(60)

        def test_use_mp_not_alive_raises_error(self, monster: MonsterAggregate):
            with pytest.raises(MonsterAlreadyDeadException):
                monster.use_mp(1)

    class TestStatusEffects:
        def test_effective_stats_with_multiplicative_buffs_via_domain_service(
            self, monster: MonsterAggregate, spot_id: SpotId
        ):
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
            from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
            monster.add_status_effect(StatusEffect(StatusEffectType.ATTACK_UP, 1.5, WorldTick(100)))
            monster.add_status_effect(StatusEffect(StatusEffectType.ATTACK_UP, 1.2, WorldTick(100)))

            tick = WorldTick(10)
            effective_stats = compute_effective_stats(
                monster.get_base_stats_with_growth(tick), monster.active_effects, tick
            )
            assert effective_stats.attack == 36  # 20 * 1.5 * 1.2

        def test_effective_stats_filters_expired_effects_via_domain_service(
            self, monster: MonsterAggregate, spot_id: SpotId
        ):
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
            from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
            monster.add_status_effect(StatusEffect(StatusEffectType.ATTACK_UP, 2.0, WorldTick(5)))
            monster.add_status_effect(StatusEffect(StatusEffectType.ATTACK_UP, 1.5, WorldTick(20)))

            tick = WorldTick(10)
            effective_stats = compute_effective_stats(
                monster.get_base_stats_with_growth(tick), monster.active_effects, tick
            )
            assert effective_stats.attack == 30  # 20 * 1.5 のみ
            monster.cleanup_expired_effects(tick)
            assert len(monster.active_effects) == 1

        def test_buff_and_debuff_stacking_via_domain_service(
            self, monster: MonsterAggregate, spot_id: SpotId
        ):
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
            from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
            monster.add_status_effect(StatusEffect(StatusEffectType.ATTACK_UP, 1.5, WorldTick(100)))
            monster.add_status_effect(StatusEffect(StatusEffectType.ATTACK_DOWN, 0.5, WorldTick(100)))

            tick = WorldTick(10)
            effective_stats = compute_effective_stats(
                monster.get_base_stats_with_growth(tick), monster.active_effects, tick
            )
            assert effective_stats.attack == 15  # 20 * 1.5 * 0.5

    class TestSpawnedAtTick:
        """spawned_at_tick のテスト"""

        def test_spawned_at_tick_before_spawn_is_none(self, monster: MonsterAggregate):
            """スポーン前は spawned_at_tick が None であること"""
            assert monster.spawned_at_tick is None

        def test_spawned_at_tick_after_spawn_equals_current_tick(
            self, monster: MonsterAggregate, spot_id: SpotId
        ):
            """スポーン時に渡した current_tick が spawned_at_tick にセットされること"""
            tick = WorldTick(42)
            monster.spawn(Coordinate(0, 0, 0), spot_id, tick)
            assert monster.spawned_at_tick == tick

    class TestGrowthStages:
        """成長段階（get_current_growth_multiplier / get_base_stats_with_growth + compute_effective_stats）のテスト"""

        @pytest.fixture
        def template_with_growth_stages(
            self, base_stats: BaseStats, reward_info: RewardInfo, respawn_info: RespawnInfo
        ) -> MonsterTemplate:
            """幼体(0〜99 tick: 0.8) / 成体(100+ tick: 1.0) の2段階テンプレート"""
            return MonsterTemplate(
                template_id=MonsterTemplateId.create(2),
                name="Dragon",
                base_stats=base_stats,
                reward_info=reward_info,
                respawn_info=respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="Grows over time.",
                growth_stages=[
                    GrowthStage(after_ticks=0, stats_multiplier=0.8),
                    GrowthStage(after_ticks=100, stats_multiplier=1.0),
                ],
            )

        @pytest.fixture
        def monster_with_growth(
            self, template_with_growth_stages: MonsterTemplate, skill_loadout: SkillLoadoutAggregate
        ) -> MonsterAggregate:
            return MonsterAggregate.create(
                monster_id=MonsterId.create(2),
                template=template_with_growth_stages,
                world_object_id=WorldObjectId.create(2002),
                skill_loadout=skill_loadout,
            )

        def test_get_current_growth_multiplier_before_spawn_returns_one(
            self, monster_with_growth: MonsterAggregate
        ):
            """未スポーン時は乗率 1.0 を返すこと"""
            assert monster_with_growth.get_current_growth_multiplier(WorldTick(0)) == 1.0
            assert monster_with_growth.get_current_growth_multiplier(WorldTick(200)) == 1.0

        def test_get_current_growth_multiplier_when_current_tick_before_spawned_at_returns_one(
            self, monster_with_growth: MonsterAggregate, spot_id: SpotId
        ):
            """スポーン済みでも current_tick が spawned_at_tick より前の場合は乗率 1.0 を返すこと（時刻ずれ等の防御）"""
            monster_with_growth.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(100))
            assert monster_with_growth.get_current_growth_multiplier(WorldTick(50)) == 1.0
            assert monster_with_growth.get_current_growth_multiplier(WorldTick(99)) == 1.0

        def test_get_current_growth_multiplier_juvenile_stage(
            self, monster_with_growth: MonsterAggregate, spot_id: SpotId
        ):
            """スポーン直後〜99 tick は幼体乗率 0.8 であること"""
            monster_with_growth.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            assert monster_with_growth.get_current_growth_multiplier(WorldTick(0)) == 0.8
            assert monster_with_growth.get_current_growth_multiplier(WorldTick(50)) == 0.8
            assert monster_with_growth.get_current_growth_multiplier(WorldTick(99)) == 0.8

        def test_get_current_growth_multiplier_adult_stage(
            self, monster_with_growth: MonsterAggregate, spot_id: SpotId
        ):
            """100 tick 経過後は成体乗率 1.0 であること"""
            monster_with_growth.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            assert monster_with_growth.get_current_growth_multiplier(WorldTick(100)) == 1.0
            assert monster_with_growth.get_current_growth_multiplier(WorldTick(200)) == 1.0

        def test_get_base_stats_with_growth_applies_growth_multiplier_juvenile(
            self, monster_with_growth: MonsterAggregate, spot_id: SpotId
        ):
            """幼体時は get_base_stats_with_growth の攻撃・防御・速度に 0.8 が掛かること"""
            monster_with_growth.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            stats = monster_with_growth.get_base_stats_with_growth(WorldTick(50))
            # base: attack=20, defense=15, speed=10
            assert stats.attack == 16  # 20 * 0.8
            assert stats.defense == 12  # 15 * 0.8
            assert stats.speed == 8  # 10 * 0.8

        def test_get_base_stats_with_growth_applies_growth_multiplier_adult(
            self, monster_with_growth: MonsterAggregate, spot_id: SpotId
        ):
            """成体時は get_base_stats_with_growth がベースのままであること"""
            monster_with_growth.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            stats = monster_with_growth.get_base_stats_with_growth(WorldTick(150))
            assert stats.attack == 20
            assert stats.defense == 15
            assert stats.speed == 10

        def test_get_effective_flee_threshold_and_allow_chase_default_without_flee_bias(
            self, monster_with_growth: MonsterAggregate, spot_id: SpotId
        ):
            """flee_bias_multiplier 未指定の段階ではテンプレートの flee_threshold と allow_chase True であること"""
            monster_with_growth.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            # template_with_growth_stages の flee_threshold はデフォルト 0.2
            assert monster_with_growth.get_effective_flee_threshold(WorldTick(50)) == 0.2
            assert monster_with_growth.get_allow_chase(WorldTick(50)) is True

        def test_get_base_stats_with_growth_no_growth_stages_uses_one(
            self, monster: MonsterAggregate, spot_id: SpotId
        ):
            """growth_stages が空のテンプレートでは乗率 1.0 であること"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            stats = monster.get_base_stats_with_growth(WorldTick(1000))
            assert stats.attack == monster.template.base_stats.attack
            assert stats.defense == monster.template.base_stats.defense

        def test_get_base_stats_with_growth_applies_growth_to_max_hp_mp(
            self, monster_with_growth: MonsterAggregate, spot_id: SpotId
        ):
            """成長段階の乗率が max_hp, max_mp にも適用されること"""
            monster_with_growth.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            stats = monster_with_growth.get_base_stats_with_growth(WorldTick(50))
            # base max_hp=100, max_mp=50、幼体 0.8 → 80, 40
            assert stats.max_hp == 80
            assert stats.max_mp == 40

        def test_spawn_initializes_hp_mp_with_effective_stats_juvenile(
            self, monster_with_growth: MonsterAggregate, spot_id: SpotId
        ):
            """成長段階ありのテンプレートでスポーン時、HP/MP は実効 max_hp/max_mp で満タンに初期化されること（幼体）"""
            monster_with_growth.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            # 幼体 0.8 → 80, 40
            assert monster_with_growth.hp.value == 80
            assert monster_with_growth.mp.value == 40
            assert monster_with_growth.hp.max_hp == 80
            assert monster_with_growth.mp.max_mp == 40

        def test_respawn_initializes_hp_mp_with_effective_stats(
            self, monster_with_growth: MonsterAggregate, spot_id: SpotId
        ):
            """成長段階ありのテンプレートでリスポーン時も、HP/MP は実効 max_hp/max_mp で満タンに初期化されること"""
            monster_with_growth.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster_with_growth.apply_damage(80, WorldTick(10))
            monster_with_growth.respawn(Coordinate(5, 5, 0), WorldTick(200), spot_id)
            # リスポーン時 spawned_at_tick=200 なので経過 0 → 幼体段階（0.8）→ 80, 40
            assert monster_with_growth.hp.value == 80
            assert monster_with_growth.mp.value == 40

        def test_get_effective_flee_threshold_with_stage_flee_bias(
            self, monster_with_growth: MonsterAggregate, spot_id: SpotId
        ):
            """成長段階に flee_bias_multiplier がある場合に get_effective_flee_threshold がそれを反映すること"""
            # template_with_growth_stages は flee_bias なしなので、別 fixture で flee_bias ありのテンプレートを作る
            from ai_rpg_world.domain.monster.value_object.growth_stage import GrowthStage
            base_stats = BaseStats(100, 50, 20, 15, 10, 0.05, 0.03)
            template_flee = MonsterTemplate(
                template_id=MonsterTemplateId.create(3),
                name="Prey",
                base_stats=base_stats,
                reward_info=RewardInfo(10, 5, None),
                respawn_info=RespawnInfo(100, True),
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="Flees easily when juvenile.",
                growth_stages=[
                    GrowthStage(after_ticks=0, stats_multiplier=0.8, flee_bias_multiplier=1.5, allow_chase=False),
                    GrowthStage(after_ticks=100, stats_multiplier=1.0),
                ],
            )
            from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
            from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(3), owner_id=3003, normal_capacity=10, awakened_capacity=10)
            agg = MonsterAggregate.create(
                monster_id=MonsterId.create(3),
                template=template_flee,
                world_object_id=WorldObjectId.create(3003),
                skill_loadout=loadout,
            )
            agg.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            # テンプレートの flee_threshold は 0.2。1.5 倍で min(1.0, 0.3) = 0.3
            assert agg.get_effective_flee_threshold(WorldTick(50)) == 0.3
            assert agg.get_allow_chase(WorldTick(50)) is False
            # 成体ではデフォルト（flee_bias なしなので 0.2）、allow_chase True
            assert agg.get_effective_flee_threshold(WorldTick(150)) == 0.2
            assert agg.get_allow_chase(WorldTick(150)) is True


class TestMonsterAggregateBehaviorState(TestMonsterAggregate):
    """Monster の行動状態スナップショットと decide のテスト（TestMonsterAggregate の fixture を利用）"""

    @pytest.fixture
    def spawned_monster(
        self, monster_template, skill_loadout, spot_id
    ) -> MonsterAggregate:
        agg = MonsterAggregate.create(
            monster_id=MonsterId.create(1),
            template=monster_template,
            world_object_id=WorldObjectId(1),
            skill_loadout=skill_loadout,
        )
        agg.spawn(Coordinate(5, 5, 0), spot_id, WorldTick(10))
        return agg

    def test_to_behavior_state_snapshot_after_spawn(self, spawned_monster):
        """スポーン直後の to_behavior_state_snapshot が IDLE と初期位置を返すこと"""
        from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum
        from ai_rpg_world.domain.monster.value_object.behavior_state_snapshot import BehaviorStateSnapshot

        snap = spawned_monster.to_behavior_state_snapshot(
            Coordinate(5, 5, 0), WorldTick(10)
        )
        assert isinstance(snap, BehaviorStateSnapshot)
        assert snap.state == BehaviorStateEnum.IDLE
        assert snap.target_id is None
        assert snap.last_known_target_position is None
        assert snap.hp_percentage == 1.0
        assert snap.flee_threshold == 0.2

    def test_to_behavior_state_snapshot_phase_thresholds_from_template(self, base_stats, reward_info, respawn_info, skill_loadout, spot_id):
        """phase_thresholds はテンプレートから取得されること"""
        from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum
        from ai_rpg_world.domain.monster.value_object.behavior_state_snapshot import BehaviorStateSnapshot

        template = MonsterTemplate(
            template_id=MonsterTemplateId.create(2),
            name="Boss",
            base_stats=base_stats,
            reward_info=reward_info,
            respawn_info=respawn_info,
            race=Race.BEAST,
            faction=MonsterFactionEnum.ENEMY,
            description="Boss",
            phase_thresholds=[0.5, 0.25],
        )
        agg = MonsterAggregate.create(
            monster_id=MonsterId.create(2),
            template=template,
            world_object_id=WorldObjectId(2),
            skill_loadout=skill_loadout,
        )
        agg.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
        snap = agg.to_behavior_state_snapshot(Coordinate(0, 0, 0), WorldTick(0))
        assert snap.phase_thresholds == (0.5, 0.25)

    class TestApplyBehaviorTransition:
        """apply_behavior_transition のテスト"""

        def test_apply_behavior_transition_success_empty_result(
            self, spawned_monster
        ):
            """空の StateTransitionResult で呼んでも状態が変わらず例外が出ないこと"""
            result = StateTransitionResult()
            spawned_monster.clear_events()
            spawned_monster.apply_behavior_transition(result, WorldTick(10))
            assert spawned_monster.behavior_state == BehaviorStateEnum.IDLE
            events = spawned_monster.get_events()
            assert len(events) == 0

        def test_apply_behavior_transition_when_not_spawned_raises(self, monster):
            """未スポーンのモンスターで呼ぶと MonsterAlreadyDeadException"""
            result = StateTransitionResult()
            with pytest.raises(MonsterAlreadyDeadException):
                monster.apply_behavior_transition(result, WorldTick(0))

        def test_apply_behavior_transition_when_dead_raises(
            self, monster, spot_id
        ):
            """死亡済みモンスターで呼ぶと MonsterAlreadyDeadException"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(999, WorldTick(1))
            assert monster.status == MonsterStatusEnum.DEAD
            result = StateTransitionResult()
            with pytest.raises(MonsterAlreadyDeadException):
                monster.apply_behavior_transition(result, WorldTick(2))

        def test_apply_behavior_transition_flee_result_updates_state(
            self, spawned_monster
        ):
            """FLEE の StateTransitionResult で呼ぶと状態が FLEE になりイベントが発行されること"""
            spawned_monster.clear_events()
            result = StateTransitionResult(
                flee_from_threat_id=WorldObjectId(999),
                flee_from_threat_coordinate=Coordinate(10, 10, 0),
            )
            spawned_monster.apply_behavior_transition(result, WorldTick(10))
            assert spawned_monster.behavior_state == BehaviorStateEnum.FLEE
            assert spawned_monster.behavior_target_id == WorldObjectId(999)
            events = spawned_monster.get_events()
            assert any(isinstance(e, TargetSpottedEvent) for e in events)
            assert any(isinstance(e, ActorStateChangedEvent) for e in events)

    class TestApplyTerritoryReturnIfNeeded:
        """apply_territory_return_if_needed のテスト"""

        def test_apply_territory_return_when_outside_radius(
            self, base_stats, reward_info, respawn_info, skill_loadout, spot_id
        ):
            """テリトリ外で CHASE のとき RETURN に遷移すること"""
            template = MonsterTemplate(
                template_id=MonsterTemplateId.create(2),
                name="Territory",
                base_stats=base_stats,
                reward_info=reward_info,
                respawn_info=respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="x",
                territory_radius=5,
            )
            agg = MonsterAggregate.create(
                monster_id=MonsterId.create(2),
                template=template,
                world_object_id=WorldObjectId(2),
                skill_loadout=skill_loadout,
            )
            agg.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            agg._behavior_state = BehaviorStateEnum.CHASE
            agg.clear_events()
            # 座標 (10, 0, 0) は初期位置 (0,0,0) から距離 10 > territory_radius 5
            agg.apply_territory_return_if_needed(Coordinate(10, 0, 0))
            assert agg.behavior_state == BehaviorStateEnum.RETURN
            events = agg.get_events()
            assert any(
                isinstance(e, ActorStateChangedEvent)
                and e.new_state == BehaviorStateEnum.RETURN
                for e in events
            )

        def test_apply_territory_return_when_inside_radius_no_change(
            self, base_stats, reward_info, respawn_info, skill_loadout, spot_id
        ):
            """テリトリ内のときは状態が変わらないこと"""
            template = MonsterTemplate(
                template_id=MonsterTemplateId.create(2),
                name="Territory",
                base_stats=base_stats,
                reward_info=reward_info,
                respawn_info=respawn_info,
                race=Race.BEAST,
                faction=MonsterFactionEnum.ENEMY,
                description="x",
                territory_radius=10,
            )
            agg = MonsterAggregate.create(
                monster_id=MonsterId.create(2),
                template=template,
                world_object_id=WorldObjectId(2),
                skill_loadout=skill_loadout,
            )
            agg.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            agg._behavior_state = BehaviorStateEnum.CHASE
            agg.clear_events()
            agg.apply_territory_return_if_needed(Coordinate(2, 0, 0))
            assert agg.behavior_state == BehaviorStateEnum.CHASE
            events = agg.get_events()
            assert not any(
                isinstance(e, ActorStateChangedEvent)
                and e.new_state == BehaviorStateEnum.RETURN
                for e in events
            )

        def test_apply_territory_return_when_not_spawned_raises(self, monster):
            """未スポーンのモンスターで呼ぶと MonsterAlreadyDeadException"""
            with pytest.raises(MonsterAlreadyDeadException):
                monster.apply_territory_return_if_needed(Coordinate(0, 0, 0))

    class TestRecordMove:
        """record_move のテスト"""

        def test_record_move_success(self, spawned_monster):
            """record_move で MonsterDecidedToMoveEvent が 1 件発行されること"""
            spawned_monster.clear_events()
            spawned_monster.record_move(
                Coordinate(6, 5, 0), WorldTick(10)
            )
            events = spawned_monster.get_events()
            move_events = [
                e for e in events if isinstance(e, MonsterDecidedToMoveEvent)
            ]
            assert len(move_events) == 1
            assert move_events[0].actor_id == spawned_monster.world_object_id
            assert move_events[0].coordinate == {"x": 6, "y": 5, "z": 0}
            assert move_events[0].spot_id == spawned_monster.spot_id
            assert move_events[0].current_tick == WorldTick(10)

        def test_record_move_when_not_spawned_raises(self, monster):
            """未スポーンのモンスターで呼ぶと MonsterAlreadyDeadException"""
            with pytest.raises(MonsterAlreadyDeadException):
                monster.record_move(Coordinate(1, 1, 0), WorldTick(0))

        def test_record_move_when_dead_raises(self, monster, spot_id):
            """死亡済みモンスターで呼ぶと MonsterAlreadyDeadException"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(999, WorldTick(1))
            with pytest.raises(MonsterAlreadyDeadException):
                monster.record_move(Coordinate(1, 1, 0), WorldTick(2))

    class TestRecordUseSkill:
        """record_use_skill のテスト"""

        def test_record_use_skill_success(self, spawned_monster):
            """record_use_skill で MonsterDecidedToUseSkillEvent が 1 件発行されること"""
            spawned_monster.clear_events()
            spawned_monster.record_use_skill(0, None, WorldTick(10))
            events = spawned_monster.get_events()
            skill_events = [
                e
                for e in events
                if isinstance(e, MonsterDecidedToUseSkillEvent)
            ]
            assert len(skill_events) == 1
            assert skill_events[0].actor_id == spawned_monster.world_object_id
            assert skill_events[0].skill_slot_index == 0
            assert skill_events[0].target_id is None
            assert skill_events[0].spot_id == spawned_monster.spot_id
            assert skill_events[0].current_tick == WorldTick(10)

        def test_record_use_skill_when_not_spawned_raises(self, monster):
            """未スポーンのモンスターで呼ぶと MonsterAlreadyDeadException"""
            with pytest.raises(MonsterAlreadyDeadException):
                monster.record_use_skill(0, None, WorldTick(0))

        def test_record_use_skill_when_dead_raises(self, monster, spot_id):
            """死亡済みモンスターで呼ぶと MonsterAlreadyDeadException"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(999, WorldTick(1))
            with pytest.raises(MonsterAlreadyDeadException):
                monster.record_use_skill(0, None, WorldTick(2))

    class TestRecordInteract:
        """record_interact のテスト"""

        def test_record_interact_success(self, spawned_monster):
            """record_interact で MonsterDecidedToInteractEvent が 1 件発行されること"""
            target_id = WorldObjectId(99)
            spawned_monster.clear_events()
            spawned_monster.record_interact(target_id, WorldTick(10))
            events = spawned_monster.get_events()
            interact_events = [
                e
                for e in events
                if isinstance(e, MonsterDecidedToInteractEvent)
            ]
            assert len(interact_events) == 1
            assert interact_events[0].actor_id == spawned_monster.world_object_id
            assert interact_events[0].target_id == target_id
            assert interact_events[0].spot_id == spawned_monster.spot_id
            assert interact_events[0].current_tick == WorldTick(10)

        def test_record_interact_when_not_spawned_raises(self, monster):
            """未スポーンのモンスターで呼ぶと MonsterAlreadyDeadException"""
            with pytest.raises(MonsterAlreadyDeadException):
                monster.record_interact(WorldObjectId(1), WorldTick(0))

        def test_record_interact_when_dead_raises(self, monster, spot_id):
            """死亡済みモンスターで呼ぶと MonsterAlreadyDeadException"""
            monster.spawn(Coordinate(0, 0, 0), spot_id, WorldTick(0))
            monster.apply_damage(999, WorldTick(1))
            with pytest.raises(MonsterAlreadyDeadException):
                monster.record_interact(WorldObjectId(1), WorldTick(2))

    def test_advance_patrol_index(self, spawned_monster):
        """advance_patrol_index がインデックスを進めること"""
        assert spawned_monster.behavior_patrol_index == 0
        spawned_monster.advance_patrol_index(3)
        assert spawned_monster.behavior_patrol_index == 1
        spawned_monster.advance_patrol_index(3)
        assert spawned_monster.behavior_patrol_index == 2
        spawned_monster.advance_patrol_index(3)
        assert spawned_monster.behavior_patrol_index == 0
