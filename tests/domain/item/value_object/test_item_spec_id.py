import pytest
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.exception.item_exception import ItemInstanceIdValidationException


class TestItemSpecId:
    """ItemSpecId値オブジェクトのテスト"""

    def test_create_valid_id(self):
        """正常なID作成のテスト"""
        template_id = ItemSpecId(1)
        assert template_id.value == 1

    def test_create_from_string(self):
        """文字列からのID作成のテスト"""
        template_id = ItemSpecId.create("123")
        assert template_id.value == 123

    def test_invalid_id_zero(self):
        """無効なID（0）のテスト"""
        with pytest.raises(ItemInstanceIdValidationException):
            ItemSpecId(0)

    def test_invalid_id_negative(self):
        """無効なID（負の値）のテスト"""
        with pytest.raises(ItemInstanceIdValidationException):
            ItemSpecId(-1)

    def test_invalid_string(self):
        """無効な文字列のテスト"""
        with pytest.raises(ItemInstanceIdValidationException):
            ItemSpecId.create("abc")

    def test_str_conversion(self):
        """文字列変換のテスト"""
        template_id = ItemSpecId(42)
        assert str(template_id) == "42"

    def test_int_conversion(self):
        """int変換のテスト"""
        template_id = ItemSpecId(42)
        assert int(template_id) == 42

    def test_equality(self):
        """等価性テスト"""
        id1 = ItemSpecId(1)
        id2 = ItemSpecId(1)
        id3 = ItemSpecId(2)

        assert id1 == id2
        assert id1 != id3
        assert id1 != "1"  # 異なる型とは等しくない

    def test_hash(self):
        """ハッシュテスト"""
        id1 = ItemSpecId(1)
        id2 = ItemSpecId(1)

        assert hash(id1) == hash(id2)

        # setで重複を除去できる
        ids = {id1, id2}
        assert len(ids) == 1
