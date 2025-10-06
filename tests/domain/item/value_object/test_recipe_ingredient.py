import pytest
from src.domain.item.value_object.recipe_ingredient import RecipeIngredient
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.exception import QuantityValidationException


class TestRecipeIngredient:
    """RecipeIngredient値オブジェクトのテスト"""

    @pytest.fixture
    def sample_item_spec_id(self):
        """テスト用のItemSpecIdを作成"""
        return ItemSpecId(1)

    def test_create_valid_recipe_ingredient(self, sample_item_spec_id):
        """正常なRecipeIngredient作成のテスト"""
        ingredient = RecipeIngredient(
            item_spec_id=sample_item_spec_id,
            quantity=5
        )
        assert ingredient.item_spec_id == sample_item_spec_id
        assert ingredient.quantity == 5

    def test_create_with_minimum_quantity(self, sample_item_spec_id):
        """最小数量（1）での作成テスト"""
        ingredient = RecipeIngredient(
            item_spec_id=sample_item_spec_id,
            quantity=1
        )
        assert ingredient.quantity == 1

    def test_invalid_quantity_zero(self, sample_item_spec_id):
        """無効な数量（0）のテスト"""
        with pytest.raises(QuantityValidationException) as exc_info:
            RecipeIngredient(
                item_spec_id=sample_item_spec_id,
                quantity=0
            )
        assert "Recipe ingredient: quantity must be positive, got 0" in str(exc_info.value)

    def test_invalid_quantity_negative(self, sample_item_spec_id):
        """無効な数量（負の値）のテスト"""
        with pytest.raises(QuantityValidationException) as exc_info:
            RecipeIngredient(
                item_spec_id=sample_item_spec_id,
                quantity=-1
            )
        assert "Recipe ingredient: quantity must be positive, got -1" in str(exc_info.value)

    def test_str_representation(self, sample_item_spec_id):
        """文字列表現のテスト"""
        ingredient = RecipeIngredient(
            item_spec_id=sample_item_spec_id,
            quantity=3
        )
        expected_str = f"{sample_item_spec_id} x3"
        assert str(ingredient) == expected_str

    def test_equality_same_ingredients(self, sample_item_spec_id):
        """同じ材料の等価性テスト"""
        ingredient1 = RecipeIngredient(
            item_spec_id=sample_item_spec_id,
            quantity=5
        )
        ingredient2 = RecipeIngredient(
            item_spec_id=sample_item_spec_id,
            quantity=5
        )
        assert ingredient1 == ingredient2

    def test_equality_different_spec_id(self, sample_item_spec_id):
        """異なるスペックIDでの等価性テスト"""
        ingredient1 = RecipeIngredient(
            item_spec_id=sample_item_spec_id,
            quantity=5
        )
        different_spec_id = ItemSpecId(2)
        ingredient2 = RecipeIngredient(
            item_spec_id=different_spec_id,
            quantity=5
        )
        assert ingredient1 != ingredient2

    def test_equality_different_quantity(self, sample_item_spec_id):
        """異なる数量での等価性テスト"""
        ingredient1 = RecipeIngredient(
            item_spec_id=sample_item_spec_id,
            quantity=5
        )
        ingredient2 = RecipeIngredient(
            item_spec_id=sample_item_spec_id,
            quantity=3
        )
        assert ingredient1 != ingredient2

    def test_equality_different_type(self, sample_item_spec_id):
        """異なる型との等価性テスト"""
        ingredient = RecipeIngredient(
            item_spec_id=sample_item_spec_id,
            quantity=5
        )
        assert ingredient != "not an ingredient"
        assert ingredient != 42

    def test_hash_consistency(self, sample_item_spec_id):
        """ハッシュの一貫性テスト"""
        ingredient1 = RecipeIngredient(
            item_spec_id=sample_item_spec_id,
            quantity=5
        )
        ingredient2 = RecipeIngredient(
            item_spec_id=sample_item_spec_id,
            quantity=5
        )

        assert hash(ingredient1) == hash(ingredient2)

        # setで重複を除去できる
        ingredients = {ingredient1, ingredient2}
        assert len(ingredients) == 1

    def test_immutable(self, sample_item_spec_id):
        """不変性のテスト"""
        ingredient = RecipeIngredient(
            item_spec_id=sample_item_spec_id,
            quantity=5
        )

        # frozen=Trueなので属性の直接変更は不可
        with pytest.raises(AttributeError):
            ingredient.quantity = 10

        with pytest.raises(AttributeError):
            ingredient.item_spec_id = ItemSpecId(999)
