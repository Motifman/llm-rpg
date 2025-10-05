import pytest
from src.domain.item.value_object.recipe_id import RecipeId
from src.domain.item.exception.item_exception import ItemInstanceIdValidationException


class TestRecipeId:
    """RecipeId値オブジェクトのテスト"""

    def test_create_valid_id(self):
        """正常なID作成のテスト"""
        recipe_id = RecipeId(1)
        assert recipe_id.value == 1

    def test_create_from_string(self):
        """文字列からのID作成のテスト"""
        recipe_id = RecipeId.create("123")
        assert recipe_id.value == 123

    def test_invalid_id_zero(self):
        """無効なID（0）のテスト"""
        with pytest.raises(ItemInstanceIdValidationException):
            RecipeId(0)

    def test_invalid_id_negative(self):
        """無効なID（負の値）のテスト"""
        with pytest.raises(ItemInstanceIdValidationException):
            RecipeId(-1)

    def test_invalid_string(self):
        """無効な文字列のテスト"""
        with pytest.raises(ItemInstanceIdValidationException):
            RecipeId.create("abc")

    def test_invalid_string_empty(self):
        """空文字列のテスト"""
        with pytest.raises(ItemInstanceIdValidationException):
            RecipeId.create("")

    def test_str_conversion(self):
        """文字列変換のテスト"""
        recipe_id = RecipeId(42)
        assert str(recipe_id) == "42"

    def test_int_conversion(self):
        """int変換のテスト"""
        recipe_id = RecipeId(42)
        assert int(recipe_id) == 42

    def test_equality(self):
        """等価性テスト"""
        id1 = RecipeId(1)
        id2 = RecipeId(1)
        id3 = RecipeId(2)

        assert id1 == id2
        assert id1 != id3
        assert id1 != "1"  # 異なる型とは等しくない

    def test_hash(self):
        """ハッシュテスト"""
        id1 = RecipeId(1)
        id2 = RecipeId(1)

        assert hash(id1) == hash(id2)

        # setで重複を除去できる
        ids = {id1, id2}
        assert len(ids) == 1

    def test_immutable(self):
        """不変性のテスト"""
        recipe_id = RecipeId(10)
        with pytest.raises(AttributeError):
            recipe_id.value = 20  # 直接変更不可

    def test_create_from_large_number(self):
        """大きな数字からの作成テスト"""
        large_id = RecipeId.create(999999)
        assert large_id.value == 999999

    def test_create_from_string_with_spaces(self):
        """空白を含む文字列からの作成テスト（int()で変換可能）"""
        recipe_id = RecipeId.create(" 123 ")
        assert recipe_id.value == 123

    def test_create_from_string_with_newlines(self):
        """改行を含む文字列からの作成テスト（int()で変換可能）"""
        recipe_id = RecipeId.create("123\n")
        assert recipe_id.value == 123
