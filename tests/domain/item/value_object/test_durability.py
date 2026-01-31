import pytest
from ai_rpg_world.domain.item.value_object.durability import Durability
from ai_rpg_world.domain.item.exception import DurabilityValidationException


class TestDurability:
    """Durability値オブジェクトのテスト"""

    def test_create_valid_durability(self):
        """正常な耐久度作成のテスト"""
        durability = Durability(max_value=100, current=50)
        assert durability.max_value == 100
        assert durability.current == 50
        assert not durability.is_broken

    def test_create_full_durability(self):
        """満タン耐久度のテスト"""
        durability = Durability(max_value=100, current=100)
        assert durability.current == 100
        assert not durability.is_broken

    def test_create_broken_durability(self):
        """破損状態の耐久度のテスト"""
        durability = Durability(max_value=100, current=0)
        assert durability.current == 0
        assert durability.is_broken

    def test_invalid_max_value_zero(self):
        """無効な最大値（0）のテスト"""
        with pytest.raises(DurabilityValidationException):
            Durability(max_value=0, current=0)

    def test_invalid_max_value_negative(self):
        """無効な最大値（負の値）のテスト"""
        with pytest.raises(DurabilityValidationException):
            Durability(max_value=-1, current=0)

    def test_invalid_current_negative(self):
        """無効な現在値（負の値）のテスト"""
        with pytest.raises(DurabilityValidationException):
            Durability(max_value=100, current=-1)

    def test_invalid_current_greater_than_max(self):
        """現在値が最大値を超える場合のテスト"""
        with pytest.raises(DurabilityValidationException):
            Durability(max_value=100, current=150)

    def test_use_success(self):
        """正常な使用のテスト"""
        durability = Durability(max_value=100, current=50)
        new_durability, success = durability.use(10)
        assert success is True
        assert new_durability.current == 40
        assert not new_durability.is_broken

    def test_use_to_zero(self):
        """0になる使用のテスト"""
        durability = Durability(max_value=100, current=5)
        new_durability, success = durability.use(5)
        assert success is True
        assert new_durability.current == 0
        assert new_durability.is_broken

    def test_use_beyond_zero(self):
        """0を下回る使用のテスト"""
        durability = Durability(max_value=100, current=3)
        new_durability, success = durability.use(10)
        assert success is True
        assert new_durability.current == 0
        assert new_durability.is_broken

    def test_use_already_broken(self):
        """既に破損している場合の使用テスト"""
        durability = Durability(max_value=100, current=0)
        new_durability, success = durability.use(1)
        assert success is False
        assert new_durability.current == 0
        assert new_durability.is_broken

    def test_use_default_amount(self):
        """デフォルト使用量のテスト"""
        durability = Durability(max_value=100, current=10)
        new_durability, success = durability.use()
        assert success is True
        assert new_durability.current == 9

    def test_repair(self):
        """修理のテスト"""
        durability = Durability(max_value=100, current=50)
        repaired_durability = durability.repair(20)
        assert repaired_durability.current == 70

    def test_repair_over_max(self):
        """最大値を超える修理のテスト"""
        durability = Durability(max_value=100, current=90)
        repaired_durability = durability.repair(20)
        assert repaired_durability.current == 100

    def test_repair_default_amount(self):
        """デフォルト修理量のテスト"""
        durability = Durability(max_value=100, current=50)
        repaired_durability = durability.repair()
        assert repaired_durability.current == 51

    def test_immutable(self):
        """不変であることのテスト"""
        durability = Durability(max_value=100, current=50)
        with pytest.raises(AttributeError):
            durability.current = 40  # 直接変更不可
