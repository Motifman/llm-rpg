"""
MonsterLifecycleState のテスト

正常ケース・例外ケース・境界ケースの網羅的検証。
"""

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.value_object.monster_lifecycle_state import MonsterLifecycleState
from ai_rpg_world.domain.monster.value_object.monster_hp import MonsterHp
from ai_rpg_world.domain.monster.value_object.monster_mp import MonsterMp
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterStatusEnum
from ai_rpg_world.domain.monster.exception.monster_exceptions import (
    MonsterStatsValidationException,
    MonsterInsufficientMpException,
)


class TestMonsterLifecycleStateCreateForUnspawned:
    """create_for_unspawned のテスト"""

    def test_creates_dead_state_with_full_hp_mp(self):
        """未出現状態: DEAD, hp/mp 満タン, spawned_at_tick=None"""
        state = MonsterLifecycleState.create_for_unspawned(max_hp=100, max_mp=50)
        assert state.status == MonsterStatusEnum.DEAD
        assert state.hp.value == 100
        assert state.hp.max_hp == 100
        assert state.mp.value == 50
        assert state.mp.max_mp == 50
        assert state.last_death_tick is None
        assert state.spawned_at_tick is None
        assert state.hunger == 0.0
        assert state.starvation_timer == 0

    def test_creates_with_minimal_stats(self):
        """最小ステータス（max_hp=1, max_mp=0）"""
        state = MonsterLifecycleState.create_for_unspawned(max_hp=1, max_mp=0)
        assert state.hp.value == 1
        assert state.mp.value == 0


class TestMonsterLifecycleStateCreateForSpawned:
    """create_for_spawned のテスト"""

    def test_creates_alive_state_with_full_hp_mp(self):
        """スポーン状態: ALIVE, hp/mp 満タン"""
        tick = WorldTick(100)
        state = MonsterLifecycleState.create_for_spawned(
            max_hp=80,
            max_mp=40,
            spawned_at_tick=tick,
        )
        assert state.status == MonsterStatusEnum.ALIVE
        assert state.hp.value == 80
        assert state.mp.value == 40
        assert state.spawned_at_tick == tick
        assert state.last_death_tick is None
        assert state.hunger == 0.0
        assert state.starvation_timer == 0

    def test_creates_with_initial_hunger(self):
        """initial_hunger を指定"""
        tick = WorldTick(50)
        state = MonsterLifecycleState.create_for_spawned(
            max_hp=50,
            max_mp=25,
            spawned_at_tick=tick,
            initial_hunger=0.3,
        )
        assert state.hunger == 0.3

    def test_initial_hunger_clamped_to_valid_range(self):
        """initial_hunger が 0-1 外ならクランプ"""
        tick = WorldTick(50)
        state_high = MonsterLifecycleState.create_for_spawned(
            max_hp=50,
            max_mp=25,
            spawned_at_tick=tick,
            initial_hunger=1.5,
        )
        assert state_high.hunger == 1.0

        state_low = MonsterLifecycleState.create_for_spawned(
            max_hp=50,
            max_mp=25,
            spawned_at_tick=tick,
            initial_hunger=-0.1,
        )
        assert state_low.hunger == 0.0


