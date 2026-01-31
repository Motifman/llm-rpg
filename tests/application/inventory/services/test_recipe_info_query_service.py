"""
RecipeInfoQueryServiceのテスト
"""
import pytest
from unittest.mock import Mock
from src.application.inventory.services.recipe_info_query_service import RecipeInfoQueryService
from src.infrastructure.repository.in_memory_recipe_repository import InMemoryRecipeRepository
from src.application.inventory.contracts.dtos import RecipeDto, RecipeIngredientDto, RecipeResultDto
from src.application.inventory.exceptions.recipe_info_query_application_exception import RecipeInfoQueryApplicationException
from src.application.common.exceptions import SystemErrorException
from src.domain.item.exception.item_exception import RecipeNotFoundException, ItemInstanceIdValidationException
from src.domain.item.value_object.recipe_id import RecipeId
from src.domain.item.value_object.item_spec_id import ItemSpecId


class TestRecipeInfoQueryService:
    """RecipeInfoQueryServiceのテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.repository = InMemoryRecipeRepository()
        self.service = RecipeInfoQueryService(self.repository)

    def teardown_method(self):
        """各テストメソッドの後に実行"""
        pass

    def test_get_recipe_success(self):
        """レシピ取得 - 正常系"""
        # Given
        recipe_id = 1  # 鉄の剣のレシピ

        # When
        result = self.service.get_recipe(recipe_id)

        # Then
        assert isinstance(result, RecipeDto)
        assert result.recipe_id == 1
        assert result.name == "鉄の剣の作成"
        assert result.description == "鉄鉱石と鋼鉄インゴットから鉄の剣を作成します。"
        assert isinstance(result.ingredients, list)
        assert isinstance(result.result, RecipeResultDto)
        assert result.result.item_spec_id == 1  # 鉄の剣
        assert result.result.quantity == 1

    def test_get_recipe_not_found(self):
        """レシピ取得 - 存在しないID"""
        # Given
        recipe_id = 999  # 存在しないID

        # When & Then
        with pytest.raises(RecipeInfoQueryApplicationException) as exc_info:
            self.service.get_recipe(recipe_id)

        assert exc_info.value.context.get("recipe_id") == recipe_id
        assert "Recipe not found" in str(exc_info.value)

    def test_get_recipe_negative_id(self):
        """レシピ取得 - 負のID（ドメイン例外からアプリケーション例外への変換）"""
        # Given
        recipe_id = -1

        # When & Then
        with pytest.raises(RecipeInfoQueryApplicationException) as exc_info:
            self.service.get_recipe(recipe_id)

        # ドメイン例外がアプリケーション例外に変換されていることを確認
        assert exc_info.value.cause is not None
        assert hasattr(exc_info.value.cause, 'error_code')
        assert "Domain error in RecipeInfoQuery usecase" in str(exc_info.value)

    def test_get_recipe_zero_id(self):
        """レシピ取得 - IDが0（ドメイン例外からアプリケーション例外への変換）"""
        # Given
        recipe_id = 0

        # When & Then
        with pytest.raises(RecipeInfoQueryApplicationException) as exc_info:
            self.service.get_recipe(recipe_id)

        # ドメイン例外がアプリケーション例外に変換されていることを確認
        assert exc_info.value.cause is not None
        assert hasattr(exc_info.value.cause, 'error_code')
        assert "Domain error in RecipeInfoQuery usecase" in str(exc_info.value)

    def test_find_recipes_by_result_item_success(self):
        """指定アイテムを作成できるレシピ取得 - 正常系"""
        # Given
        item_spec_id = 1  # 鉄の剣

        # When
        results = self.service.find_recipes_by_result_item(item_spec_id)

        # Then
        assert isinstance(results, list)
        assert len(results) >= 1  # 少なくとも鉄の剣のレシピがある

        # 結果に鉄の剣のレシピが含まれていることを確認
        iron_sword_recipes = [r for r in results if r.result.item_spec_id == 1]
        assert len(iron_sword_recipes) > 0

        recipe = iron_sword_recipes[0]
        assert recipe.name == "鉄の剣の作成"
        assert isinstance(recipe.ingredients, list)
        assert len(recipe.ingredients) >= 2  # 鉄鉱石と鋼鉄インゴット

    def test_find_recipes_by_result_item_not_found(self):
        """指定アイテムを作成できるレシピ取得 - 存在しないアイテムID"""
        # Given
        item_spec_id = 999  # 作成レシピが存在しないアイテム

        # When
        results = self.service.find_recipes_by_result_item(item_spec_id)

        # Then
        assert isinstance(results, list)
        assert len(results) == 0

    def test_find_recipes_by_result_item_invalid_id(self):
        """指定アイテムを作成できるレシピ取得 - 無効なアイテムID（ドメイン例外変換）"""
        # Given
        item_spec_id = -1  # 無効なID

        # When & Then
        with pytest.raises(RecipeInfoQueryApplicationException) as exc_info:
            self.service.find_recipes_by_result_item(item_spec_id)

        # ドメイン例外がアプリケーション例外に変換されていることを確認
        assert exc_info.value.cause is not None
        assert hasattr(exc_info.value.cause, 'error_code')
        assert "Domain error in RecipeInfoQuery usecase" in str(exc_info.value)

    def test_find_recipes_by_ingredient_success(self):
        """指定アイテムを材料として使用するレシピ取得 - 正常系"""
        # Given
        item_spec_id = 4  # 鉄鉱石

        # When
        results = self.service.find_recipes_by_ingredient(item_spec_id)

        # Then
        assert isinstance(results, list)
        assert len(results) >= 1  # 鉄鉱石を使用するレシピがある

        # すべてのレシピが鉄鉱石を材料として使用していることを確認
        for recipe in results:
            ingredient_ids = [ing.item_spec_id for ing in recipe.ingredients]
            assert item_spec_id in ingredient_ids

    def test_find_recipes_by_ingredient_not_found(self):
        """指定アイテムを材料として使用するレシピ取得 - 材料として使用されないアイテム"""
        # Given
        item_spec_id = 1  # 鉄の剣（完成品なので材料として使われない）

        # When
        results = self.service.find_recipes_by_ingredient(item_spec_id)

        # Then
        assert isinstance(results, list)
        assert len(results) == 0

    def test_find_recipes_by_ingredient_invalid_id(self):
        """指定アイテムを材料として使用するレシピ取得 - 無効なアイテムID（ドメイン例外変換）"""
        # Given
        item_spec_id = -1  # 無効なID

        # When & Then
        with pytest.raises(RecipeInfoQueryApplicationException) as exc_info:
            self.service.find_recipes_by_ingredient(item_spec_id)

        # ドメイン例外がアプリケーション例外に変換されていることを確認
        assert exc_info.value.cause is not None
        assert hasattr(exc_info.value.cause, 'error_code')
        assert "Domain error in RecipeInfoQuery usecase" in str(exc_info.value)

    def test_get_all_recipes_success(self):
        """全レシピ取得 - 正常系"""
        # When
        results = self.service.get_all_recipes()

        # Then
        assert isinstance(results, list)
        assert len(results) >= 2  # サンプルデータに少なくとも2つのレシピがある

        # すべての結果がRecipeDtoであることを確認
        for recipe in results:
            assert isinstance(recipe, RecipeDto)
            assert isinstance(recipe.ingredients, list)
            assert isinstance(recipe.result, RecipeResultDto)
            assert recipe.result.quantity > 0

    def test_get_recipe_repository_exception(self):
        """レシピ取得 - リポジトリ例外"""
        # Given
        mock_repo = Mock()
        mock_repo.find_by_id.side_effect = Exception("Database connection failed")
        service = RecipeInfoQueryService(mock_repo)

        # When & Then
        with pytest.raises(SystemErrorException) as exc_info:
            service.get_recipe(1)

        assert "Database connection failed" in str(exc_info.value)
        assert exc_info.value.original_exception is not None

    def test_find_recipes_by_result_item_repository_exception(self):
        """指定アイテムを作成できるレシピ取得 - リポジトリ例外"""
        # Given
        mock_repo = Mock()
        mock_repo.find_by_result_item.side_effect = Exception("Database connection failed")
        service = RecipeInfoQueryService(mock_repo)

        # When & Then
        with pytest.raises(SystemErrorException) as exc_info:
            service.find_recipes_by_result_item(1)

        assert "Database connection failed" in str(exc_info.value)

    def test_find_recipes_by_ingredient_repository_exception(self):
        """指定アイテムを材料として使用するレシピ取得 - リポジトリ例外"""
        # Given
        mock_repo = Mock()
        mock_repo.find_by_ingredient.side_effect = Exception("Database connection failed")
        service = RecipeInfoQueryService(mock_repo)

        # When & Then
        with pytest.raises(SystemErrorException) as exc_info:
            service.find_recipes_by_ingredient(1)

        assert "Database connection failed" in str(exc_info.value)

    def test_get_all_recipes_repository_exception(self):
        """全レシピ取得 - リポジトリ例外"""
        # Given
        mock_repo = Mock()
        mock_repo.find_all.side_effect = Exception("Database connection failed")
        service = RecipeInfoQueryService(mock_repo)

        # When & Then
        with pytest.raises(SystemErrorException) as exc_info:
            service.get_all_recipes()

        assert "Database connection failed" in str(exc_info.value)

    def test_application_exception_is_reraised(self):
        """アプリケーション例外がそのまま再スローされることを確認"""
        # Given
        mock_repo = Mock()
        mock_repo.find_by_id.side_effect = RecipeInfoQueryApplicationException.recipe_not_found(999)
        service = RecipeInfoQueryService(mock_repo)

        # When & Then
        with pytest.raises(RecipeInfoQueryApplicationException) as exc_info:
            service.get_recipe(999)

        assert "Recipe not found" in str(exc_info.value)
        assert exc_info.value.context.get("recipe_id") == 999

    def test_domain_exception_conversion(self):
        """ドメイン例外がアプリケーション例外に変換されることを確認"""
        # Given - RecipeIdのバリデーションでドメイン例外が発生するようMockを設定
        mock_repo = Mock()
        # RecipeId(-1)がドメイン例外を発生させる
        mock_repo.find_by_id.side_effect = lambda x: (_ for _ in ()).throw(Exception("Domain validation error"))
        service = RecipeInfoQueryService(mock_repo)

        # RecipeIdの作成時にドメイン例外が発生するようにする
        from unittest.mock import patch
        with patch('src.domain.item.value_object.recipe_id.RecipeId') as mock_recipe_id:
            mock_recipe_id.side_effect = ItemInstanceIdValidationException()
            mock_repo.find_by_id.side_effect = ItemInstanceIdValidationException()

            # When & Then
            with pytest.raises(RecipeInfoQueryApplicationException) as exc_info:
                service.get_recipe(-1)

            # ドメイン例外がアプリケーション例外に変換されていることを確認
            assert exc_info.value.cause is not None
            assert hasattr(exc_info.value.cause, 'error_code')
            assert "Domain error in RecipeInfoQuery usecase" in str(exc_info.value)

    def test_get_recipe_logging_on_error(self, caplog):
        """レシピ取得 - エラー時のログ出力"""
        import logging

        # Given
        mock_repo = Mock()
        mock_repo.find_by_id.side_effect = Exception("Database connection failed")
        service = RecipeInfoQueryService(mock_repo)

        # When & Then
        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemErrorException):
                service.get_recipe(1)

        # ログが記録されていることを確認
        assert len(caplog.records) == 1
        log_record = caplog.records[0]
        assert log_record.levelname == "ERROR"
        assert "Unexpected error in get_recipe" in log_record.message
        assert "Database connection failed" in log_record.message

    def test_repository_integration(self):
        """リポジトリとの統合テスト"""
        # 全レシピ数の確認
        all_recipes = self.repository.find_all()
        assert len(all_recipes) >= 2  # サンプルデータで作成した全レシピ数

        # 結果アイテム別検索の確認
        iron_sword_recipes = self.repository.find_by_result_item(ItemSpecId(1))
        assert len(iron_sword_recipes) >= 1

        # 材料別検索の確認
        iron_ore_recipes = self.repository.find_by_ingredient(ItemSpecId(4))
        assert len(iron_ore_recipes) >= 1

        # 個別のレシピ取得確認
        recipe = self.repository.find_by_id(RecipeId(1))
        assert recipe is not None
        assert recipe.recipe_id.value == 1
