import pytest
from src.domain.player.value_object.stamina import Stamina
from src.domain.player.exception import StaminaValidationException


class TestStamina:
    """Stamina値オブジェクトのテスト"""

    def test_create_stamina_success(self):
        """正常作成のテスト"""
        stamina = Stamina.create(50, 100)
        assert stamina.value == 50
        assert stamina.max_stamina == 100

    def test_create_stamina_with_value_over_max(self):
        """最大値を超える値を指定した場合、値が制限される"""
        stamina = Stamina.create(150, 100)
        assert stamina.value == 100
        assert stamina.max_stamina == 100

    def test_create_stamina_with_negative_value(self):
        """負の値を指定した場合、値が制限される"""
        stamina = Stamina.create(-10, 100)
        assert stamina.value == 0
        assert stamina.max_stamina == 100

    def test_direct_instantiation_negative_max_stamina(self):
        """直接インスタンス化でmax_staminaが負の値の場合"""
        with pytest.raises(StaminaValidationException, match="max_staminaは0以上の値である必要があります"):
            Stamina(50, -10)

    def test_direct_instantiation_negative_value(self):
        """直接インスタンス化でvalueが負の値の場合"""
        with pytest.raises(StaminaValidationException, match="スタミナは0以上の値である必要があります"):
            Stamina(-10, 100)

    def test_direct_instantiation_value_over_max(self):
        """直接インスタンス化でvalueがmax_staminaを超える場合"""
        with pytest.raises(StaminaValidationException, match="スタミナはmax_stamina以下の値である必要があります"):
            Stamina(150, 100)

    def test_consume_success(self):
        """消費のテスト（正常系）"""
        stamina = Stamina.create(50, 100)
        consumed_stamina = stamina.consume(20)
        assert consumed_stamina.value == 30
        assert consumed_stamina.max_stamina == 100

    def test_consume_to_zero(self):
        """消費でスタミナが0になる場合"""
        stamina = Stamina.create(30, 100)
        consumed_stamina = stamina.consume(30)
        assert consumed_stamina.value == 0
        assert consumed_stamina.max_stamina == 100

    def test_consume_over_current_value(self):
        """現在のスタミナを超えて消費する場合、値が制限される"""
        stamina = Stamina.create(30, 100)
        consumed_stamina = stamina.consume(50)
        assert consumed_stamina.value == 0
        assert consumed_stamina.max_stamina == 100

    def test_consume_negative_amount(self):
        """消費量が負の値の場合"""
        stamina = Stamina.create(50, 100)
        with pytest.raises(StaminaValidationException, match="消費量は0以上の値である必要があります"):
            stamina.consume(-10)

    def test_recover_success(self):
        """回復のテスト（正常系）"""
        stamina = Stamina.create(30, 100)
        recovered_stamina = stamina.recover(20)
        assert recovered_stamina.value == 50
        assert recovered_stamina.max_stamina == 100

    def test_recover_over_max(self):
        """回復で最大値を超える場合"""
        stamina = Stamina.create(80, 100)
        recovered_stamina = stamina.recover(30)
        assert recovered_stamina.value == 100
        assert recovered_stamina.max_stamina == 100

    def test_recover_negative_amount(self):
        """回復量が負の値の場合"""
        stamina = Stamina.create(50, 100)
        with pytest.raises(StaminaValidationException, match="回復量は0以上の値である必要があります"):
            stamina.recover(-10)

    def test_can_consume_true(self):
        """消費可能かどうかのテスト（可能）"""
        stamina = Stamina.create(50, 100)
        assert stamina.can_consume(30) is True

    def test_can_consume_false(self):
        """消費可能かどうかのテスト（不可能）"""
        stamina = Stamina.create(20, 100)
        assert stamina.can_consume(30) is False

    def test_can_consume_exactly_current_value(self):
        """現在のスタミナと同量を消費可能かどうか"""
        stamina = Stamina.create(50, 100)
        assert stamina.can_consume(50) is True

    def test_can_consume_zero(self):
        """0を消費可能かどうか"""
        stamina = Stamina.create(0, 100)
        assert stamina.can_consume(0) is True

    def test_can_consume_negative_amount(self):
        """消費量が負の値の場合のエラー"""
        stamina = Stamina.create(50, 100)
        with pytest.raises(StaminaValidationException, match="消費量は0以上の値である必要があります"):
            stamina.can_consume(-10)

    def test_is_empty_false(self):
        """スタミナが空かどうかのテスト（空でない）"""
        stamina = Stamina.create(50, 100)
        assert stamina.is_empty() is False

    def test_is_empty_true(self):
        """スタミナが空かどうかのテスト（空）"""
        stamina = Stamina.create(0, 100)
        assert stamina.is_empty() is True

    def test_is_empty_negative_value(self):
        """スタミナが負の値の場合（空とみなされる）"""
        stamina = Stamina.create(-5, 100)
        assert stamina.is_empty() is True

    def test_is_full_false(self):
        """スタミナが最大値かどうかのテスト（最大でない）"""
        stamina = Stamina.create(50, 100)
        assert stamina.is_full() is False

    def test_is_full_true(self):
        """スタミナが最大値かどうかのテスト（最大）"""
        stamina = Stamina.create(100, 100)
        assert stamina.is_full() is True

    def test_get_percentage_normal(self):
        """パーセント取得のテスト（通常）"""
        stamina = Stamina.create(50, 100)
        assert stamina.get_percentage() == 0.5

    def test_get_percentage_zero_max(self):
        """最大スタミナが0の場合のパーセント取得"""
        stamina = Stamina.create(0, 0)
        assert stamina.get_percentage() == 0.0

    def test_get_percentage_zero_value(self):
        """スタミナが0の場合のパーセント取得"""
        stamina = Stamina.create(0, 100)
        assert stamina.get_percentage() == 0.0

    def test_get_percentage_full(self):
        """スタミナが最大の場合のパーセント取得"""
        stamina = Stamina.create(100, 100)
        assert stamina.get_percentage() == 1.0

    def test_str_representation(self):
        """文字列表現のテスト"""
        stamina = Stamina.create(75, 100)
        assert str(stamina) == "75/100"

    def test_equality_same_values(self):
        """等価性のテスト（同じ値）"""
        stamina1 = Stamina.create(50, 100)
        stamina2 = Stamina.create(50, 100)
        assert stamina1 == stamina2

    def test_equality_different_values(self):
        """等価性のテスト（異なる値）"""
        stamina1 = Stamina.create(50, 100)
        stamina2 = Stamina.create(30, 100)
        assert stamina1 != stamina2

    def test_equality_different_max(self):
        """等価性のテスト（異なる最大値）"""
        stamina1 = Stamina.create(50, 100)
        stamina2 = Stamina.create(50, 150)
        assert stamina1 != stamina2

    def test_equality_with_non_stamina(self):
        """異なる型のオブジェクトとの等価性"""
        stamina = Stamina.create(50, 100)
        assert stamina != "50/100"

    def test_hash_consistency(self):
        """ハッシュの一貫性テスト"""
        stamina1 = Stamina.create(50, 100)
        stamina2 = Stamina.create(50, 100)
        assert hash(stamina1) == hash(stamina2)

    def test_immutability(self):
        """不変性のテスト"""
        stamina = Stamina.create(50, 100)
        # メソッド呼び出し後も元のオブジェクトは変更されない
        stamina.consume(10)
        stamina.recover(10)
        assert stamina.value == 50
        assert stamina.max_stamina == 100