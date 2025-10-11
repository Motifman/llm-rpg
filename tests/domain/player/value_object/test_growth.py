import pytest
from src.domain.player.value_object.growth import Growth
from src.domain.player.value_object.exp_table import ExpTable
from src.domain.player.exception.player_exceptions import GrowthValidationException


class TestGrowth:
    """Growth値オブジェクトのテスト"""

    def setup_method(self):
        """各テストメソッド実行前に共通のセットアップ"""
        self.exp_table = ExpTable(base_exp=100.0, exponent=1.5)

    def test_create_valid_growth(self):
        """有効なパラメータでGrowthを作成できること"""
        growth = Growth(level=1, total_exp=0, exp_table=self.exp_table)
        assert growth.level == 1
        assert growth.total_exp == 0
        assert growth.exp_table == self.exp_table

    def test_create_level_two_with_sufficient_exp(self):
        """レベル2に必要な経験値がある場合に作成できること"""
        required_exp = self.exp_table.get_required_exp_for_level(2)  # 100
        growth = Growth(level=2, total_exp=required_exp, exp_table=self.exp_table)
        assert growth.level == 2
        assert growth.total_exp == required_exp

    def test_create_with_negative_level_raises_error(self):
        """levelが負の値の場合エラーが発生すること"""
        with pytest.raises(GrowthValidationException, match="level must be greater than 0"):
            Growth(level=-1, total_exp=0, exp_table=self.exp_table)

    def test_create_with_zero_level_raises_error(self):
        """levelが0の場合エラーが発生すること"""
        with pytest.raises(GrowthValidationException, match="level must be greater than 0"):
            Growth(level=0, total_exp=0, exp_table=self.exp_table)

    def test_create_with_negative_total_exp_raises_error(self):
        """total_expが負の値の場合エラーが発生すること"""
        with pytest.raises(GrowthValidationException, match="total_exp must be greater than or equal to 0"):
            Growth(level=1, total_exp=-10, exp_table=self.exp_table)

    def test_create_with_insufficient_exp_for_level_raises_error(self):
        """指定レベルに必要な経験値が不足している場合エラーが発生すること"""
        # レベル2には100経験値が必要だが、50しかない場合
        with pytest.raises(GrowthValidationException, match="total_exp 50 is insufficient for level 2"):
            Growth(level=2, total_exp=50, exp_table=self.exp_table)

    def test_create_with_insufficient_exp_for_higher_level_raises_error(self):
        """高いレベルに必要な経験値が不足している場合エラーが発生すること"""
        # レベル5に必要な経験値を確認
        required_exp = self.exp_table.get_required_exp_for_level(5)
        insufficient_exp = required_exp - 1

        with pytest.raises(GrowthValidationException, match=f"total_exp {insufficient_exp} is insufficient for level 5"):
            Growth(level=5, total_exp=insufficient_exp, exp_table=self.exp_table)

    def test_gain_exp_zero_returns_same_growth_no_level_up(self):
        """経験値0を獲得した場合、同じGrowthが返されレベルアップしないこと"""
        growth = Growth(level=1, total_exp=0, exp_table=self.exp_table)
        new_growth, leveled_up = growth.gain_exp(0)

        assert new_growth.level == 1
        assert new_growth.total_exp == 0
        assert not leveled_up
        # 同じインスタンスではないことを確認（新しいインスタンスが返される）
        assert new_growth is not growth

    def test_gain_exp_small_amount_no_level_up(self):
        """少量の経験値を獲得してもレベルアップしない場合"""
        growth = Growth(level=1, total_exp=0, exp_table=self.exp_table)

        # レベル2に必要な経験値は100なので、50獲得してもレベルアップしない
        new_growth, leveled_up = growth.gain_exp(50)

        assert new_growth.level == 1
        assert new_growth.total_exp == 50
        assert not leveled_up

    def test_gain_exp_exact_amount_for_level_up(self):
        """レベルアップに必要な正確な経験値を獲得した場合レベルアップすること"""
        growth = Growth(level=1, total_exp=0, exp_table=self.exp_table)

        # レベル2に必要な経験値は100
        new_growth, leveled_up = growth.gain_exp(100)

        assert new_growth.level == 2
        assert new_growth.total_exp == 100
        assert leveled_up

    def test_gain_exp_more_than_needed_for_level_up(self):
        """レベルアップに必要な経験値を超えて獲得した場合レベルアップすること"""
        growth = Growth(level=1, total_exp=0, exp_table=self.exp_table)

        # レベル2に必要な経験値は100、150獲得
        new_growth, leveled_up = growth.gain_exp(150)

        assert new_growth.level == 2
        assert new_growth.total_exp == 150
        assert leveled_up

    def test_gain_exp_multiple_level_up(self):
        """一度に複数レベルアップする場合"""
        growth = Growth(level=1, total_exp=0, exp_table=self.exp_table)

        # レベル2: 100, レベル3: 282, 合計382経験値が必要
        # 400経験値を獲得
        new_growth, leveled_up = growth.gain_exp(400)

        assert new_growth.level == 3
        assert new_growth.total_exp == 400
        assert leveled_up

    def test_gain_exp_from_mid_level(self):
        """レベル2から経験値を獲得する場合"""
        # レベル2の状態からスタート
        level2_exp = self.exp_table.get_required_exp_for_level(2)  # 100
        growth = Growth(level=2, total_exp=level2_exp, exp_table=self.exp_table)

        # さらに182経験値獲得（レベル3に到達する分）
        additional_exp = 182
        new_growth, leveled_up = growth.gain_exp(additional_exp)

        assert new_growth.level == 3
        assert new_growth.total_exp == level2_exp + additional_exp
        assert leveled_up

    def test_gain_exp_negative_amount_raises_error(self):
        """負の経験値を獲得しようとした場合エラーが発生すること"""
        growth = Growth(level=1, total_exp=0, exp_table=self.exp_table)

        with pytest.raises(GrowthValidationException, match="exp_amount must be greater than or equal to 0"):
            growth.gain_exp(-10)

    def test_gain_exp_zero_from_higher_level(self):
        """高いレベルから経験値0を獲得する場合"""
        level3_exp = self.exp_table.get_required_exp_for_level(3)  # 282
        growth = Growth(level=3, total_exp=level3_exp, exp_table=self.exp_table)

        new_growth, leveled_up = growth.gain_exp(0)

        assert new_growth.level == 3
        assert new_growth.total_exp == level3_exp
        assert not leveled_up

    def test_gain_exp_to_reach_level_four(self):
        """レベル4に到達する経験値を獲得する場合"""
        level3_exp = self.exp_table.get_required_exp_for_level(3)  # 282
        growth = Growth(level=3, total_exp=level3_exp, exp_table=self.exp_table)

        # レベル4に必要な経験値 - レベル3の経験値
        level4_exp = self.exp_table.get_required_exp_for_level(4)
        additional_needed = level4_exp - level3_exp

        new_growth, leveled_up = growth.gain_exp(additional_needed)

        assert new_growth.level == 4
        assert new_growth.total_exp == level4_exp
        assert leveled_up

    def test_equality(self):
        """等価性比較が正しく動作すること"""
        growth1 = Growth(level=1, total_exp=0, exp_table=self.exp_table)
        growth2 = Growth(level=1, total_exp=0, exp_table=self.exp_table)
        growth3 = Growth(level=2, total_exp=100, exp_table=self.exp_table)

        assert growth1 == growth2
        assert growth1 != growth3
        assert growth1 != "not a growth"

    def test_hash(self):
        """ハッシュ値が正しく生成されること"""
        growth1 = Growth(level=1, total_exp=0, exp_table=self.exp_table)
        growth2 = Growth(level=1, total_exp=0, exp_table=self.exp_table)

        assert hash(growth1) == hash(growth2)

        # setで重複が除去されることを確認
        growth_set = {growth1, growth2}
        assert len(growth_set) == 1

    def test_immutability(self):
        """不変性が保たれていること"""
        growth = Growth(level=1, total_exp=0, exp_table=self.exp_table)
        original_level = growth.level

        # 属性を直接変更しようとするとエラーになるはず
        with pytest.raises(AttributeError):
            growth.level = 2

        # 元の値は変わっていないことを確認
        assert growth.level == original_level
