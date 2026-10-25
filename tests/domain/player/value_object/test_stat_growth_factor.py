import math

import pytest

from ai_rpg_world.domain.player.exception.player_exceptions import StatGrowthFactorValidationException
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor


class TestStatGrowthFactor:
    """StatGrowthFactor値オブジェクトのテスト"""

    def test_create_valid_stat_growth_factor(self):
        """有効なパラメータでStatGrowthFactorを作成できること"""
        growth_factor = StatGrowthFactor(
            hp_factor=1.0,
            mp_factor=0.8,
            attack_factor=0.9,
            defense_factor=0.7,
            speed_factor=0.6,
            critical_rate_factor=0.1,
            evasion_rate_factor=0.05,
        )
        assert growth_factor.hp_factor == 1.0
        assert growth_factor.mp_factor == 0.8
        assert growth_factor.attack_factor == 0.9
        assert growth_factor.defense_factor == 0.7
        assert growth_factor.speed_factor == 0.6
        assert growth_factor.critical_rate_factor == 0.1
        assert growth_factor.evasion_rate_factor == 0.05

    @pytest.mark.parametrize(
        "field, invalid_value, message",
        [
            pytest.param(
                "hp_factor",
                -1.0,
                "hp_factor must be greater than or equal to 0",
                id="test_create_with_negative_hp_factor_raises_error",
            ),
            pytest.param(
                "mp_factor",
                -0.5,
                "mp_factor must be greater than or equal to 0",
                id="test_create_with_negative_mp_factor_raises_error",
            ),
            pytest.param(
                "attack_factor",
                -0.2,
                "attack_factor must be greater than or equal to 0",
                id="test_create_with_negative_attack_factor_raises_error",
            ),
            pytest.param(
                "defense_factor",
                -0.1,
                "defense_factor must be greater than or equal to 0",
                id="test_create_with_negative_defense_factor_raises_error",
            ),
            pytest.param(
                "speed_factor",
                -0.3,
                "speed_factor must be greater than or equal to 0",
                id="test_create_with_negative_speed_factor_raises_error",
            ),
            pytest.param(
                "critical_rate_factor",
                -0.1,
                "critical_rate_factor must be greater than or equal to 0",
                id="test_create_with_negative_critical_rate_factor_raises_error",
            ),
            pytest.param(
                "evasion_rate_factor",
                -0.05,
                "evasion_rate_factor must be greater than or equal to 0",
                id="test_create_with_negative_evasion_rate_factor_raises_error",
            ),
        ],
    )
    def test_rejects_negative_growth_factor_fields(self, field, invalid_value, message):
        """他項目が正常な入力で、指定項目の不正値を固有例外と文言で拒否する。"""
        values = {
            "hp_factor": 1.0,
            "mp_factor": 0.8,
            "attack_factor": 0.9,
            "defense_factor": 0.7,
            "speed_factor": 0.6,
            "critical_rate_factor": 0.1,
            "evasion_rate_factor": 0.05,
        }
        values[field] = invalid_value
        with pytest.raises(StatGrowthFactorValidationException, match=message):
            StatGrowthFactor(**values)

    def test_create_with_zero_hp_factor_allows_zero(self):
        """hp_factorが0の場合も作成できること"""
        growth_factor = StatGrowthFactor(
            hp_factor=0.0,
            mp_factor=0.8,
            attack_factor=0.9,
            defense_factor=0.7,
            speed_factor=0.6,
            critical_rate_factor=0.1,
            evasion_rate_factor=0.05,
        )
        assert growth_factor.hp_factor == 0.0

    def test_for_level_one(self):
        """レベル1の成長率が正しく計算されること"""
        growth_factor = StatGrowthFactor.for_level(1)
        expected_growth = 1.0 / math.sqrt(1)  # 1.0

        assert growth_factor.hp_factor == pytest.approx(expected_growth, rel=1e-7)
        assert growth_factor.mp_factor == pytest.approx(expected_growth, rel=1e-7)
        assert growth_factor.attack_factor == pytest.approx(expected_growth, rel=1e-7)
        assert growth_factor.defense_factor == pytest.approx(expected_growth, rel=1e-7)
        assert growth_factor.speed_factor == pytest.approx(expected_growth, rel=1e-7)
        assert growth_factor.critical_rate_factor == pytest.approx(expected_growth * 0.1, rel=1e-7)
        assert growth_factor.evasion_rate_factor == pytest.approx(expected_growth * 0.1, rel=1e-7)

    def test_for_level_two(self):
        """レベル2の成長率がレベル1より小さくなること"""
        growth_factor_1 = StatGrowthFactor.for_level(1)
        growth_factor_2 = StatGrowthFactor.for_level(2)

        expected_growth_2 = 1.0 / math.sqrt(2)  # 約0.707

        assert growth_factor_2.hp_factor == pytest.approx(expected_growth_2, rel=1e-7)
        # レベル2の方がレベル1より成長率が低いことを確認
        assert growth_factor_2.hp_factor < growth_factor_1.hp_factor

    def test_for_level_five(self):
        """レベル5の成長率がさらに小さくなること"""
        growth_factor_2 = StatGrowthFactor.for_level(2)
        growth_factor_5 = StatGrowthFactor.for_level(5)

        expected_growth_5 = 1.0 / math.sqrt(5)  # 約0.447

        assert growth_factor_5.hp_factor == pytest.approx(expected_growth_5, rel=1e-7)
        # レベル5の方がレベル2より成長率が低いことを確認
        assert growth_factor_5.hp_factor < growth_factor_2.hp_factor

    @pytest.mark.parametrize(
        "level, expected_growth, expected_rate",
        [
            pytest.param(1, 2.0, 0.2, id="original_level_one"),
            pytest.param(4, 1.0, 0.1, id="noninitial_level_four"),
        ],
    )
    def test_for_level_with_custom_base_growth_rate(self, level, expected_growth, expected_rate):
        """独自係数2を全7項目へ反映し、非初期レベルでは減衰も適用する。"""
        base_rate = 2.0
        growth_factor = StatGrowthFactor.for_level(level, base_growth_rate=base_rate)

        assert growth_factor.hp_factor == pytest.approx(expected_growth, rel=1e-7)
        assert (
            growth_factor.mp_factor,
            growth_factor.attack_factor,
            growth_factor.defense_factor,
            growth_factor.speed_factor,
        ) == pytest.approx((expected_growth,) * 4, rel=1e-7)
        assert (
            growth_factor.critical_rate_factor,
            growth_factor.evasion_rate_factor,
        ) == pytest.approx((expected_rate, expected_rate), rel=1e-7)

    def test_for_level_zero_raises_error(self):
        """levelが0の場合エラーが発生すること"""
        with pytest.raises(StatGrowthFactorValidationException, match="level must be greater than 0"):
            StatGrowthFactor.for_level(0)

    def test_for_level_negative_raises_error(self):
        """levelが負の値の場合エラーが発生すること"""
        with pytest.raises(StatGrowthFactorValidationException, match="level must be greater than 0"):
            StatGrowthFactor.for_level(-1)

    def test_growth_rate_decreases_with_level(self):
        """レベルが上がるにつれて成長率が減少することを確認"""
        growth_factors = [StatGrowthFactor.for_level(level) for level in range(1, 11)]

        # 各レベルで成長率が減少していることを確認
        for i in range(len(growth_factors) - 1):
            assert growth_factors[i + 1].hp_factor < growth_factors[i].hp_factor

    def test_equality(self):
        """等価性比較が正しく動作すること"""
        factor1 = StatGrowthFactor(
            hp_factor=1.0,
            mp_factor=0.8,
            attack_factor=0.9,
            defense_factor=0.7,
            speed_factor=0.6,
            critical_rate_factor=0.1,
            evasion_rate_factor=0.05,
        )
        factor2 = StatGrowthFactor(
            hp_factor=1.0,
            mp_factor=0.8,
            attack_factor=0.9,
            defense_factor=0.7,
            speed_factor=0.6,
            critical_rate_factor=0.1,
            evasion_rate_factor=0.05,
        )
        factor3 = StatGrowthFactor(
            hp_factor=1.5,
            mp_factor=0.8,
            attack_factor=0.9,
            defense_factor=0.7,
            speed_factor=0.6,
            critical_rate_factor=0.1,
            evasion_rate_factor=0.05,
        )

        assert factor1 == factor2
        assert factor1 != factor3
        assert factor1 != "not a factor"

    def test_hash(self):
        """ハッシュ値が正しく生成されること"""
        factor1 = StatGrowthFactor(
            hp_factor=1.0,
            mp_factor=0.8,
            attack_factor=0.9,
            defense_factor=0.7,
            speed_factor=0.6,
            critical_rate_factor=0.1,
            evasion_rate_factor=0.05,
        )
        factor2 = StatGrowthFactor(
            hp_factor=1.0,
            mp_factor=0.8,
            attack_factor=0.9,
            defense_factor=0.7,
            speed_factor=0.6,
            critical_rate_factor=0.1,
            evasion_rate_factor=0.05,
        )

        assert hash(factor1) == hash(factor2)

        # setで重複が除去されることを確認
        factor_set = {factor1, factor2}
        assert len(factor_set) == 1

    def test_immutability(self):
        """不変性が保たれていること"""
        growth_factor = StatGrowthFactor(
            hp_factor=1.0,
            mp_factor=0.8,
            attack_factor=0.9,
            defense_factor=0.7,
            speed_factor=0.6,
            critical_rate_factor=0.1,
            evasion_rate_factor=0.05,
        )
        original_hp_factor = growth_factor.hp_factor

        # 属性を直接変更しようとするとエラーになるはず
        with pytest.raises(AttributeError):
            growth_factor.hp_factor = 2.0

        # 元の値は変わっていないことを確認
        assert growth_factor.hp_factor == original_hp_factor
