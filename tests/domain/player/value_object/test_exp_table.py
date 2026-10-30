import math

import pytest

from ai_rpg_world.domain.player.exception.player_exceptions import ExpTableValidationException
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable


class TestExpTable:
    """ExpTable値オブジェクトのテスト"""

    def test_create_valid_exp_table(self):
        """有効なパラメータでExpTableを作成できること"""
        exp_table = ExpTable(base_exp=100.0, exponent=1.5, level_offset=0.0)
        assert exp_table.base_exp == 100.0
        assert exp_table.exponent == 1.5
        assert exp_table.level_offset == 0.0

    def test_create_with_level_offset(self):
        """level_offsetを指定して作成できること"""
        exp_table = ExpTable(base_exp=50.0, exponent=2.0, level_offset=1.0)
        assert exp_table.base_exp == 50.0
        assert exp_table.exponent == 2.0
        assert exp_table.level_offset == 1.0

    @pytest.mark.parametrize(
        "field, invalid_value, message",
        [
            pytest.param(
                "base_exp",
                -1.0,
                "base_exp must be greater than 0",
                id="test_create_with_negative_base_exp_raises_error",
            ),
            pytest.param(
                "base_exp", 0.0, "base_exp must be greater than 0", id="test_create_with_zero_base_exp_raises_error"
            ),
            pytest.param(
                "exponent",
                -1.0,
                "exponent must be greater than 0",
                id="test_create_with_negative_exponent_raises_error",
            ),
            pytest.param(
                "exponent", 0.0, "exponent must be greater than 0", id="test_create_with_zero_exponent_raises_error"
            ),
        ],
    )
    def test_rejects_nonpositive_curve_parameters(self, field, invalid_value, message):
        """他項目が正常な入力で、指定項目の不正値を固有例外と文言で拒否する。"""
        values = {
            "base_exp": 100.0,
            "exponent": 1.5,
        }
        values[field] = invalid_value
        with pytest.raises(ExpTableValidationException, match=message):
            ExpTable(**values)

    def test_get_required_exp_for_level_one(self):
        """レベル1に必要な経験値は0であること"""
        exp_table = ExpTable(base_exp=100.0, exponent=1.5)
        assert exp_table.get_required_exp_for_level(1) == 0

    def test_get_required_exp_for_level_two(self):
        """レベル2に必要な経験値が正しく計算されること"""
        exp_table = ExpTable(base_exp=100.0, exponent=1.5)
        expected = int(100.0 * math.pow(1 + 0.0, 1.5))  # 100 * (1^1.5) = 100
        assert exp_table.get_required_exp_for_level(2) == expected

    def test_get_required_exp_for_level_three(self):
        """レベル3に必要な経験値が正しく計算されること"""
        exp_table = ExpTable(base_exp=100.0, exponent=1.5)
        # レベル3に到達するための累積経験値は282
        expected = int(100.0 * math.pow(2 + 0.0, 1.5))  # 100 * (2^1.5) = 100 * 2.828 = 282
        assert exp_table.get_required_exp_for_level(3) == expected

    def test_get_required_exp_with_level_offset(self):
        """level_offsetを考慮した経験値計算が正しいこと"""
        exp_table = ExpTable(base_exp=100.0, exponent=2.0, level_offset=1.0)
        # レベル2の場合: 100 * ((2-1+1)^2) = 100 * (2^2) = 400
        expected = int(100.0 * math.pow(2 - 1 + 1.0, 2.0))
        assert exp_table.get_required_exp_for_level(2) == expected

    def test_get_level_from_exp_zero(self):
        """経験値0の場合はレベル1であること"""
        exp_table = ExpTable(base_exp=100.0, exponent=1.5)
        assert exp_table.get_level_from_exp(0) == 1

    def test_get_level_from_exp_negative(self):
        """負の経験値の場合はレベル1であること"""
        exp_table = ExpTable(base_exp=100.0, exponent=1.5)
        assert exp_table.get_level_from_exp(-10) == 1

    def test_get_level_from_exp_level_two(self):
        """レベル2に到達する経験値の場合レベル2が返されること"""
        exp_table = ExpTable(base_exp=100.0, exponent=1.5)
        level_2_exp = exp_table.get_required_exp_for_level(2)
        assert exp_table.get_level_from_exp(level_2_exp) == 2

    def test_get_level_from_exp_between_levels(self):
        """レベル間の経験値の場合、正しいレベルが返されること"""
        exp_table = ExpTable(base_exp=100.0, exponent=1.5)
        level_2_exp = exp_table.get_required_exp_for_level(2)  # 100
        level_3_exp = exp_table.get_required_exp_for_level(3)  # 282

        # レベル2の経験値より少し多い場合
        assert exp_table.get_level_from_exp(level_2_exp + 1) == 2

        # レベル3の経験値より少し少ない場合
        assert exp_table.get_level_from_exp(level_3_exp - 1) == 2

    def test_get_level_from_exp_exact_level_three(self):
        """レベル3に到達する正確な経験値の場合レベル3が返されること"""
        exp_table = ExpTable(base_exp=100.0, exponent=1.5)
        level_3_exp = exp_table.get_required_exp_for_level(3)
        assert exp_table.get_level_from_exp(level_3_exp) == 3

    def test_get_level_from_exp_high_value(self):
        """累積経験値10000では到達可能な最大レベル22を返す。"""
        exp_table = ExpTable(base_exp=100.0, exponent=1.5)
        high_exp = 10000
        level = exp_table.get_level_from_exp(high_exp)
        assert level == 22
        required_exp = exp_table.get_required_exp_for_level(level)
        assert high_exp >= required_exp
        # 次のレベルに必要な経験値は現在のレベルより多いはず
        next_level_exp = exp_table.get_required_exp_for_level(level + 1)
        assert next_level_exp > required_exp
        assert high_exp < next_level_exp

    def test_equality(self):
        """等価性比較が正しく動作すること"""
        table1 = ExpTable(base_exp=100.0, exponent=1.5, level_offset=0.0)
        table2 = ExpTable(base_exp=100.0, exponent=1.5, level_offset=0.0)
        table3 = ExpTable(base_exp=200.0, exponent=1.5, level_offset=0.0)

        assert table1 == table2
        assert table1 != table3
        assert table1 != "not a table"

    def test_hash(self):
        """ハッシュ値が正しく生成されること"""
        table1 = ExpTable(base_exp=100.0, exponent=1.5, level_offset=0.0)
        table2 = ExpTable(base_exp=100.0, exponent=1.5, level_offset=0.0)

        assert hash(table1) == hash(table2)

        # setで重複が除去されることを確認
        table_set = {table1, table2}
        assert len(table_set) == 1

    def test_immutability(self):
        """不変性が保たれていること"""
        exp_table = ExpTable(base_exp=100.0, exponent=1.5, level_offset=0.0)
        original_base_exp = exp_table.base_exp

        # 属性を直接変更しようとするとエラーになるはず
        with pytest.raises(AttributeError):
            exp_table.base_exp = 200.0

        # 元の値は変わっていないことを確認
        assert exp_table.base_exp == original_base_exp
