import pytest
from src.domain.player.value_object.player_inventory_id import PlayerInventoryId
from src.domain.player.exception.player_exceptions import PlayerInventoryIdValidationException


class TestPlayerInventoryId:
    """PlayerInventoryId値オブジェクトのテスト"""

    def test_create_valid_id(self):
        """有効なIDで作成できること"""
        inventory_id = PlayerInventoryId(1)
        assert inventory_id.value == 1

    def test_create_zero_id_raises_error(self):
        """0のIDは作成できないこと"""
        with pytest.raises(PlayerInventoryIdValidationException):
            PlayerInventoryId(0)

    def test_create_negative_id_raises_error(self):
        """負のIDは作成できないこと"""
        with pytest.raises(PlayerInventoryIdValidationException):
            PlayerInventoryId(-1)

    def test_create_from_int(self):
        """intから作成できること"""
        inventory_id = PlayerInventoryId.create(5)
        assert inventory_id.value == 5

    def test_create_from_valid_string(self):
        """有効な文字列から作成できること"""
        inventory_id = PlayerInventoryId.create("10")
        assert inventory_id.value == 10

    def test_create_from_invalid_string_raises_error(self):
        """無効な文字列からは作成できないこと"""
        with pytest.raises(PlayerInventoryIdValidationException):
            PlayerInventoryId.create("abc")

    def test_str_conversion(self):
        """文字列変換が正しく動作すること"""
        inventory_id = PlayerInventoryId(123)
        assert str(inventory_id) == "123"

    def test_int_conversion(self):
        """int変換が正しく動作すること"""
        inventory_id = PlayerInventoryId(456)
        assert int(inventory_id) == 456

    def test_equality(self):
        """等価性比較が正しく動作すること"""
        id1 = PlayerInventoryId(100)
        id2 = PlayerInventoryId(100)
        id3 = PlayerInventoryId(200)

        assert id1 == id2
        assert id1 != id3
        assert id1 != "not an id"

    def test_hash(self):
        """ハッシュ値が正しく生成されること"""
        id1 = PlayerInventoryId(100)
        id2 = PlayerInventoryId(100)

        assert hash(id1) == hash(id2)

        # setで重複が除去されることを確認
        id_set = {id1, id2}
        assert len(id_set) == 1
