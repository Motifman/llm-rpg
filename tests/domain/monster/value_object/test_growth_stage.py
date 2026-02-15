import pytest

from ai_rpg_world.domain.monster.value_object.growth_stage import GrowthStage, MAX_GROWTH_STAGES
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterTemplateValidationException


class TestGrowthStage:
    """GrowthStage 値オブジェクトのテスト"""

    class TestCreateSuccess:
        def test_create_success_minimal(self):
            """after_ticks=0, stats_multiplier=1.0 で作成できること"""
            stage = GrowthStage(after_ticks=0, stats_multiplier=1.0)
            assert stage.after_ticks == 0
            assert stage.stats_multiplier == 1.0

        def test_create_success_juvenile(self):
            """幼体段階（0.8 乗率）で作成できること"""
            stage = GrowthStage(after_ticks=0, stats_multiplier=0.8)
            assert stage.after_ticks == 0
            assert stage.stats_multiplier == 0.8

        def test_create_success_adult(self):
            """成体段階（100 tick 以降）で作成できること"""
            stage = GrowthStage(after_ticks=100, stats_multiplier=1.0)
            assert stage.after_ticks == 100
            assert stage.stats_multiplier == 1.0

        def test_create_success_boundary_multiplier(self):
            """乗率の境界値 0.01 と 2.0 で作成できること"""
            low = GrowthStage(after_ticks=0, stats_multiplier=0.01)
            high = GrowthStage(after_ticks=0, stats_multiplier=2.0)
            assert low.stats_multiplier == 0.01
            assert high.stats_multiplier == 2.0

        def test_create_success_with_flee_bias_and_allow_chase(self):
            """flee_bias_multiplier と allow_chase を指定して作成できること（幼体用）"""
            stage = GrowthStage(
                after_ticks=0,
                stats_multiplier=0.8,
                flee_bias_multiplier=1.5,
                allow_chase=False,
            )
            assert stage.flee_bias_multiplier == 1.5
            assert stage.allow_chase is False

        def test_create_success_flee_bias_boundary_low(self):
            """flee_bias_multiplier の境界値 0.1 で作成できること"""
            stage = GrowthStage(after_ticks=0, stats_multiplier=1.0, flee_bias_multiplier=0.1)
            assert stage.flee_bias_multiplier == 0.1

        def test_create_success_flee_bias_boundary_high(self):
            """flee_bias_multiplier の境界値 3.0 で作成できること"""
            stage = GrowthStage(after_ticks=0, stats_multiplier=1.0, flee_bias_multiplier=3.0)
            assert stage.flee_bias_multiplier == 3.0

    class TestCreateValidationFailure:
        def test_create_fail_negative_after_ticks(self):
            """after_ticks が負の場合は MonsterTemplateValidationException を投げること"""
            with pytest.raises(MonsterTemplateValidationException, match="after_ticks cannot be negative"):
                GrowthStage(after_ticks=-1, stats_multiplier=1.0)

        def test_create_fail_stats_multiplier_zero(self):
            """stats_multiplier が 0 の場合はエラーとなること"""
            with pytest.raises(MonsterTemplateValidationException, match="stats_multiplier must be between"):
                GrowthStage(after_ticks=0, stats_multiplier=0.0)

        def test_create_fail_stats_multiplier_negative(self):
            """stats_multiplier が負の場合はエラーとなること"""
            with pytest.raises(MonsterTemplateValidationException, match="stats_multiplier must be between"):
                GrowthStage(after_ticks=0, stats_multiplier=-0.5)

        def test_create_fail_stats_multiplier_over_two(self):
            """stats_multiplier が 2.0 を超える場合はエラーとなること"""
            with pytest.raises(MonsterTemplateValidationException, match="stats_multiplier must be between"):
                GrowthStage(after_ticks=0, stats_multiplier=2.01)

        def test_create_fail_flee_bias_out_of_range(self):
            """flee_bias_multiplier が 0.1〜3.0 の範囲外の場合はエラーとなること"""
            with pytest.raises(MonsterTemplateValidationException, match="flee_bias_multiplier must be between"):
                GrowthStage(after_ticks=0, stats_multiplier=1.0, flee_bias_multiplier=0.05)
            with pytest.raises(MonsterTemplateValidationException, match="flee_bias_multiplier must be between"):
                GrowthStage(after_ticks=0, stats_multiplier=1.0, flee_bias_multiplier=3.5)

    def test_max_growth_stages_constant(self):
        """MAX_GROWTH_STAGES が 4 であること"""
        assert MAX_GROWTH_STAGES == 4