class TestMonsterLifecycleStateValidation:
    """バリデーションのテスト"""

    def test_rejects_hunger_above_one(self):
        """hunger > 1.0 で例外"""
        hp = MonsterHp.create(100, 100)
        mp = MonsterMp.create(50, 50)
        with pytest.raises(MonsterStatsValidationException) as exc_info:
            MonsterLifecycleState(
                hp=hp,
                mp=mp,
                status=MonsterStatusEnum.ALIVE,
                last_death_tick=None,
                spawned_at_tick=WorldTick(0),
                hunger=1.1,
                starvation_timer=0,
            )
        assert "hunger" in str(exc_info.value).lower()

    def test_rejects_hunger_below_zero(self):
        """hunger < 0 で例外"""
        hp = MonsterHp.create(100, 100)
        mp = MonsterMp.create(50, 50)
        with pytest.raises(MonsterStatsValidationException) as exc_info:
            MonsterLifecycleState(
                hp=hp,
                mp=mp,
                status=MonsterStatusEnum.ALIVE,
                last_death_tick=None,
                spawned_at_tick=WorldTick(0),
                hunger=-0.1,
                starvation_timer=0,
            )
        assert "hunger" in str(exc_info.value).lower()

    def test_rejects_negative_starvation_timer(self):
        """starvation_timer < 0 で例外"""
        hp = MonsterHp.create(100, 100)
        mp = MonsterMp.create(50, 50)
        with pytest.raises(MonsterStatsValidationException) as exc_info:
            MonsterLifecycleState(
                hp=hp,
                mp=mp,
                status=MonsterStatusEnum.ALIVE,
                last_death_tick=None,
                spawned_at_tick=WorldTick(0),
                hunger=0.5,
                starvation_timer=-1,
            )
        assert "starvation_timer" in str(exc_info.value).lower()


class TestMonsterLifecycleStateApplyDamage:
    """apply_damage のテスト"""

    @pytest.fixture
    def alive_state(self) -> MonsterLifecycleState:
        return MonsterLifecycleState.create_for_spawned(
            max_hp=100,
            max_mp=50,
            spawned_at_tick=WorldTick(0),
        )

    def test_applies_damage_returns_new_instance(self, alive_state: MonsterLifecycleState):
        """ダメージ適用で新しいインスタンス、元は不変"""
        new_state = alive_state.apply_damage(30)
        assert new_state is not alive_state
        assert new_state.hp.value == 70
        assert alive_state.hp.value == 100

    def test_applies_damage_to_zero_hp(self, alive_state: MonsterLifecycleState):
        """ダメージで HP 0 になっても status は変わらない（集約が死亡処理）"""
        new_state = alive_state.apply_damage(100)
        assert new_state.hp.value == 0
        assert new_state.hp.is_alive() is False
        assert new_state.status == MonsterStatusEnum.ALIVE

    def test_rejects_negative_damage(self, alive_state: MonsterLifecycleState):
        """負のダメージで例外"""
        with pytest.raises(MonsterStatsValidationException) as exc_info:
            alive_state.apply_damage(-1)
        assert "negative" in str(exc_info.value).lower() or "Damage" in str(exc_info.value)


class TestMonsterLifecycleStateApplyHeal:
    """apply_heal のテスト"""

    @pytest.fixture
    def damaged_state(self) -> MonsterLifecycleState:
        state = MonsterLifecycleState.create_for_spawned(
            max_hp=100,
            max_mp=50,
            spawned_at_tick=WorldTick(0),
        )
        return state.apply_damage(40)

    def test_applies_heal_returns_new_instance(self, damaged_state: MonsterLifecycleState):
        """回復で新しいインスタンス"""
        new_state = damaged_state.apply_heal(20)
        assert new_state is not damaged_state
        assert new_state.hp.value == 80
        assert damaged_state.hp.value == 60

    def test_heal_clamped_to_max_hp(self, damaged_state: MonsterLifecycleState):
        """回復量が max_hp を超えてもクランプ"""
        new_state = damaged_state.apply_heal(100)
        assert new_state.hp.value == 100

    def test_rejects_negative_heal(self, damaged_state: MonsterLifecycleState):
        """負の回復で例外"""
        with pytest.raises(MonsterStatsValidationException):
            damaged_state.apply_heal(-1)


