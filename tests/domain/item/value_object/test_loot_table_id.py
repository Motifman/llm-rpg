import pytest
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId
from ai_rpg_world.domain.item.exception.item_exception import LootTableIdValidationException


class TestLootTableId:
    """LootTableId値オブジェクトのテスト"""

    def test_create_valid_id(self):
        """正常なID作成のテスト"""
        lid = LootTableId(1)
        assert lid.value == 1

    def test_create_from_string(self):
        """数値文字列からのID作成のテスト"""
        lid = LootTableId.create("123")
        assert lid.value == 123

    def test_create_from_int(self):
        """intからのcreateのテスト"""
        lid = LootTableId.create(42)
        assert lid.value == 42

    def test_invalid_id_zero(self):
        """無効なID（0）のテスト"""
        with pytest.raises(LootTableIdValidationException):
            LootTableId(0)

    def test_invalid_id_negative(self):
        """無効なID（負の値）のテスト"""
        with pytest.raises(LootTableIdValidationException):
            LootTableId(-1)

    def test_invalid_string_non_numeric(self):
        """非数値文字列のテスト"""
        with pytest.raises(LootTableIdValidationException):
            LootTableId.create("abc")

    def test_invalid_string_empty(self):
        """空文字列のテスト"""
        with pytest.raises(LootTableIdValidationException):
            LootTableId.create("")

    def test_str_conversion(self):
        """文字列変換のテスト"""
        lid = LootTableId(42)
        assert str(lid) == "42"

    def test_int_conversion(self):
        """int変換のテスト"""
        lid = LootTableId(42)
        assert int(lid) == 42

    def test_equality(self):
        """等価性テスト"""
        id1 = LootTableId(1)
        id2 = LootTableId(1)
        id3 = LootTableId(2)

        assert id1 == id2
        assert id1 != id3
        assert id1 != "1"

    def test_hash(self):
        """ハッシュテスト"""
        id1 = LootTableId(1)
        id2 = LootTableId(1)

        assert hash(id1) == hash(id2)
        ids = {id1, id2}
        assert len(ids) == 1
