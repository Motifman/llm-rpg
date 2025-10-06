import pytest
from src.domain.item.value_object.recipe_result import RecipeResult
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.exception import QuantityValidationException


class TestRecipeResult:
    """RecipeResult値オブジェクトのテスト"""

    @pytest.fixture
    def sample_item_spec_id(self):
        """テスト用のItemSpecIdを作成"""
        return ItemSpecId(1)

    def test_create_valid_recipe_result(self, sample_item_spec_id):
        """正常なRecipeResult作成のテスト"""
        result = RecipeResult(
            item_spec_id=sample_item_spec_id,
            quantity=5
        )
        assert result.item_spec_id == sample_item_spec_id
        assert result.quantity == 5

    def test_create_with_minimum_quantity(self, sample_item_spec_id):
        """最小数量（1）での作成テスト"""
        result = RecipeResult(
            item_spec_id=sample_item_spec_id,
            quantity=1
        )
        assert result.quantity == 1

    def test_invalid_quantity_zero(self, sample_item_spec_id):
        """無効な数量（0）のテスト"""
        with pytest.raises(QuantityValidationException) as exc_info:
            RecipeResult(
                item_spec_id=sample_item_spec_id,
                quantity=0
            )
        assert "Recipe result: quantity must be positive, got 0" in str(exc_info.value)

    def test_invalid_quantity_negative(self, sample_item_spec_id):
        """無効な数量（負の値）のテスト"""
        with pytest.raises(QuantityValidationException) as exc_info:
            RecipeResult(
                item_spec_id=sample_item_spec_id,
                quantity=-1
            )
        assert "Recipe result: quantity must be positive, got -1" in str(exc_info.value)

    def test_str_representation(self, sample_item_spec_id):
        """文字列表現のテスト"""
        result = RecipeResult(
            item_spec_id=sample_item_spec_id,
            quantity=3
        )
        expected_str = f"{sample_item_spec_id} x3"
        assert str(result) == expected_str

    def test_equality_same_results(self, sample_item_spec_id):
        """同じ結果の等価性テスト"""
        result1 = RecipeResult(
            item_spec_id=sample_item_spec_id,
            quantity=5
        )
        result2 = RecipeResult(
            item_spec_id=sample_item_spec_id,
            quantity=5
        )
        assert result1 == result2

    def test_equality_different_spec_id(self, sample_item_spec_id):
        """異なるスペックIDでの等価性テスト"""
        result1 = RecipeResult(
            item_spec_id=sample_item_spec_id,
            quantity=5
        )
        different_spec_id = ItemSpecId(2)
        result2 = RecipeResult(
            item_spec_id=different_spec_id,
            quantity=5
        )
        assert result1 != result2

    def test_equality_different_quantity(self, sample_item_spec_id):
        """異なる数量での等価性テスト"""
        result1 = RecipeResult(
            item_spec_id=sample_item_spec_id,
            quantity=5
        )
        result2 = RecipeResult(
            item_spec_id=sample_item_spec_id,
            quantity=3
        )
        assert result1 != result2

    def test_equality_different_type(self, sample_item_spec_id):
        """異なる型との等価性テスト"""
        result = RecipeResult(
            item_spec_id=sample_item_spec_id,
            quantity=5
        )
        assert result != "not a result"
        assert result != 42

    def test_hash_consistency(self, sample_item_spec_id):
        """ハッシュの一貫性テスト"""
        result1 = RecipeResult(
            item_spec_id=sample_item_spec_id,
            quantity=5
        )
        result2 = RecipeResult(
            item_spec_id=sample_item_spec_id,
            quantity=5
        )

        assert hash(result1) == hash(result2)

        # setで重複を除去できる
        results = {result1, result2}
        assert len(results) == 1

    def test_immutable(self, sample_item_spec_id):
        """不変性のテスト"""
        result = RecipeResult(
            item_spec_id=sample_item_spec_id,
            quantity=5
        )

        # frozen=Trueなので属性の直接変更は不可
        with pytest.raises(AttributeError):
            result.quantity = 10

        with pytest.raises(AttributeError):
            result.item_spec_id = ItemSpecId(999)
