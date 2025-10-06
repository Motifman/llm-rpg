import pytest
from src.domain.item.value_object.item_instance_id import ItemInstanceId
from src.domain.item.exception.item_exception import ItemInstanceIdValidationException


class TestItemInstanceId:
    """ItemInstanceId値オブジェクトのテスト"""

    def test_create_valid_id(self):
        """正常なID作成のテスト"""
        item_id = ItemInstanceId(1)
        assert item_id.value == 1

    def test_create_from_string(self):
        """文字列からのID作成のテスト"""
        item_id = ItemInstanceId.create("123")
        assert item_id.value == 123

    def test_invalid_id_zero(self):
        """無効なID（0）のテスト"""
        with pytest.raises(ItemInstanceIdValidationException):
            ItemInstanceId(0)

    def test_invalid_id_negative(self):
        """無効なID（負の値）のテスト"""
        with pytest.raises(ItemInstanceIdValidationException):
            ItemInstanceId(-1)

    def test_invalid_string(self):
        """無効な文字列のテスト"""
        with pytest.raises(ItemInstanceIdValidationException):
            ItemInstanceId.create("abc")

    def test_str_conversion(self):
        """文字列変換のテスト"""
        item_id = ItemInstanceId(42)
        assert str(item_id) == "42"

    def test_int_conversion(self):
        """int変換のテスト"""
        item_id = ItemInstanceId(42)
        assert int(item_id) == 42

    def test_equality(self):
        """等価性テスト"""
        id1 = ItemInstanceId(1)
        id2 = ItemInstanceId(1)
        id3 = ItemInstanceId(2)

        assert id1 == id2
        assert id1 != id3
        assert id1 != "1"  # 異なる型とは等しくない

    def test_hash(self):
        """ハッシュテスト"""
        id1 = ItemInstanceId(1)
        id2 = ItemInstanceId(1)

        assert hash(id1) == hash(id2)

        # setで重複を除去できる
        ids = {id1, id2}
        assert len(ids) == 1
