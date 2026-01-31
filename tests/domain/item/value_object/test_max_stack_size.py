import pytest
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.exception import MaxStackSizeValidationException


class TestMaxStackSize:
    """MaxStackSize値オブジェクトのテスト"""

    def test_create_valid_stack_size(self):
        """正常なスタックサイズ作成のテスト"""
        stack_size = MaxStackSize(64)
        assert stack_size.value == 64

    def test_create_stack_size_one(self):
        """スタックサイズ1のテスト"""
        stack_size = MaxStackSize(1)
        assert stack_size.value == 1

    def test_invalid_stack_size_zero(self):
        """無効なスタックサイズ（0）のテスト"""
        with pytest.raises(MaxStackSizeValidationException):
            MaxStackSize(0)

    def test_invalid_stack_size_negative(self):
        """無効なスタックサイズ（負の値）のテスト"""
        with pytest.raises(MaxStackSizeValidationException):
            MaxStackSize(-1)

    def test_immutable(self):
        """不変性のテスト"""
        stack_size = MaxStackSize(10)
        with pytest.raises(AttributeError):
            stack_size.value = 20