class TestMonsterLifecycleStateApplyMpRecovery:
    """apply_mp_recovery のテスト"""

    @pytest.fixture
    def mp_used_state(self) -> MonsterLifecycleState:
        state = MonsterLifecycleState.create_for_spawned(
            max_hp=100,
            max_mp=50,
            spawned_at_tick=WorldTick(0),
        )
        return state.apply_mp_use(20)

    def test_applies_mp_recovery(self, mp_used_state: MonsterLifecycleState):
        """MP 回復で新しいインスタンス"""
        new_state = mp_used_state.apply_mp_recovery(10)
        assert new_state.mp.value == 40
        assert mp_used_state.mp.value == 30

    def test_rejects_negative_recovery(self, mp_used_state: MonsterLifecycleState):
        """負の MP 回復で例外"""
        with pytest.raises(MonsterStatsValidationException):
            mp_used_state.apply_mp_recovery(-1)


class TestMonsterLifecycleStateApplyMpUse:
    """apply_mp_use のテスト"""

    @pytest.fixture
    def alive_state(self) -> MonsterLifecycleState:
        return MonsterLifecycleState.create_for_spawned(
            max_hp=100,
            max_mp=50,
            spawned_at_tick=WorldTick(0),
        )

    def test_applies_mp_use(self, alive_state: MonsterLifecycleState):
        """MP 消費で新しいインスタンス"""
        new_state = alive_state.apply_mp_use(15)
        assert new_state.mp.value == 35
        assert alive_state.mp.value == 50

    def test_insufficient_mp_raises(self, alive_state: MonsterLifecycleState):
        """MP 不足で MonsterInsufficientMpException"""
        with pytest.raises(MonsterInsufficientMpException):
            alive_state.apply_mp_use(60)


class TestMonsterLifecycleStateWithDeath:
    """with_death のテスト"""

    @pytest.fixture
    def alive_state(self) -> MonsterLifecycleState:
        return MonsterLifecycleState.create_for_spawned(
            max_hp=100,
            max_mp=50,
            spawned_at_tick=WorldTick(10),
        )

    def test_with_death_sets_status_and_tick(self, alive_state: MonsterLifecycleState):
        """死亡で status=DEAD, last_death_tick 設定"""
        tick = WorldTick(100)
        new_state = alive_state.with_death(tick)
        assert new_state.status == MonsterStatusEnum.DEAD
        assert new_state.last_death_tick == tick
        assert new_state.spawned_at_tick == WorldTick(10)
        assert alive_state.status == MonsterStatusEnum.ALIVE


class TestMonsterLifecycleStateWithSpawnReset:
    """with_spawn_reset のテスト"""

    @pytest.fixture
    def dead_state(self) -> MonsterLifecycleState:
        state = MonsterLifecycleState.create_for_spawned(
            max_hp=100,
            max_mp=50,
            spawned_at_tick=WorldTick(10),
        )
        return state.apply_damage(100).with_death(WorldTick(50))

    def test_with_spawn_reset_full_recovery(self, dead_state: MonsterLifecycleState):
        """リスポーンで HP/MP 満タン、飢餓リセット"""
        tick = WorldTick(150)
        new_state = dead_state.with_spawn_reset(
            max_hp=120,
            max_mp=60,
            spawned_at_tick=tick,
            initial_hunger=0.2,
        )
        assert new_state.status == MonsterStatusEnum.ALIVE
        assert new_state.hp.value == 120
        assert new_state.mp.value == 60
        assert new_state.spawned_at_tick == tick
        assert new_state.hunger == 0.2
        assert new_state.starvation_timer == 0
        assert new_state.last_death_tick is None


