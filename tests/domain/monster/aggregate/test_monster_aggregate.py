import pytest
from unittest.mock import patch
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterStatusEnum, MonsterFactionEnum
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.monster.event.monster_events import (
    MonsterCreatedEvent,
    MonsterSpawnedEvent,
    MonsterDamagedEvent,
    MonsterDiedEvent,
    MonsterRespawnedEvent,
    MonsterEvadedEvent,
    MonsterHealedEvent,
    MonsterMpRecoveredEvent
)
from ai_rpg_world.domain.monster.exception.monster_exceptions import (
    MonsterAlreadyDeadException,
    MonsterAlreadySpawnedException,
    MonsterNotDeadException,
    MonsterNotSpawnedException,
    MonsterRespawnIntervalNotMetException,
    MonsterInsufficientMpException
)
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.common.value_object import WorldTick


@pytest.fixture
def base_stats():
    return BaseStats(
        max_hp=100,
        max_mp=50,
        attack=20,
        defense=15,
        speed=10,
        critical_rate=0.05,
        evasion_rate=0.03
    )


@pytest.fixture
def reward_info():
    return RewardInfo(exp=100, gold=50, loot_table_id="loot_slime_01")


@pytest.fixture
def respawn_info():
    return RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=True)


@pytest.fixture
def monster_template(base_stats, reward_info, respawn_info):
    return MonsterTemplate(
        template_id=MonsterTemplateId.create(1),
        name="Slime",
        base_stats=base_stats,
        reward_info=reward_info,
        respawn_info=respawn_info,
        race=Race.BEAST,
        faction=MonsterFactionEnum.ENEMY,
        description="A weak blue slime."
    )


@pytest.fixture
def monster(monster_template):
    return MonsterAggregate.create(
        monster_id=MonsterId.create(1),
        template=monster_template,
        world_object_id=WorldObjectId.create(1001)
    )


