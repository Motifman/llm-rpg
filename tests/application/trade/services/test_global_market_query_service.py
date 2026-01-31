"""
GlobalMarketQueryServiceのテスト
"""
import pytest
from typing import Optional
from datetime import datetime, timedelta
import base64
import json

from src.application.trade.services.global_market_query_service import GlobalMarketQueryService
from src.infrastructure.repository.in_memory_global_market_listing_read_model_repository import InMemoryGlobalMarketListingReadModelRepository
from src.application.trade.contracts.global_market_dtos import (
    GlobalMarketFilterDto,
    GlobalMarketListingDto,
    GlobalMarketListDto
)
from src.application.trade.exceptions.global_market_query_application_exception import GlobalMarketQueryApplicationException
from src.application.common.exceptions import SystemErrorException
from src.domain.common.exception import DomainException
from src.domain.trade.exception.trade_exception import TradeSearchFilterValidationException
from src.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType
from src.domain.trade.enum.trade_enum import TradeStatus
from src.domain.trade.value_object.trade_id import TradeId
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.value_object.item_instance_id import ItemInstanceId
from src.domain.trade.read_model.global_market_listing_read_model import GlobalMarketListingReadModel


class TestGlobalMarketQueryService:
    """GlobalMarketQueryServiceのテストクラス"""

    def setup_method(self):
        """各テストメソッド実行前に呼ばれる"""
        self.repository = InMemoryGlobalMarketListingReadModelRepository()
        self.service = GlobalMarketQueryService(self.repository)

    def test_get_market_listings_no_filter_default_limit(self):
        """フィルタなし、デフォルトlimit（50）で出品を取得できる"""
        result = self.service.get_market_listings()

        assert isinstance(result, GlobalMarketListDto)
        assert len(result.listings) > 0
        assert len(result.listings) <= 50
        # グローバル取引所では常にACTIVEステータスのみ
        for listing in result.listings:
            assert listing.status == "active"
        # 作成日時の降順で並んでいることを確認
        if len(result.listings) > 1:
            assert result.listings[0].created_at >= result.listings[1].created_at

    def test_get_market_listings_no_filter_custom_limit(self):
        """フィルタなし、カスタムlimitで出品を取得できる"""
        result = self.service.get_market_listings(limit=5)

        assert isinstance(result, GlobalMarketListDto)
        assert len(result.listings) <= 5

    def test_get_market_listings_with_cursor_pagination(self):
        """カーソルベースページングで出品を取得できる"""
        # 最初のページを取得（limit=3）
        first_page = self.service.get_market_listings(limit=3)
        assert isinstance(first_page, GlobalMarketListDto)
        assert len(first_page.listings) <= 3

        # カーソルが存在する場合、次のページを取得
        if first_page.next_cursor:
            second_page = self.service.get_market_listings(limit=3, cursor=first_page.next_cursor)
            assert isinstance(second_page, GlobalMarketListDto)
            assert len(second_page.listings) <= 3

            # ページングが正しく動作していることを確認（重複がない）
            first_page_ids = {listing.trade_id for listing in first_page.listings}
            second_page_ids = {listing.trade_id for listing in second_page.listings}
            assert first_page_ids.isdisjoint(second_page_ids)

    def test_get_market_listings_zero_limit(self):
        """limit=0を指定するとGlobalMarketQueryApplicationExceptionが発生"""
        with pytest.raises(GlobalMarketQueryApplicationException) as exc_info:
            self.service.get_market_listings(limit=0)

        assert "Limit must be between 1 and 100, got 0" in str(exc_info.value)

    def test_get_market_listings_negative_limit(self):
        """負のlimitを指定するとGlobalMarketQueryApplicationExceptionが発生"""
        with pytest.raises(GlobalMarketQueryApplicationException) as exc_info:
            self.service.get_market_listings(limit=-1)

        assert "Limit must be between 1 and 100, got -1" in str(exc_info.value)

    def test_get_market_listings_limit_over_max(self):
        """limit=101を指定するとGlobalMarketQueryApplicationExceptionが発生"""
        with pytest.raises(GlobalMarketQueryApplicationException) as exc_info:
            self.service.get_market_listings(limit=101)

        assert "Limit must be between 1 and 100, got 101" in str(exc_info.value)

    def test_get_market_listings_invalid_cursor_base64(self):
        """無効なbase64形式のカーソルを指定するとSystemErrorExceptionが発生"""
        with pytest.raises(SystemErrorException) as exc_info:
            self.service.get_market_listings(cursor="invalid_base64_string!")

        assert "get_market_listings failed: Invalid cursor format" in str(exc_info.value)

    def test_get_market_listings_invalid_cursor_json(self):
        """base64は有効だがJSONが無効なカーソルを指定するとSystemErrorExceptionが発生"""
        # "invalid_json" をbase64エンコードしたもの
        invalid_cursor = "aW52YWxpZF9qc29u"  # base64 of "invalid_json"
        with pytest.raises(SystemErrorException) as exc_info:
            self.service.get_market_listings(cursor=invalid_cursor)

        assert "get_market_listings failed: Invalid cursor format" in str(exc_info.value)

    def test_get_market_listings_invalid_cursor_missing_fields(self):
        """必須フィールドが欠けているカーソルを指定するとSystemErrorExceptionが発生"""
        # 必須フィールド(created_at)が欠けているJSON
        invalid_data = {"entity_id": 123}
        json_str = json.dumps(invalid_data, separators=(',', ':'))
        invalid_cursor = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')

        with pytest.raises(SystemErrorException) as exc_info:
            self.service.get_market_listings(cursor=invalid_cursor)

        assert "get_market_listings failed: Invalid cursor format" in str(exc_info.value)

    def test_get_market_listings_filter_by_item_name(self):
        """アイテム名で出品をフィルタリングできる"""
        filter_dto = GlobalMarketFilterDto(item_name="剣")
        result = self.service.get_market_listings(filter_dto=filter_dto)

        assert isinstance(result, GlobalMarketListDto)
        # 全ての結果に"剣"が含まれていることを確認
        for listing in result.listings:
            assert "剣" in listing.item_name

    def test_get_market_listings_filter_by_item_name_case_insensitive(self):
        """アイテム名検索は大文字小文字を区別しない"""
        filter_dto = GlobalMarketFilterDto(item_name="SWORD")  # 大文字で検索
        result = self.service.get_market_listings(filter_dto=filter_dto)

        assert isinstance(result, GlobalMarketListDto)
        # 小文字の"剣"を含むアイテムがヒットすることを確認
        for listing in result.listings:
            assert "sword" in listing.item_name.lower() or "剣" in listing.item_name

    def test_get_market_listings_filter_by_item_types(self):
        """アイテムタイプで出品をフィルタリングできる"""
        filter_dto = GlobalMarketFilterDto(item_types=["equipment"])
        result = self.service.get_market_listings(filter_dto=filter_dto)

        assert isinstance(result, GlobalMarketListDto)
        for listing in result.listings:
            assert listing.item_type == "equipment"

    def test_get_market_listings_filter_by_multiple_item_types(self):
        """複数のアイテムタイプで出品をフィルタリングできる"""
        filter_dto = GlobalMarketFilterDto(item_types=["equipment", "consumable"])
        result = self.service.get_market_listings(filter_dto=filter_dto)

        assert isinstance(result, GlobalMarketListDto)
        for listing in result.listings:
            assert listing.item_type in ["equipment", "consumable"]

    def test_get_market_listings_filter_by_rarities(self):
        """レアリティで出品をフィルタリングできる"""
        filter_dto = GlobalMarketFilterDto(rarities=["rare"])
        result = self.service.get_market_listings(filter_dto=filter_dto)

        assert isinstance(result, GlobalMarketListDto)
        for listing in result.listings:
            assert listing.item_rarity == "rare"

    def test_get_market_listings_filter_by_multiple_rarities(self):
        """複数のレアリティで出品をフィルタリングできる"""
        filter_dto = GlobalMarketFilterDto(rarities=["common", "uncommon"])
        result = self.service.get_market_listings(filter_dto=filter_dto)

        assert isinstance(result, GlobalMarketListDto)
        for listing in result.listings:
            assert listing.item_rarity in ["common", "uncommon"]

    def test_get_market_listings_filter_by_equipment_types(self):
        """装備タイプで出品をフィルタリングできる"""
        filter_dto = GlobalMarketFilterDto(equipment_types=["weapon"])
        result = self.service.get_market_listings(filter_dto=filter_dto)

        assert isinstance(result, GlobalMarketListDto)
        for listing in result.listings:
            assert listing.item_equipment_type == "weapon"

    def test_get_market_listings_filter_by_multiple_equipment_types(self):
        """複数の装備タイプで出品をフィルタリングできる"""
        filter_dto = GlobalMarketFilterDto(equipment_types=["weapon", "armor"])
        result = self.service.get_market_listings(filter_dto=filter_dto)

        assert isinstance(result, GlobalMarketListDto)
        for listing in result.listings:
            assert listing.item_equipment_type in ["weapon", "armor"]

    def test_get_market_listings_filter_by_price_range_min_only(self):
        """最小価格のみで出品をフィルタリングできる"""
        filter_dto = GlobalMarketFilterDto(min_price=1000)
        result = self.service.get_market_listings(filter_dto=filter_dto)

        assert isinstance(result, GlobalMarketListDto)
        for listing in result.listings:
            assert listing.requested_gold >= 1000

    def test_get_market_listings_filter_by_price_range_max_only(self):
        """最大価格のみで出品をフィルタリングできる"""
        filter_dto = GlobalMarketFilterDto(max_price=1000)
        result = self.service.get_market_listings(filter_dto=filter_dto)

        assert isinstance(result, GlobalMarketListDto)
        for listing in result.listings:
            assert listing.requested_gold <= 1000

    def test_get_market_listings_filter_by_price_range_min_max(self):
        """価格範囲（最小・最大）で出品をフィルタリングできる"""
        filter_dto = GlobalMarketFilterDto(min_price=200, max_price=2000)
        result = self.service.get_market_listings(filter_dto=filter_dto)

        assert isinstance(result, GlobalMarketListDto)
        for listing in result.listings:
            assert 200 <= listing.requested_gold <= 2000

    def test_get_market_listings_filter_equipment_only(self):
        """装備品のみをフィルタリングできる"""
        filter_dto = GlobalMarketFilterDto(item_types=["equipment"])
        result = self.service.get_market_listings(filter_dto=filter_dto)

        assert isinstance(result, GlobalMarketListDto)
        for listing in result.listings:
            assert listing.item_type == "equipment"
            # 装備品の場合は装備タイプが設定されている
            assert listing.item_equipment_type is not None

    def test_get_market_listings_multiple_filters_combined(self):
        """複数のフィルタ条件を組み合わせて検索できる"""
        filter_dto = GlobalMarketFilterDto(
            item_types=["equipment"],
            rarities=["common", "uncommon"],
            equipment_types=["weapon"],
            min_price=100,
            max_price=1500
        )
        result = self.service.get_market_listings(filter_dto=filter_dto)

        assert isinstance(result, GlobalMarketListDto)
        for listing in result.listings:
            assert listing.item_type == "equipment"
            assert listing.item_rarity in ["common", "uncommon"]
            assert listing.item_equipment_type == "weapon"
            assert 100 <= listing.requested_gold <= 1500

    def test_get_market_listings_empty_result_no_matching_filters(self):
        """フィルタ条件に一致する出品がない場合、空のリストが返る"""
        filter_dto = GlobalMarketFilterDto(
            item_name="存在しないアイテム名12345",
            min_price=999999
        )
        result = self.service.get_market_listings(filter_dto=filter_dto)

        assert isinstance(result, GlobalMarketListDto)
        assert len(result.listings) == 0
        assert result.next_cursor is None

    def test_get_market_listings_empty_result_equipment_type_without_equipment(self):
        """装備タイプを指定したが装備品でないアイテムの場合、空の結果が返る"""
        filter_dto = GlobalMarketFilterDto(
            item_types=["consumable"],
            equipment_types=["weapon"]  # 消費アイテムに武器タイプは存在しない
        )
        result = self.service.get_market_listings(filter_dto=filter_dto)

        assert isinstance(result, GlobalMarketListDto)
        assert len(result.listings) == 0
        assert result.next_cursor is None

    def test_execute_with_error_handling_domain_exception(self):
        """ドメイン例外が発生した場合、GlobalMarketQueryApplicationExceptionに変換される"""
        from unittest.mock import Mock
        from src.domain.common.exception import StateException

        # モックを作成してDomainExceptionを発生させる
        mock_operation = Mock(side_effect=StateException("Test domain error"))

        with pytest.raises(GlobalMarketQueryApplicationException) as exc_info:
            self.service._execute_with_error_handling(
                operation=mock_operation,
                context={"action": "test"}
            )

        assert "Domain error in GlobalMarketQuery usecase: DOMAIN_ERROR" in str(exc_info.value)

    def test_execute_with_error_handling_application_exception(self):
        """GlobalMarketQueryApplicationExceptionはそのまま再スローされる"""
        from unittest.mock import Mock

        app_exception = GlobalMarketQueryApplicationException("Test application error")

        mock_operation = Mock(side_effect=app_exception)

        with pytest.raises(GlobalMarketQueryApplicationException) as exc_info:
            self.service._execute_with_error_handling(
                operation=mock_operation,
                context={"action": "test"}
            )

        assert exc_info.value is app_exception

    def test_execute_with_error_handling_unexpected_exception(self):
        """予期しない例外が発生した場合、SystemErrorExceptionに変換される"""
        from unittest.mock import Mock

        mock_operation = Mock(side_effect=ValueError("Unexpected error"))

        with pytest.raises(SystemErrorException) as exc_info:
            self.service._execute_with_error_handling(
                operation=mock_operation,
                context={"action": "test_action"}
            )

        assert "test_action failed: Unexpected error" in str(exc_info.value)
        assert isinstance(exc_info.value.original_exception, ValueError)

    def test_convert_to_filter_none_filter_dto(self):
        """filter_dtoがNoneの場合、ACTIVEステータスのみのフィルタが作成される"""
        result = self.service._convert_to_filter(None)

        assert result.item_name is None
        assert result.item_types is None
        assert result.rarities is None
        assert result.equipment_types is None
        assert result.min_price is None
        assert result.max_price is None
        assert result.statuses == [TradeStatus.ACTIVE]

    def test_convert_to_filter_with_all_conditions(self):
        """全ての条件が設定されたfilter_dtoから正しくフィルタが変換される"""
        filter_dto = GlobalMarketFilterDto(
            item_name="test item",
            item_types=["equipment", "consumable"],
            rarities=["common", "rare"],
            equipment_types=["weapon", "armor"],
            min_price=100,
            max_price=1000
        )

        result = self.service._convert_to_filter(filter_dto)

        assert result.item_name == "test item"
        assert result.item_types == [ItemType.EQUIPMENT, ItemType.CONSUMABLE]
        assert result.rarities == [Rarity.COMMON, Rarity.RARE]
        assert result.equipment_types == [EquipmentType.WEAPON, EquipmentType.ARMOR]
        assert result.min_price == 100
        assert result.max_price == 1000
        assert result.statuses == [TradeStatus.ACTIVE]  # グローバル取引所では常にACTIVE

    def test_convert_to_filter_invalid_enum_values(self):
        """無効なenum値が指定された場合、ValueErrorが発生"""
        filter_dto = GlobalMarketFilterDto(item_types=["invalid_type"])

        with pytest.raises(ValueError) as exc_info:
            self.service._convert_to_filter(filter_dto)

        assert "'invalid_type' is not a valid ItemType" in str(exc_info.value)

    def test_convert_to_listing_dto_equipment_with_durability(self):
        """耐久度を持つ装備品のReadModelが正しくDTOに変換される"""
        # サンプルデータから装備品を取得
        repository = InMemoryGlobalMarketListingReadModelRepository()
        sample_listing = repository.find_by_id(TradeId(1))  # 鋼の剣

        result = self.service._convert_to_listing_dto(sample_listing)

        assert isinstance(result, GlobalMarketListingDto)
        assert result.trade_id == 1
        assert result.item_spec_id == 1
        assert result.item_instance_id == 1
        assert result.item_name == "鋼の剣"
        assert result.item_quantity == 1
        assert result.item_type == "equipment"
        assert result.item_rarity == "common"
        assert result.item_equipment_type == "weapon"
        assert result.status == "active"
        assert result.durability_current == 85
        assert result.durability_max == 100
        assert result.requested_gold == 500

    def test_convert_to_listing_dto_consumable_without_durability(self):
        """耐久度を持たない消費アイテムのReadModelが正しくDTOに変換される"""
        # サンプルデータから消費アイテムを取得
        repository = InMemoryGlobalMarketListingReadModelRepository()
        sample_listing = repository.find_by_id(TradeId(3))  # 回復薬

        result = self.service._convert_to_listing_dto(sample_listing)

        assert isinstance(result, GlobalMarketListingDto)
        assert result.trade_id == 3
        assert result.item_name == "回復薬"
        assert result.item_type == "consumable"
        assert result.item_equipment_type is None  # 消費アイテムなのでNone
        assert result.durability_current is None
        assert result.durability_max is None

    def test_convert_to_listing_dto_material_item(self):
        """素材アイテムのReadModelが正しくDTOに変換される"""
        # サンプルデータから素材アイテムを取得
        repository = InMemoryGlobalMarketListingReadModelRepository()
        sample_listing = repository.find_by_id(TradeId(6))  # 丈夫な縄

        result = self.service._convert_to_listing_dto(sample_listing)

        assert isinstance(result, GlobalMarketListingDto)
        assert result.item_type == "material"
        assert result.item_equipment_type is None
        assert result.durability_current is None
        assert result.durability_max is None