class TestMonsterLifecycleStateTickHunger:
    """tick_hunger のテスト"""

    @pytest.fixture
    def alive_state(self) -> MonsterLifecycleState:
        return MonsterLifecycleState.create_for_spawned(
            max_hp=100,
            max_mp=50,
            spawned_at_tick=WorldTick(0),
            initial_hunger=0.0,
        )

    def test_hunger_increases(self, alive_state: MonsterLifecycleState):
        """飢餓が増加"""
        new_state, should_starve = alive_state.tick_hunger(
            hunger_increase_per_tick=0.1,
            hunger_starvation_threshold=1.0,
            starvation_ticks=5,
        )
        assert new_state.hunger == 0.1
        assert should_starve is False
        assert new_state.starvation_timer == 0

    def test_hunger_clamped_to_one(self, alive_state: MonsterLifecycleState):
        """飢餓は 1.0 でクランプ"""
        state_high = MonsterLifecycleState(
            hp=alive_state.hp,
            mp=alive_state.mp,
            status=alive_state.status,
            last_death_tick=alive_state.last_death_tick,
            spawned_at_tick=alive_state.spawned_at_tick,
            hunger=0.95,
            starvation_timer=0,
        )
        new_state, _ = state_high.tick_hunger(
            hunger_increase_per_tick=0.1,
            hunger_starvation_threshold=1.0,
            starvation_ticks=5,
        )
        assert new_state.hunger == 1.0

    def test_starvation_timer_increments_when_at_threshold(self, alive_state: MonsterLifecycleState):
        """閾値以上で starvation_timer が増加"""
        state_at_threshold = MonsterLifecycleState(
            hp=alive_state.hp,
            mp=alive_state.mp,
            status=alive_state.status,
            last_death_tick=alive_state.last_death_tick,
            spawned_at_tick=alive_state.spawned_at_tick,
            hunger=0.99,
            starvation_timer=0,
        )
        new_state, should_starve = state_at_threshold.tick_hunger(
            hunger_increase_per_tick=0.1,
            hunger_starvation_threshold=1.0,
            starvation_ticks=3,
        )
        assert new_state.hunger == 1.0
        assert new_state.starvation_timer == 1
        assert should_starve is False

    def test_should_starve_true_after_starvation_ticks(self, alive_state: MonsterLifecycleState):
        """starvation_ticks 経過で should_starve=True"""
        state_near_death = MonsterLifecycleState(
            hp=alive_state.hp,
            mp=alive_state.mp,
            status=alive_state.status,
            last_death_tick=alive_state.last_death_tick,
            spawned_at_tick=alive_state.spawned_at_tick,
            hunger=1.0,
            starvation_timer=2,
        )
        new_state, should_starve = state_near_death.tick_hunger(
            hunger_increase_per_tick=0.1,
            hunger_starvation_threshold=1.0,
            starvation_ticks=3,
        )
        assert new_state.starvation_timer == 3
        assert should_starve is True

    def test_disabled_starvation_returns_unchanged(self, alive_state: MonsterLifecycleState):
        """starvation_ticks == 0 のとき変化なし（飢餓無効）"""
        new_state, should_starve = alive_state.tick_hunger(
            hunger_increase_per_tick=0.1,
            hunger_starvation_threshold=1.0,
            starvation_ticks=0,
        )
        assert new_state is alive_state
        assert should_starve is False

    def test_rejects_negative_starvation_ticks(self, alive_state: MonsterLifecycleState):
        """starvation_ticks < 0 で例外"""
        with pytest.raises(MonsterStatsValidationException) as exc_info:
            alive_state.tick_hunger(
                hunger_increase_per_tick=0.1,
                hunger_starvation_threshold=1.0,
                starvation_ticks=-1,
            )
        assert "starvation_ticks" in str(exc_info.value).lower()

    def test_rejects_negative_hunger_increase(self, alive_state: MonsterLifecycleState):
        """hunger_increase_per_tick < 0 で例外"""
        with pytest.raises(MonsterStatsValidationException) as exc_info:
            alive_state.tick_hunger(
                hunger_increase_per_tick=-0.1,
                hunger_starvation_threshold=1.0,
                starvation_ticks=5,
            )
        assert "hunger_increase_per_tick" in str(exc_info.value).lower()

    def test_rejects_threshold_below_zero(self, alive_state: MonsterLifecycleState):
        """hunger_starvation_threshold < 0 で例外"""
        with pytest.raises(MonsterStatsValidationException) as exc_info:
            alive_state.tick_hunger(
                hunger_increase_per_tick=0.1,
                hunger_starvation_threshold=-0.1,
                starvation_ticks=5,
            )
        assert "hunger_starvation_threshold" in str(exc_info.value).lower()

    def test_rejects_threshold_above_one(self, alive_state: MonsterLifecycleState):
        """hunger_starvation_threshold > 1.0 で例外"""
        with pytest.raises(MonsterStatsValidationException) as exc_info:
            alive_state.tick_hunger(
                hunger_increase_per_tick=0.1,
                hunger_starvation_threshold=1.5,
                starvation_ticks=5,
            )
        assert "hunger_starvation_threshold" in str(exc_info.value).lower()

    def test_zero_hunger_increase_returns_unchanged(self, alive_state: MonsterLifecycleState):
        """hunger_increase_per_tick == 0 のとき変化なし（飢餓無効）"""
        new_state, should_starve = alive_state.tick_hunger(
            hunger_increase_per_tick=0.0,
            hunger_starvation_threshold=1.0,
            starvation_ticks=5,
        )
        assert new_state is alive_state
        assert should_starve is False

    def test_timer_resets_when_below_threshold(self, alive_state: MonsterLifecycleState):
        """閾値未満に戻ると starvation_timer がリセット"""
        state_above = MonsterLifecycleState(
            hp=alive_state.hp,
            mp=alive_state.mp,
            status=alive_state.status,
            last_death_tick=alive_state.last_death_tick,
            spawned_at_tick=alive_state.spawned_at_tick,
            hunger=0.6,
            starvation_timer=2,
        )
        new_state, _ = state_above.tick_hunger(
            hunger_increase_per_tick=0.05,
            hunger_starvation_threshold=1.0,
            starvation_ticks=5,
        )
        assert new_state.hunger == 0.65
        assert new_state.starvation_timer == 0