class TestMonsterAggregate:
    """MonsterAggregateのテスト"""

    class TestCreate:
        """新規作成のテスト"""
        def test_create_success(self, monster, monster_template):
            """モンスター個体の新規作成が成功する"""
            assert monster.monster_id.value == 1
            assert monster.template == monster_template
            assert monster.status == MonsterStatusEnum.DEAD  # 初期状態はDEAD
            assert monster.coordinate is None

            events = monster.get_events()
            assert len(events) == 1
            assert isinstance(events[0], MonsterCreatedEvent)
            assert events[0].template_id == monster_template.template_id.value

    class TestSpawn:
        """出現（Spawn）のテスト"""
        def test_spawn_success(self, monster):
            """モンスターの出現が成功する"""
            coord = Coordinate(10, 20, 0)
            monster.spawn(coord)

            assert monster.coordinate == coord
            assert monster.status == MonsterStatusEnum.ALIVE
            assert monster.hp.value == monster.template.base_stats.max_hp
            assert monster.mp.value == monster.template.base_stats.max_mp
            
            events = monster.get_events()
            assert any(isinstance(e, MonsterSpawnedEvent) for e in events)
            spawn_event = next(e for e in events if isinstance(e, MonsterSpawnedEvent))
            assert spawn_event.coordinate == {"x": 10, "y": 20, "z": 0}

        def test_spawn_already_spawned_raises_error(self, monster):
            """既に出現しているモンスターを再度出現させようとするとエラーが発生する"""
            monster.spawn(Coordinate(0, 0))
            with pytest.raises(MonsterAlreadySpawnedException):
                monster.spawn(Coordinate(1, 1))

    class TestTakeDamage:
        """ダメージを受ける（TakeDamage）のテスト"""
        def test_take_damage_with_defense_calculation(self, monster):
            """防御力を考慮したダメージ計算が正しく行われること"""
            monster.spawn(Coordinate(0, 0))
            monster.clear_events()
            
            # raw_damage(30) - defense(15) = 15 damage (回避しないようにパッチ)
            with patch('random.random', return_value=0.5):
                monster.take_damage(30, WorldTick(10))
            
            assert monster.hp.value == 100 - 15
            
            events = monster.get_events()
            assert any(isinstance(e, MonsterDamagedEvent) for e in events)
            damage_event = next(e for e in events if isinstance(e, MonsterDamagedEvent))
            assert damage_event.damage == 15

        def test_take_damage_minimum_guarantee(self, monster):
            """防御力が高くても最低1ダメージは受けること"""
            monster.spawn(Coordinate(0, 0))
            
            # raw_damage(10) < defense(15), should be 1 damage
            with patch('random.random', return_value=0.5):
                monster.take_damage(10, WorldTick(10))
            
            assert monster.hp.value == 99

        def test_take_damage_evaded(self, monster):
            """回避率に基づいてダメージを回避できること"""
            monster.spawn(Coordinate(0, 0))
            monster.clear_events()
            
            # evasion_rate=0.03 なので 0.02 で回避成功
            with patch('random.random', return_value=0.02):
                monster.take_damage(100, WorldTick(10))
            
            assert monster.hp.value == 100 # ダメージなし
            events = monster.get_events()
            assert any(isinstance(e, MonsterEvadedEvent) for e in events)

        def test_take_damage_not_evaded(self, monster):
            """回避率に基づき回避に失敗した場合はダメージを受けること"""
            monster.spawn(Coordinate(0, 0))
            monster.clear_events()
            
            # evasion_rate=0.03 なので 0.04 で回避失敗
            with patch('random.random', return_value=0.04):
                monster.take_damage(30, WorldTick(10))
            
            assert monster.hp.value == 85 # 30 - 15 = 15 damage
            events = monster.get_events()
            assert not any(isinstance(e, MonsterEvadedEvent) for e in events)
            assert any(isinstance(e, MonsterDamagedEvent) for e in events)

        def test_take_damage_not_spawned_raises_error(self, monster):
            """出現前のモンスターがダメージを受けるとエラーが発生する"""
            with pytest.raises(MonsterNotSpawnedException):
                monster.take_damage(10, WorldTick(10))

        def test_take_damage_already_dead_raises_error(self, monster):
            """死亡しているモンスターがダメージを受けるとエラーが発生する"""
            monster.spawn(Coordinate(0, 0))
            # オーバーキルで死亡させる
            with patch('random.random', return_value=0.5):
                monster.take_damage(200, WorldTick(10))
            
            # 死亡状態なので MonsterAlreadyDeadException が発生する
            with pytest.raises(MonsterAlreadyDeadException):
                monster.take_damage(10, WorldTick(20))

    class TestDeath:
        """死亡のテスト"""
        def test_death_by_damage(self, monster, monster_template):
            """HPが0になると死亡し、報酬イベントが発行されること"""
            monster.spawn(Coordinate(1, 2, 3))
            current_tick = WorldTick(100)
            
            # 115ダメージ = (115 - 15 defense) = 100 damage (HP 100 -> 0)
            with patch('random.random', return_value=0.5):
                monster.take_damage(115, current_tick)
            
            assert monster.status == MonsterStatusEnum.DEAD
            assert monster.coordinate is None
            assert monster.last_death_tick == current_tick
            
            events = monster.get_events()
            die_event = next(e for e in events if isinstance(e, MonsterDiedEvent))
            assert die_event.respawn_tick == 200 # 100 + 100
            assert die_event.exp == monster_template.reward_info.exp
            assert die_event.gold == monster_template.reward_info.gold
            assert die_event.loot_table_id == monster_template.reward_info.loot_table_id

    class TestRespawn:
        """リスポーン（Respawn）のテスト"""
        def test_respawn_success(self, monster):
            """リスポーン間隔を満たしていればリスポーンが成功する"""
            monster.spawn(Coordinate(0, 0))
            with patch('random.random', return_value=0.5):
                monster.take_damage(200, WorldTick(100))
            monster.clear_events()
            
            new_coord = Coordinate(5, 5, 0)
            # 間隔は100なので、tick 200ならOK
            monster.respawn(new_coord, WorldTick(200))
            
            assert monster.status == MonsterStatusEnum.ALIVE
            assert monster.hp.value == 100
            assert monster.mp.value == 50
            assert monster.coordinate == new_coord
            assert monster.last_death_tick is None
            
            events = monster.get_events()
            assert any(isinstance(e, MonsterRespawnedEvent) for e in events)

        def test_respawn_too_early_raises_error(self, monster):
            """リスポーン間隔を満たしていない場合はエラーが発生する"""
            monster.spawn(Coordinate(0, 0))
            with patch('random.random', return_value=0.5):
                monster.take_damage(200, WorldTick(100))
            
            with pytest.raises(MonsterRespawnIntervalNotMetException):
                monster.respawn(Coordinate(0, 0), WorldTick(150))

        def test_respawn_not_dead_raises_error(self, monster):
            """生存しているモンスターをリスポーンさせようとするとエラーが発生する"""
            monster.spawn(Coordinate(0, 0))
            with pytest.raises(MonsterNotDeadException):
                monster.respawn(Coordinate(0, 0), WorldTick(200))

    class TestShouldRespawn:
        """リスポーン判定（ShouldRespawn）のテスト"""
        def test_should_respawn_conditions(self, monster):
            """リスポーン条件（死亡状態かつ時間経過）が正しく判定されること"""
            monster.spawn(Coordinate(0, 0))
            with patch('random.random', return_value=0.5):
                monster.take_damage(200, WorldTick(100))
            
            assert monster.should_respawn(WorldTick(150)) is False
            assert monster.should_respawn(WorldTick(200)) is True

        def test_should_respawn_no_auto_respawn(self, monster_template):
            """自動リスポーンが無効な場合は常にFalseを返すこと"""
            custom_respawn = RespawnInfo(respawn_interval_ticks=100, is_auto_respawn=False)
            template = MonsterTemplate(
                template_id=monster_template.template_id,
                name=monster_template.name,
                base_stats=monster_template.base_stats,
                reward_info=monster_template.reward_info,
                respawn_info=custom_respawn,
                race=monster_template.race,
                faction=monster_template.faction,
                description=monster_template.description
            )
            monster = MonsterAggregate.create(MonsterId.create(1), template, WorldObjectId.create(1))
            monster.spawn(Coordinate(0, 0))
            with patch('random.random', return_value=0.5):
                monster.take_damage(200, WorldTick(100))
            
            assert monster.should_respawn(WorldTick(300)) is False

    class TestRecoveryAndRegeneration:
        """回復と自然回復のテスト"""
        def test_heal_hp_success(self, monster):
            """HPの回復が成功し、イベントが発行されること"""
            monster.spawn(Coordinate(0, 0))
            with patch('random.random', return_value=0.5):
                monster.take_damage(50, WorldTick(10))
            monster.clear_events()

            monster.heal_hp(30)
            assert monster.hp.value == 95 # 100 - (50 - 15 defense) + 30 = 100 - 35 + 30 = 95
            
            events = monster.get_events()
            assert any(isinstance(e, MonsterHealedEvent) for e in events)
            healed_event = next(e for e in events if isinstance(e, MonsterHealedEvent))
            assert healed_event.amount == 30
            assert healed_event.current_hp == 95

        def test_recover_mp_success(self, monster):
            """MPの回復が成功し、イベントが発行されること"""
            monster.spawn(Coordinate(0, 0))
            monster.use_mp(40)
            monster.clear_events()

            monster.recover_mp(20)
            assert monster.mp.value == 30 # 50 - 40 + 20
            
            events = monster.get_events()
            assert any(isinstance(e, MonsterMpRecoveredEvent) for e in events)
            recovered_event = next(e for e in events if isinstance(e, MonsterMpRecoveredEvent))
            assert recovered_event.amount == 20
            assert recovered_event.current_mp == 30

        def test_on_tick_regeneration(self, monster):
            """on_tickによってHPとMPが微量回復すること"""
            monster.spawn(Coordinate(0, 0))
            with patch('random.random', return_value=0.5):
                monster.take_damage(50, WorldTick(10))
            monster.use_mp(40)
            monster.clear_events()

            # max_hp=100, max_mp=50 なので hp_regen=1, mp_regen=1 (1% or min 1)
            monster.on_tick(WorldTick(11))
            
            assert monster.hp.value == 66 # 100 - (50 - 15) + 1 = 66
            assert monster.mp.value == 11

    class TestMpUsage:
        """MP消費のテスト"""
        def test_use_mp_success(self, monster):
            """MPの消費が成功すること"""
            monster.spawn(Coordinate(0, 0))
            monster.use_mp(20)
            assert monster.mp.value == 30

        def test_use_mp_insufficient_raises_error(self, monster):
            """MPが不足している場合にエラーが発生すること"""
            monster.spawn(Coordinate(0, 0))
            with pytest.raises(MonsterInsufficientMpException):
                monster.use_mp(60)

        def test_use_mp_not_alive_raises_error(self, monster):
            """生存していないモンスターがMPを消費しようとするとエラーが発生すること"""
            # 初期状態はDEAD
            with pytest.raises(MonsterAlreadyDeadException):
                monster.use_mp(10)
