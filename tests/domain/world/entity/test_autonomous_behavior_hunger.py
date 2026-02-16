"""Phase 6: AutonomousBehaviorComponent の飢餓関連のテスト"""

import pytest
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent
from ai_rpg_world.domain.world.exception.behavior_exception import HungerValidationException


class TestAutonomousBehaviorComponentHunger:
    """飢餓パラメータと tick_hunger_and_starvation のテスト"""

    def test_hunger_defaults_when_disabled(self):
        """starvation_ticks=0 のとき飢餓は無効（デフォルト）"""
        comp = AutonomousBehaviorComponent(
            hunger=0.5,
            hunger_increase_per_tick=0.0,
            starvation_ticks=0,
        )
        assert comp.hunger == 0.5
        assert comp.tick_hunger_and_starvation() is False
        comp.add_hunger(0.1)
        assert comp.hunger == 0.5  # 変化しない（無効）
        comp.reduce_hunger(0.2)
        assert comp.hunger == 0.5  # 変化しない（無効）

    def test_add_hunger_increases_capped_at_one(self):
        """add_hunger は 1.0 でキャップされる"""
        comp = AutonomousBehaviorComponent(
            hunger=0.8,
            hunger_increase_per_tick=0.01,
            hunger_starvation_threshold=0.9,
            starvation_ticks=10,
        )
        comp.add_hunger(0.5)
        assert comp.hunger == 1.0

    def test_reduce_hunger_decreases_capped_at_zero(self):
        """reduce_hunger は 0.0 でフロアされる"""
        comp = AutonomousBehaviorComponent(
            hunger=0.3,
            hunger_increase_per_tick=0.01,
            starvation_ticks=10,
        )
        comp.reduce_hunger(0.5)
        assert comp.hunger == 0.0

    def test_tick_hunger_and_starvation_increases_hunger(self):
        """tick_hunger_and_starvation で飢餓が増加する"""
        comp = AutonomousBehaviorComponent(
            hunger=0.0,
            hunger_increase_per_tick=0.1,
            hunger_starvation_threshold=0.9,
            starvation_ticks=3,
        )
        assert comp.tick_hunger_and_starvation() is False
        assert comp.hunger == 0.1
        assert comp.starvation_timer == 0

    def test_tick_hunger_and_starvation_returns_true_when_starved(self):
        """閾値以上が starvation_ticks 続くと True を返す"""
        comp = AutonomousBehaviorComponent(
            hunger=0.85,
            hunger_increase_per_tick=0.1,
            hunger_starvation_threshold=0.8,
            starvation_ticks=3,
        )
        comp.starvation_timer = 0
        assert comp.tick_hunger_and_starvation() is False  # hunger 0.95, timer 1
        assert comp.tick_hunger_and_starvation() is False  # hunger 1.0, timer 2
        assert comp.tick_hunger_and_starvation() is True   # timer 3 → starved

    def test_tick_hunger_below_threshold_resets_timer(self):
        """閾値未満になると starvation_timer がリセットされる"""
        comp = AutonomousBehaviorComponent(
            hunger=0.85,
            hunger_increase_per_tick=0.1,
            hunger_starvation_threshold=0.95,
            starvation_ticks=5,
        )
        comp.tick_hunger_and_starvation()  # 0.95, timer 1
        comp.tick_hunger_and_starvation()  # 1.0, timer 2
        comp.reduce_hunger(0.2)            # 0.8 (< 0.95)
        assert comp.tick_hunger_and_starvation() is False  # 0.9 < 0.95 → timer リセット
        assert comp.starvation_timer == 0
        assert comp.tick_hunger_and_starvation() is False  # 1.0 >= 0.95 → timer 1
        assert comp.starvation_timer == 1

    def test_constructor_fail_hunger_out_of_range(self):
        """hunger が 0.0〜1.0 の範囲外の場合はエラー"""
        with pytest.raises(HungerValidationException, match="hunger must be between"):
            AutonomousBehaviorComponent(hunger=1.5, starvation_ticks=1)
        with pytest.raises(HungerValidationException, match="hunger must be between"):
            AutonomousBehaviorComponent(hunger=-0.1, starvation_ticks=1)

    def test_constructor_fail_starvation_threshold_out_of_range(self):
        """hunger_starvation_threshold が範囲外の場合はエラー"""
        with pytest.raises(HungerValidationException, match="hunger_starvation_threshold"):
            AutonomousBehaviorComponent(
                hunger=0.5,
                hunger_starvation_threshold=1.5,
                starvation_ticks=1,
            )

    def test_constructor_fail_starvation_ticks_negative(self):
        """starvation_ticks が負の場合はエラー"""
        with pytest.raises(HungerValidationException, match="starvation_ticks"):
            AutonomousBehaviorComponent(hunger=0.5, starvation_ticks=-1)

    def test_to_dict_includes_hunger_fields(self):
        """to_dict に飢餓関連フィールドが含まれること"""
        comp = AutonomousBehaviorComponent(
            hunger=0.3,
            hunger_increase_per_tick=0.01,
            hunger_starvation_threshold=0.8,
            starvation_ticks=20,
        )
        comp.starvation_timer = 5
        data = comp.to_dict()
        assert data["hunger"] == 0.3
        assert data["hunger_increase_per_tick"] == 0.01
        assert data["hunger_starvation_threshold"] == 0.8
        assert data["starvation_ticks"] == 20
        assert data["starvation_timer"] == 5