class TestMonsterLifecycleStateDecreaseHunger:
    """decrease_hunger のテスト"""

    @pytest.fixture
    def hungry_state(self) -> MonsterLifecycleState:
        return MonsterLifecycleState.create_for_spawned(
            max_hp=100,
            max_mp=50,
            spawned_at_tick=WorldTick(0),
            initial_hunger=0.8,
        )

    def test_decreases_hunger(self, hungry_state: MonsterLifecycleState):
        """飢餓が減少"""
        new_state = hungry_state.decrease_hunger(0.3)
        assert new_state.hunger == 0.5
        assert new_state.starvation_timer == 0

    def test_decrease_clamped_to_zero(self, hungry_state: MonsterLifecycleState):
        """飢餓は 0 でクランプ"""
        new_state = hungry_state.decrease_hunger(1.0)
        assert new_state.hunger == 0.0

    def test_zero_or_negative_amount_returns_self(self, hungry_state: MonsterLifecycleState):
        """amount <= 0 のとき同一インスタンス"""
        assert hungry_state.decrease_hunger(0.0) is hungry_state
        assert hungry_state.decrease_hunger(-0.1) is hungry_state


class TestMonsterLifecycleStateImmutability:
    """不変性のテスト"""

    def test_all_mutations_return_new_instance(self):
        """すべての変更メソッドが新しいインスタンスを返す"""
        state = MonsterLifecycleState.create_for_spawned(
            max_hp=100,
            max_mp=50,
            spawned_at_tick=WorldTick(0),
        )
        assert state.apply_damage(1) is not state
        assert state.apply_heal(0) is not state
        assert state.apply_mp_recovery(0) is not state
        assert state.apply_mp_use(0) is not state
        assert state.with_death(WorldTick(1)) is not state
        assert state.decrease_hunger(0.1) is not state
        new_state, _ = state.tick_hunger(0.1, 1.0, 5)
        assert new_state is not state
