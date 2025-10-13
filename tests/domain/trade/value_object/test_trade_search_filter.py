import pytest
from src.domain.trade.value_object.trade_search_filter import TradeSearchFilter
from src.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType
from src.domain.trade.enum.trade_enum import TradeStatus
from src.domain.trade.exception.trade_exception import TradeSearchFilterValidationException


class TestTradeSearchFilter:
    """TradeSearchFilterのテスト"""

    def test_create_empty_filter(self):
        """空のフィルタを作成できる"""
        filter = TradeSearchFilter()
        assert filter.item_name is None
        assert filter.item_types is None
        assert filter.rarities is None
        assert filter.equipment_types is None
        assert filter.min_price is None
        assert filter.max_price is None
        assert filter.statuses is None

    def test_create_filter_with_item_name(self):
        """アイテム名フィルタを作成できる"""
        filter = TradeSearchFilter(item_name="sword")
        assert filter.item_name == "sword"

    def test_create_filter_with_price_range(self):
        """価格範囲フィルタを作成できる"""
        filter = TradeSearchFilter(min_price=100, max_price=500)
        assert filter.min_price == 100
        assert filter.max_price == 500

    def test_price_validation_negative_min_price(self):
        """負の最小価格はエラー"""
        with pytest.raises(TradeSearchFilterValidationException, match="Minimum price cannot be negative"):
            TradeSearchFilter(min_price=-1)

    def test_price_validation_negative_max_price(self):
        """負の最大価格はエラー"""
        with pytest.raises(TradeSearchFilterValidationException, match="Maximum price cannot be negative"):
            TradeSearchFilter(max_price=-1)

    def test_price_validation_min_greater_than_max(self):
        """最小価格が最大価格より大きい場合はエラー"""
        with pytest.raises(TradeSearchFilterValidationException, match="Minimum price cannot be greater than maximum price"):
            TradeSearchFilter(min_price=500, max_price=100)

    def test_active_only_factory_method(self):
        """active_onlyファクトリーメソッド"""
        filter = TradeSearchFilter.active_only()
        assert filter.statuses == [TradeStatus.ACTIVE]

    def test_by_item_name_factory_method(self):
        """by_item_nameファクトリーメソッド"""
        filter = TradeSearchFilter.by_item_name("sword")
        assert filter.item_name == "sword"

    def test_by_price_range_factory_method(self):
        """by_price_rangeファクトリーメソッド"""
        filter = TradeSearchFilter.by_price_range(min_price=100, max_price=500)
        assert filter.min_price == 100
        assert filter.max_price == 500

    def test_by_item_types_factory_method(self):
        """by_item_typesファクトリーメソッド"""
        item_types = [ItemType.EQUIPMENT, ItemType.CONSUMABLE]
        filter = TradeSearchFilter.by_item_types(item_types)
        assert filter.item_types == item_types

    def test_from_primitives_empty(self):
        """空のプリミティブから作成"""
        filter = TradeSearchFilter.from_primitives()
        assert filter.item_name is None
        assert filter.item_types is None

    def test_from_primitives_with_item_name(self):
        """アイテム名付きのプリミティブから作成"""
        filter = TradeSearchFilter.from_primitives(item_name="sword")
        assert filter.item_name == "sword"

    def test_from_primitives_with_item_types(self):
        """アイテムタイプ付きのプリミティブから作成"""
        filter = TradeSearchFilter.from_primitives(
            item_types=["equipment", "consumable"]
        )
        assert filter.item_types == [ItemType.EQUIPMENT, ItemType.CONSUMABLE]

    def test_from_primitives_with_rarities(self):
        """レアリティ付きのプリミティブから作成"""
        filter = TradeSearchFilter.from_primitives(
            rarities=["rare", "epic"]
        )
        assert filter.rarities == [Rarity.RARE, Rarity.EPIC]

    def test_from_primitives_with_equipment_types(self):
        """装備タイプ付きのプリミティブから作成"""
        filter = TradeSearchFilter.from_primitives(
            equipment_types=["weapon", "armor"]
        )
        assert filter.equipment_types == [EquipmentType.WEAPON, EquipmentType.ARMOR]

    def test_from_primitives_with_statuses(self):
        """ステータス付きのプリミティブから作成"""
        filter = TradeSearchFilter.from_primitives(
            statuses=["active", "completed"]
        )
        assert filter.statuses == [TradeStatus.ACTIVE, TradeStatus.COMPLETED]

    def test_from_primitives_with_price_range(self):
        """価格範囲付きのプリミティブから作成"""
        filter = TradeSearchFilter.from_primitives(min_price=100, max_price=500)
        assert filter.min_price == 100
        assert filter.max_price == 500

    def test_from_primitives_validation(self):
        """プリミティブからの作成でもバリデーションが働く"""
        with pytest.raises(TradeSearchFilterValidationException):
            TradeSearchFilter.from_primitives(min_price=-1)
