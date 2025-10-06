"""
ItemInfoQueryServiceのテスト
"""
import pytest
from unittest.mock import Mock
from src.application.inventory.services.item_info_query_service import ItemInfoQueryService
from src.infrastructure.repository.in_memory_item_spec_repository import InMemoryItemSpecRepository
from src.application.inventory.contracts.dtos import ItemSpecDto, ErrorResponseDto
from src.application.inventory.exceptions.item_info_query_application_exception import ItemInfoQueryApplicationException
from src.application.inventory.exceptions import SystemErrorException
from src.domain.item.exception.item_exception import ItemInstanceIdValidationException
from src.domain.item.enum.item_enum import ItemType, Rarity


class TestItemInfoQueryService:
    """ItemInfoQueryServiceのテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.repository = InMemoryItemSpecRepository()
        self.service = ItemInfoQueryService(self.repository)

    def teardown_method(self):
        """各テストメソッドの後に実行"""
        pass

    def test_get_item_spec_success(self):
        """アイテムスペック取得 - 正常系"""
        # Given
        item_spec_id = 1  # 鉄の剣

        # When
        result = self.service.get_item_spec(item_spec_id)

        # Then
        assert isinstance(result, ItemSpecDto)
        assert result.item_spec_id == 1
        assert result.name == "鉄の剣"
        assert result.item_type == ItemType.EQUIPMENT
        assert result.rarity == Rarity.COMMON
        assert result.description == "基本的な鉄製の剣。冒険者の定番武器。"
        assert result.max_stack_size == 1
        assert result.durability_max == 100

    def test_get_item_spec_not_found(self):
        """アイテムスペック取得 - 存在しないID"""
        # Given
        item_spec_id = 999  # 存在しないID

        # When & Then
        with pytest.raises(ItemInfoQueryApplicationException) as exc_info:
            self.service.get_item_spec(item_spec_id)

        assert exc_info.value.context.get("item_spec_id") == item_spec_id
        assert "Item spec not found" in str(exc_info.value)

    def test_search_items_by_type_equipment(self):
        """アイテムタイプ別検索 - EQUIPMENT"""
        # Given
        item_type = ItemType.EQUIPMENT

        # When
        results = self.service.search_items_by_type(item_type)

        # Then
        assert isinstance(results, list)
        assert len(results) >= 8  # 剣3つ + 鎧2つ + 靴・手袋・兜の3つ

        # 全てEQUIPMENTタイプであることを確認
        for result in results:
            assert isinstance(result, ItemSpecDto)
            assert result.item_type == ItemType.EQUIPMENT

        # 特定のアイテムが含まれていることを確認
        item_names = [result.name for result in results]
        assert "鉄の剣" in item_names
        assert "革の鎧" in item_names
        assert "革の靴" in item_names

    def test_search_items_by_type_consumable(self):
        """アイテムタイプ別検索 - CONSUMABLE"""
        # Given
        item_type = ItemType.CONSUMABLE

        # When
        results = self.service.search_items_by_type(item_type)

        # Then
        assert isinstance(results, list)
        assert len(results) == 3  # 回復ポーション、マナポーション、上級回復ポーション

        for result in results:
            assert isinstance(result, ItemSpecDto)
            assert result.item_type == ItemType.CONSUMABLE

        item_names = [result.name for result in results]
        assert "回復ポーション" in item_names
        assert "マナポーション" in item_names
        assert "上級回復ポーション" in item_names

    def test_search_items_by_type_material(self):
        """アイテムタイプ別検索 - MATERIAL"""
        # Given
        item_type = ItemType.MATERIAL

        # When
        results = self.service.search_items_by_type(item_type)

        # Then
        assert isinstance(results, list)
        assert len(results) == 3  # 鉄鉱石、鋼鉄インゴット、神秘のクリスタル

        for result in results:
            assert isinstance(result, ItemSpecDto)
            assert result.item_type == ItemType.MATERIAL

    def test_search_items_by_rarity_common(self):
        """レアリティ別検索 - COMMON"""
        # Given
        rarity = Rarity.COMMON

        # When
        results = self.service.search_items_by_rarity(rarity)

        # Then
        assert isinstance(results, list)
        assert len(results) >= 6  # 複数のCOMMONアイテム

        for result in results:
            assert isinstance(result, ItemSpecDto)
            assert result.rarity == Rarity.COMMON

    def test_search_items_by_rarity_legendary(self):
        """レアリティ別検索 - LEGENDARY"""
        # Given
        rarity = Rarity.LEGENDARY

        # When
        results = self.service.search_items_by_rarity(rarity)

        # Then
        assert isinstance(results, list)
        assert len(results) == 1  # 伝説の剣のみ

        result = results[0]
        assert result.name == "伝説の剣"
        assert result.rarity == Rarity.LEGENDARY

    def test_find_tradeable_items(self):
        """取引可能アイテム取得"""
        # When
        results = self.service.find_tradeable_items()

        # Then
        assert isinstance(results, list)
        # クエストアイテム以外全てが取引可能
        assert len(results) == 15  # 全アイテム数 - クエストアイテム数

        # クエストアイテムが含まれていないことを確認
        item_names = [result.name for result in results]
        assert "古代の巻物" not in item_names
        assert "クエストキー" not in item_names

        # 通常アイテムが含まれていることを確認
        assert "鉄の剣" in item_names
        assert "回復ポーション" in item_names
        assert "鉄鉱石" in item_names

    def test_find_item_by_name_existing(self):
        """名前検索 - 存在するアイテム"""
        # Given
        name = "鉄の剣"

        # When
        result = self.service.find_item_by_name(name)

        # Then
        assert result is not None
        assert isinstance(result, ItemSpecDto)
        assert result.name == "鉄の剣"
        assert result.item_spec_id == 1

    def test_find_item_by_name_not_existing(self):
        """名前検索 - 存在しないアイテム"""
        # Given
        name = "存在しないアイテム"

        # When
        result = self.service.find_item_by_name(name)

        # Then
        assert result is None

    def test_find_item_by_name_case_sensitive(self):
        """名前検索 - 大文字小文字の区別"""
        # Given
        name = "鉄の剣"  # 正確な名前

        # When
        result = self.service.find_item_by_name(name)

        # Then
        assert result is not None

        # Given - 異なるケース
        name_wrong_case = "てつのけん"  # ひらがな

        # When
        result_wrong = self.service.find_item_by_name(name_wrong_case)

        # Then
        assert result_wrong is None

    def test_repository_integration(self):
        """リポジトリとの統合テスト"""
        # リポジトリが正しく動作することを確認

        # 1. 全アイテム数の確認
        all_items = self.repository.find_all()
        assert len(all_items) == 17  # サンプルデータで作成した全アイテム数

        # 2. タイプ別検索の確認
        equipment_items = self.repository.find_by_type(ItemType.EQUIPMENT)
        assert len(equipment_items) >= 8

        consumable_items = self.repository.find_by_type(ItemType.CONSUMABLE)
        assert len(consumable_items) == 3

        # 3. レアリティ別検索の確認
        legendary_items = self.repository.find_by_rarity(Rarity.LEGENDARY)
        assert len(legendary_items) == 1

        # 4. 名前検索の確認
        sword_item = self.repository.find_by_name("鉄の剣")
        assert sword_item is not None
        assert sword_item.item_spec_id.value == 1

        # 5. 取引可能アイテムの確認
        tradeable_items = self.repository.find_tradeable_items()
        assert len(tradeable_items) == 15  # 全アイテム数 - クエストアイテム数

        # クエストアイテムは取引不可能
        quest_items = [item for item in all_items if item.item_type == ItemType.QUEST]
        assert len(quest_items) == 2  # 古代の巻物、クエストキー

    def test_get_item_spec_negative_id(self):
        """アイテムスペック取得 - 負のID（ドメイン例外からアプリケーション例外への変換）"""
        # Given
        item_spec_id = -1

        # When & Then
        with pytest.raises(ItemInfoQueryApplicationException) as exc_info:
            self.service.get_item_spec(item_spec_id)

        # ドメイン例外がアプリケーション例外に変換されていることを確認
        assert exc_info.value.cause is not None
        assert hasattr(exc_info.value.cause, 'error_code')
        assert "Domain error in ItemInfoQuery usecase" in str(exc_info.value)

    def test_get_item_spec_zero_id(self):
        """アイテムスペック取得 - IDが0（ドメイン例外からアプリケーション例外への変換）"""
        # Given
        item_spec_id = 0

        # When & Then
        with pytest.raises(ItemInfoQueryApplicationException) as exc_info:
            self.service.get_item_spec(item_spec_id)

        # ドメイン例外がアプリケーション例外に変換されていることを確認
        assert exc_info.value.cause is not None
        assert hasattr(exc_info.value.cause, 'error_code')
        assert "Domain error in ItemInfoQuery usecase" in str(exc_info.value)

    def test_find_item_by_name_empty_string(self):
        """名前検索 - 空文字列"""
        # Given
        name = ""

        # When
        result = self.service.find_item_by_name(name)

        # Then
        assert result is None

    def test_find_item_by_name_none(self):
        """名前検索 - None"""
        # Given
        name = None

        # When
        result = self.service.find_item_by_name(name)

        # Then
        # リポジトリの実装によってはNoneが返される可能性がある
        assert result is None

    def test_get_item_spec_repository_exception(self):
        """アイテムスペック取得 - リポジトリ例外"""
        # Given
        mock_repo = Mock()
        mock_repo.find_by_id.side_effect = Exception("Database connection failed")
        service = ItemInfoQueryService(mock_repo)

        # When & Then
        with pytest.raises(SystemErrorException) as exc_info:
            service.get_item_spec(1)

        assert "Database connection failed" in str(exc_info.value)
        assert exc_info.value.original_exception is not None

    def test_search_items_by_type_repository_exception(self):
        """タイプ別検索 - リポジトリ例外"""
        # Given
        mock_repo = Mock()
        mock_repo.find_by_type.side_effect = Exception("Database connection failed")
        service = ItemInfoQueryService(mock_repo)

        # When & Then
        with pytest.raises(SystemErrorException) as exc_info:
            service.search_items_by_type(ItemType.EQUIPMENT)

        assert "Database connection failed" in str(exc_info.value)

    def test_search_items_by_rarity_repository_exception(self):
        """レアリティ別検索 - リポジトリ例外"""
        # Given
        mock_repo = Mock()
        mock_repo.find_by_rarity.side_effect = Exception("Database connection failed")
        service = ItemInfoQueryService(mock_repo)

        # When & Then
        with pytest.raises(SystemErrorException) as exc_info:
            service.search_items_by_rarity(Rarity.COMMON)

        assert "Database connection failed" in str(exc_info.value)

    def test_find_tradeable_items_repository_exception(self):
        """取引可能アイテム取得 - リポジトリ例外"""
        # Given
        mock_repo = Mock()
        mock_repo.find_tradeable_items.side_effect = Exception("Database connection failed")
        service = ItemInfoQueryService(mock_repo)

        # When & Then
        with pytest.raises(SystemErrorException) as exc_info:
            service.find_tradeable_items()

        assert "Database connection failed" in str(exc_info.value)

    def test_find_item_by_name_repository_exception(self):
        """名前検索 - リポジトリ例外"""
        # Given
        mock_repo = Mock()
        mock_repo.find_by_name.side_effect = Exception("Database connection failed")
        service = ItemInfoQueryService(mock_repo)

        # When & Then
        with pytest.raises(SystemErrorException) as exc_info:
            service.find_item_by_name("鉄の剣")

        assert "Database connection failed" in str(exc_info.value)

    def test_search_items_by_type_empty_result(self):
        """タイプ別検索 - 空の結果"""
        # Given - EPICレアリティは存在しないはず
        item_type = ItemType.COSMETIC  # サンプルデータに存在しないタイプ

        # When
        results = self.service.search_items_by_type(item_type)

        # Then
        assert isinstance(results, list)
        assert len(results) == 0

    def test_search_items_by_rarity_empty_result(self):
        """レアリティ別検索 - 空の結果"""
        # Given - MYTHICレアリティはサンプルデータに存在しない
        rarity = Rarity.MYTHIC

        # When
        results = self.service.search_items_by_rarity(rarity)

        # Then
        assert isinstance(results, list)
        assert len(results) == 0

    def test_get_item_spec_repository_exception_logging(self, caplog):
        """アイテムスペック取得 - リポジトリ例外時のログ出力"""
        import logging

        # Given
        mock_repo = Mock()
        mock_repo.find_by_id.side_effect = Exception("Database connection failed")
        service = ItemInfoQueryService(mock_repo)

        # When & Then
        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemErrorException):
                service.get_item_spec(1)

        # ログが記録されていることを確認
        assert len(caplog.records) == 1
        log_record = caplog.records[0]
        assert log_record.levelname == "ERROR"
        assert "Unexpected error in get_item_spec" in log_record.message
        assert "Database connection failed" in log_record.message

    def test_application_exception_is_reraised(self):
        """アプリケーション例外がそのまま再スローされることを確認"""
        # Given
        mock_repo = Mock()
        mock_repo.find_by_id.side_effect = ItemInfoQueryApplicationException.item_spec_not_found(999)
        service = ItemInfoQueryService(mock_repo)

        # When & Then
        with pytest.raises(ItemInfoQueryApplicationException) as exc_info:
            service.get_item_spec(999)

        assert "Item spec not found" in str(exc_info.value)
        assert exc_info.value.context.get("item_spec_id") == 999

    def test_search_items_by_type_repository_exception_logging(self, caplog):
        """タイプ別検索 - リポジトリ例外時のログ出力"""
        import logging

        # Given
        mock_repo = Mock()
        mock_repo.find_by_type.side_effect = Exception("Database connection failed")
        service = ItemInfoQueryService(mock_repo)

        # When & Then
        with caplog.at_level(logging.ERROR):
            with pytest.raises(SystemErrorException):
                service.search_items_by_type(ItemType.EQUIPMENT)

        # ログが記録されていることを確認
        assert len(caplog.records) == 1
        log_record = caplog.records[0]
        assert log_record.levelname == "ERROR"
        assert "Unexpected error in search_items_by_type" in log_record.message
