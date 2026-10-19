import pytest

from ai_rpg_world.domain.player.exception.player_exceptions import BaseStatsValidationException
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor


class TestBaseStats:
    """BaseStats値オブジェクトのテスト"""

    def test_create_valid_base_stats(self):
        """有効なパラメータでBaseStatsを作成できること"""
        base_stats = BaseStats(
            max_hp=100,
            max_mp=50,
            attack=10,
            defense=5,
            speed=8,
            critical_rate=0.05,
            evasion_rate=0.03
        )
        assert base_stats.max_hp == 100
        assert base_stats.max_mp == 50
        assert base_stats.attack == 10
        assert base_stats.defense == 5
        assert base_stats.speed == 8
        assert base_stats.critical_rate == 0.05
        assert base_stats.evasion_rate == 0.03

    def test_create_with_zero_values(self):
        """各ステータスが0の場合でも作成できること"""
        base_stats = BaseStats(
            max_hp=0,
            max_mp=0,
            attack=0,
            defense=0,
            speed=0,
            critical_rate=0.0,
            evasion_rate=0.0
        )
        assert base_stats.max_hp == 0
        assert base_stats.max_mp == 0
        assert base_stats.attack == 0
        assert base_stats.defense == 0
        assert base_stats.speed == 0
        assert base_stats.critical_rate == 0.0
        assert base_stats.evasion_rate == 0.0

    @pytest.mark.parametrize(
        "field, invalid_value, message",
        [
            pytest.param('max_hp', -1, 'max_hp must be greater than 0', id='test_create_with_negative_max_hp_raises_error'),
            pytest.param('max_mp', -10, 'max_mp must be greater than 0', id='test_create_with_negative_max_mp_raises_error'),
            pytest.param('attack', -5, 'attack must be greater than 0', id='test_create_with_negative_attack_raises_error'),
            pytest.param('defense', -2, 'defense must be greater than 0', id='test_create_with_negative_defense_raises_error'),
            pytest.param('speed', -3, 'speed must be greater than 0', id='test_create_with_negative_speed_raises_error'),
            pytest.param('critical_rate', -0.1, 'critical_rate must be between 0.0 and 1.0', id='test_create_with_negative_critical_rate_raises_error'),
            pytest.param('critical_rate', 1.5, 'critical_rate must be between 0.0 and 1.0', id='test_create_with_critical_rate_over_one_raises_error'),
            pytest.param('evasion_rate', -0.05, 'evasion_rate must be between 0.0 and 1.0', id='test_create_with_negative_evasion_rate_raises_error'),
            pytest.param('evasion_rate', 1.2, 'evasion_rate must be between 0.0 and 1.0', id='test_create_with_evasion_rate_over_one_raises_error'),
        ],
    )
    def test_rejects_invalid_base_stats_fields(self, field, invalid_value, message):
        """他項目が正常な入力で、指定項目の不正値を固有例外と文言で拒否する。"""
        values = {
            'max_hp': 100,
            'max_mp': 50,
            'attack': 10,
            'defense': 5,
            'speed': 8,
            'critical_rate': 0.05,
            'evasion_rate': 0.03,
        }
        values[field] = invalid_value
        with pytest.raises(BaseStatsValidationException, match=message):
            BaseStats(**values)

    def test_grow_with_valid_growth_factor(self):
        """有効な成長率でステータスが成長すること"""
        base_stats = BaseStats(
            max_hp=100,
            max_mp=50,
            attack=10,
            defense=5,
            speed=8,
            critical_rate=0.05,
            evasion_rate=0.03
        )

        growth_factor = StatGrowthFactor(
            hp_factor=1.0,
            mp_factor=0.8,
            attack_factor=0.9,
            defense_factor=0.7,
            speed_factor=0.6,
            critical_rate_factor=0.1,
            evasion_rate_factor=0.05
        )

        grown_stats = base_stats.grow(growth_factor)

        # 整数値のステータスは成長率+1倍されて切り捨て
        assert grown_stats.max_hp == int(100 * (1.0 + 1.0))  # 200
        assert grown_stats.max_mp == int(50 * (1.0 + 0.8))   # 90
        assert grown_stats.attack == int(10 * (1.0 + 0.9))    # 19
        assert grown_stats.defense == int(5 * (1.0 + 0.7))    # 8
        assert grown_stats.speed == int(8 * (1.0 + 0.6))      # 12

        # 確率値は加算され、1.0を超えない
        assert grown_stats.critical_rate == min(1.0, 0.05 + 0.1)  # 0.15
        assert grown_stats.evasion_rate == min(1.0, 0.03 + 0.05)   # 0.08

    def test_grow_with_critical_rate_capped_at_one(self):
        """critical_rateが1.0を超えないようキャップされること"""
        base_stats = BaseStats(
            max_hp=100,
            max_mp=50,
            attack=10,
            defense=5,
            speed=8,
            critical_rate=0.95,  # 高いcritical_rate
            evasion_rate=0.03
        )

        growth_factor = StatGrowthFactor(
            hp_factor=0.1,
            mp_factor=0.1,
            attack_factor=0.1,
            defense_factor=0.1,
            speed_factor=0.1,
            critical_rate_factor=0.1,  # これを加算すると1.05になる
            evasion_rate_factor=0.05
        )

        grown_stats = base_stats.grow(growth_factor)

        # critical_rateは1.0にキャップされる
        assert grown_stats.critical_rate == 1.0
        assert grown_stats.evasion_rate == 0.08  # 0.03 + 0.05

    def test_grow_with_evasion_rate_capped_at_one(self):
        """evasion_rateが1.0を超えないようキャップされること"""
        base_stats = BaseStats(
            max_hp=100,
            max_mp=50,
            attack=10,
            defense=5,
            speed=8,
            critical_rate=0.05,
            evasion_rate=0.97  # 高いevasion_rate
        )

        growth_factor = StatGrowthFactor(
            hp_factor=0.1,
            mp_factor=0.1,
            attack_factor=0.1,
            defense_factor=0.1,
            speed_factor=0.1,
            critical_rate_factor=0.1,
            evasion_rate_factor=0.1  # これを加算すると1.07になる
        )

        grown_stats = base_stats.grow(growth_factor)

        # evasion_rateは1.0にキャップされる
        assert grown_stats.evasion_rate == 1.0
        assert grown_stats.critical_rate == pytest.approx(0.15, rel=1e-7)  # 0.05 + 0.1

    def test_grow_with_zero_growth_factor(self):
        """成長率が0の場合、ステータスが変化しないこと"""
        base_stats = BaseStats(
            max_hp=100,
            max_mp=50,
            attack=10,
            defense=5,
            speed=8,
            critical_rate=0.05,
            evasion_rate=0.03
        )

        growth_factor = StatGrowthFactor(
            hp_factor=0.0,
            mp_factor=0.0,
            attack_factor=0.0,
            defense_factor=0.0,
            speed_factor=0.0,
            critical_rate_factor=0.0,
            evasion_rate_factor=0.0
        )

        grown_stats = base_stats.grow(growth_factor)

        # 全てのステータスが変化しない
        assert grown_stats.max_hp == 100
        assert grown_stats.max_mp == 50
        assert grown_stats.attack == 10
        assert grown_stats.defense == 5
        assert grown_stats.speed == 8
        assert grown_stats.critical_rate == 0.05
        assert grown_stats.evasion_rate == 0.03

    def test_grow_returns_new_instance(self):
        """成長した新しい値を返し、元の全7項目を変更しない。"""
        base_stats = BaseStats(
            max_hp=100,
            max_mp=50,
            attack=10,
            defense=5,
            speed=8,
            critical_rate=0.05,
            evasion_rate=0.03
        )

        growth_factor = StatGrowthFactor(
            hp_factor=0.1,
            mp_factor=0.1,
            attack_factor=0.1,
            defense_factor=0.1,
            speed_factor=0.1,
            critical_rate_factor=0.01,
            evasion_rate_factor=0.01
        )

        grown_stats = base_stats.grow(growth_factor)

        # 異なるインスタンスが返される
        assert grown_stats is not base_stats

        # 元のインスタンスは変更されていない
        assert base_stats.max_hp == 100
        assert grown_stats.max_hp == 110  # 100 * (1.0 + 0.1)

        assert (
            base_stats.max_hp, base_stats.max_mp, base_stats.attack,
            base_stats.defense, base_stats.speed,
            base_stats.critical_rate, base_stats.evasion_rate,
        ) == (100, 50, 10, 5, 8, 0.05, 0.03)
        assert (
            grown_stats.max_hp, grown_stats.max_mp, grown_stats.attack,
            grown_stats.defense, grown_stats.speed,
        ) == (110, 55, 11, 5, 8)
        assert grown_stats.critical_rate == pytest.approx(0.06, rel=1e-7)
        assert grown_stats.evasion_rate == pytest.approx(0.04, rel=1e-7)

    def test_equality(self):
        """等価性比較が正しく動作すること"""
        stats1 = BaseStats(
            max_hp=100, max_mp=50, attack=10, defense=5, speed=8,
            critical_rate=0.05, evasion_rate=0.03
        )
        stats2 = BaseStats(
            max_hp=100, max_mp=50, attack=10, defense=5, speed=8,
            critical_rate=0.05, evasion_rate=0.03
        )
        stats3 = BaseStats(
            max_hp=200, max_mp=50, attack=10, defense=5, speed=8,
            critical_rate=0.05, evasion_rate=0.03
        )

        assert stats1 == stats2
        assert stats1 != stats3
        assert stats1 != "not a stats"

    def test_hash(self):
        """ハッシュ値が正しく生成されること"""
        stats1 = BaseStats(
            max_hp=100, max_mp=50, attack=10, defense=5, speed=8,
            critical_rate=0.05, evasion_rate=0.03
        )
        stats2 = BaseStats(
            max_hp=100, max_mp=50, attack=10, defense=5, speed=8,
            critical_rate=0.05, evasion_rate=0.03
        )

        assert hash(stats1) == hash(stats2)

        # setで重複が除去されることを確認
        stats_set = {stats1, stats2}
        assert len(stats_set) == 1

    def test_immutability(self):
        """不変性が保たれていること"""
        base_stats = BaseStats(
            max_hp=100, max_mp=50, attack=10, defense=5, speed=8,
            critical_rate=0.05, evasion_rate=0.03
        )
        original_max_hp = base_stats.max_hp

        # 属性を直接変更しようとするとエラーになるはず
        with pytest.raises(AttributeError):
            base_stats.max_hp = 200

        # 元の値は変わっていないことを確認
        assert base_stats.max_hp == original_max_hp
