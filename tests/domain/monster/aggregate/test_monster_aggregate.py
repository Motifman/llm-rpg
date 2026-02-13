import pytest
from unittest.mock import patch

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum, MonsterStatusEnum
from ai_rpg_world.domain.monster.event.monster_events import (
    MonsterCreatedEvent,
    MonsterDamagedEvent,
    MonsterDiedEvent,
    MonsterEvadedEvent,
    MonsterHealedEvent,
    MonsterMpRecoveredEvent,
    MonsterRespawnedEvent,
    MonsterSpawnedEvent,
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
from ai_rpg_world.domain.combat.service.combat_logic_service import CombatLogicService
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId


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
        return RewardInfo(exp=100, gold=50, loot_table_id="loot_slime_01")

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

            # When
            monster.spawn(coordinate, spot_id)

            # Then
            assert monster.coordinate == coordinate
            assert monster.spot_id == spot_id
            assert monster.status == MonsterStatusEnum.ALIVE
            assert monster.hp.value == monster.template.base_stats.max_hp
            assert monster.mp.value == monster.template.base_stats.max_mp

            events = monster.get_events()
            assert any(isinstance(e, MonsterSpawnedEvent) for e in events)
            spawn_event = next(e for e in events if isinstance(e, MonsterSpawnedEvent))
            assert spawn_event.coordinate == {"x": 10, "y": 20, "z": 0}
            assert spawn_event.spot_id == spot_id

        def test_spawn_already_spawned_raises_error(self, monster: MonsterAggregate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(0, 0, 0), spot_id)

            # When & Then
            with pytest.raises(MonsterAlreadySpawnedException):
                monster.spawn(Coordinate(1, 1, 0), spot_id)

    class TestApplyDamage:
        def test_apply_damage_success(self, monster: MonsterAggregate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(0, 0, 0), spot_id)
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
            monster.spawn(Coordinate(0, 0, 0), spot_id)
            monster.apply_damage(100, WorldTick(10))

            # When & Then
            with pytest.raises(MonsterAlreadyDeadException):
                monster.apply_damage(1, WorldTick(11))

    class TestCombatOrchestration:
        def test_application_style_damage_flow_success(self, monster: MonsterAggregate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(0, 0, 0), spot_id)
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
            monster.spawn(Coordinate(1, 1, 0), spot_id)
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
            monster.spawn(Coordinate(2, 3, 0), spot_id)
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
            monster.spawn(Coordinate(0, 0, 0), spot_id)
            monster.apply_damage(100, WorldTick(10))

            # When & Then
            with pytest.raises(MonsterAlreadyDeadException):
                monster.record_evasion()

    class TestUpdateMapPlacement:
        """update_map_placement（ゲートウェイ等によるマップ間移動）のテスト"""

        def test_update_map_placement_success(self, monster: MonsterAggregate, spot_id: SpotId):
            """出現済みモンスターの座標・スポットを更新できること"""
            monster.spawn(Coordinate(0, 0, 0), spot_id)
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
            monster.spawn(Coordinate(0, 0, 0), spot_id)
            monster.apply_damage(100, WorldTick(10))

            with pytest.raises(MonsterAlreadyDeadException):
                monster.update_map_placement(SpotId(2), Coordinate(1, 1, 0))

    class TestDeathAndRespawn:
        def test_death_by_damage_adds_reward_event(self, monster: MonsterAggregate, monster_template: MonsterTemplate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(1, 2, 3), spot_id)
            current_tick = WorldTick(100)

            # When
            monster.apply_damage(100, current_tick)

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

        def test_respawn_success(self, monster: MonsterAggregate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(0, 0, 0), spot_id)
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
            monster.spawn(Coordinate(0, 0, 0), spot_id)
            monster.apply_damage(100, WorldTick(100))

            with pytest.raises(MonsterRespawnIntervalNotMetException):
                monster.respawn(Coordinate(0, 0, 0), WorldTick(150), spot_id)

        def test_respawn_not_dead_raises_error(self, monster: MonsterAggregate, spot_id: SpotId):
            monster.spawn(Coordinate(0, 0, 0), spot_id)
            with pytest.raises(MonsterNotDeadException):
                monster.respawn(Coordinate(0, 0, 0), WorldTick(200), spot_id)

    class TestShouldRespawn:
        def test_should_respawn_conditions(self, monster: MonsterAggregate, spot_id: SpotId):
            monster.spawn(Coordinate(0, 0, 0), spot_id)
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
            monster.spawn(Coordinate(0, 0, 0), spot_id)
            monster.apply_damage(100, WorldTick(100))

            # Then
            assert monster.should_respawn(WorldTick(1000)) is False

    class TestRecoveryAndRegeneration:
        def test_heal_hp_success(self, monster: MonsterAggregate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(0, 0, 0), spot_id)
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
            monster.spawn(Coordinate(0, 0, 0), spot_id)
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
            monster.spawn(Coordinate(0, 0, 0), spot_id)
            monster.apply_damage(50, WorldTick(10))
            monster.use_mp(40)
            monster.clear_events()

            # When
            monster.on_tick(WorldTick(11))

            # Then
            # Default rate is 0.01 (1%). 100 * 0.01 = 1.
            assert monster.hp.value == 51
            assert monster.mp.value == 11
            events = monster.get_events()
            assert any(isinstance(e, MonsterHealedEvent) for e in events)
            assert any(isinstance(e, MonsterMpRecoveredEvent) for e in events)

        def test_on_tick_custom_config(self, monster: MonsterAggregate, spot_id: SpotId):
            from ai_rpg_world.domain.monster.service.monster_config_service import DefaultMonsterConfigService
            monster.spawn(Coordinate(0, 0, 0), spot_id)
            monster.apply_damage(50, WorldTick(10))
            monster.clear_events()
            
            # Rate 10%
            config = DefaultMonsterConfigService(regeneration_rate=0.1)
            monster.on_tick(WorldTick(11), config=config)
            
            assert monster.hp.value == 60 # 50 + 100 * 0.1

    class TestMpUsage:
        def test_use_mp_success(self, monster: MonsterAggregate, spot_id: SpotId):
            monster.spawn(Coordinate(0, 0, 0), spot_id)
            monster.use_mp(20)
            assert monster.mp.value == 30

        def test_use_mp_insufficient_raises_error(self, monster: MonsterAggregate, spot_id: SpotId):
            monster.spawn(Coordinate(0, 0, 0), spot_id)
            with pytest.raises(MonsterInsufficientMpException):
                monster.use_mp(60)

        def test_use_mp_not_alive_raises_error(self, monster: MonsterAggregate):
            with pytest.raises(MonsterAlreadyDeadException):
                monster.use_mp(1)

    class TestStatusEffects:
        def test_get_effective_stats_with_multiplicative_buffs(self, monster: MonsterAggregate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(0, 0, 0), spot_id)
            # 攻撃力 20
            # 1.5倍バフと1.2倍バフを付与
            from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
            from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
            monster.add_status_effect(StatusEffect(StatusEffectType.ATTACK_UP, 1.5, WorldTick(100)))
            monster.add_status_effect(StatusEffect(StatusEffectType.ATTACK_UP, 1.2, WorldTick(100)))
            
            # When
            effective_stats = monster.get_effective_stats(WorldTick(10))
            
            # Then
            # 20 * 1.5 * 1.2 = 36
            assert effective_stats.attack == 36

        def test_get_effective_stats_filters_expired_effects(self, monster: MonsterAggregate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(0, 0, 0), spot_id)
            # 攻撃力 20
            # 期限切れ(Tick 5)の 2.0倍バフ
            from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
            from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
            monster.add_status_effect(StatusEffect(StatusEffectType.ATTACK_UP, 2.0, WorldTick(5)))
            # 有効な 1.5倍バフ
            monster.add_status_effect(StatusEffect(StatusEffectType.ATTACK_UP, 1.5, WorldTick(20)))
            
            # When
            effective_stats = monster.get_effective_stats(WorldTick(10))
            
            # Then
            # 20 * 1.5 = 30
            assert effective_stats.attack == 30
            assert len(monster._active_effects) == 1

        def test_buff_and_debuff_stacking(self, monster: MonsterAggregate, spot_id: SpotId):
            # Given
            monster.spawn(Coordinate(0, 0, 0), spot_id)
            # 攻撃力 20
            # 1.5倍バフと 0.5倍デバフ
            from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
            from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
            monster.add_status_effect(StatusEffect(StatusEffectType.ATTACK_UP, 1.5, WorldTick(100)))
            monster.add_status_effect(StatusEffect(StatusEffectType.ATTACK_DOWN, 0.5, WorldTick(100)))
            
            # When
            effective_stats = monster.get_effective_stats(WorldTick(10))
            
            # Then
            # 20 * 1.5 * 0.5 = 15
            assert effective_stats.attack == 15
