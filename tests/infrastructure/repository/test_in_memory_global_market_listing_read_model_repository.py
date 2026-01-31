"""
InMemoryGlobalMarketListingReadModelRepositoryのテスト
"""
import pytest
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

from src.infrastructure.repository.in_memory_global_market_listing_read_model_repository import InMemoryGlobalMarketListingReadModelRepository
from src.domain.trade.read_model.global_market_listing_read_model import GlobalMarketListingReadModel
from src.domain.trade.repository.cursor import ListingCursor
from src.domain.trade.value_object.trade_id import TradeId
from src.domain.trade.value_object.trade_search_filter import TradeSearchFilter
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.value_object.item_instance_id import ItemInstanceId
from src.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType
from src.domain.trade.enum.trade_enum import TradeStatus


class TestInMemoryGlobalMarketListingReadModelRepository:
    """InMemoryGlobalMarketListingReadModelRepositoryのテストクラス"""

    def setup_method(self):
        """各テストメソッド実行前に呼ばれる"""
        self.repository = InMemoryGlobalMarketListingReadModelRepository()

    def test_find_by_id_existing_listing(self):
        """存在する出品をIDで検索できる"""
        listing = self.repository.find_by_id(TradeId(1))
        assert listing is not None
        assert listing.trade_id == TradeId(1)
        assert listing.item_name == "鋼の剣"

    def test_find_by_id_non_existing_listing(self):
        """存在しない出品をIDで検索するとNoneが返る"""
        listing = self.repository.find_by_id(TradeId(999))
        assert listing is None

    def test_find_by_ids_multiple_listings(self):
        """複数の出品をIDリストで検索できる"""
        listing_ids = [TradeId(1), TradeId(2), TradeId(999)]
        listings = self.repository.find_by_ids(listing_ids)

        assert len(listings) == 2
        assert listings[0].trade_id == TradeId(1)
        assert listings[1].trade_id == TradeId(2)

    def test_find_all_returns_all_listings(self):
        """find_allですべての出品を取得できる"""
        all_listings = self.repository.find_all()
        assert len(all_listings) >= 12  # サンプルデータが12件以上あるはず

        # 出品IDがユニークであることを確認
        listing_ids = [listing.trade_id for listing in all_listings]
        assert len(listing_ids) == len(set(listing_ids))

    def test_save_and_find_new_listing(self):
        """新しい出品を保存して検索できる"""
        # 新しい出品を作成
        new_listing = GlobalMarketListingReadModel.create_from_trade_data(
            trade_id=TradeId(100),
            item_spec_id=ItemSpecId(100),
            item_instance_id=ItemInstanceId(100),
            item_name="テストアイテム",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.COMMON,
            item_equipment_type=EquipmentType.WEAPON,
            status=TradeStatus.ACTIVE,
            created_at=datetime.now(),
            durability_current=100,
            durability_max=100,
            requested_gold=1000
        )

        # 保存
        saved_listing = self.repository.save(new_listing)

        # 検索して確認
        found_listing = self.repository.find_by_id(TradeId(100))
        assert found_listing is not None
        assert found_listing.trade_id == TradeId(100)
        assert found_listing.item_name == "テストアイテム"
        assert found_listing.requested_gold == 1000

    def test_delete_existing_listing(self):
        """存在する出品を削除できる"""
        # 削除前に存在することを確認
        listing_before = self.repository.find_by_id(TradeId(1))
        assert listing_before is not None

        # 削除
        result = self.repository.delete(TradeId(1))
        assert result is True

        # 削除後に存在しないことを確認
        listing_after = self.repository.find_by_id(TradeId(1))
        assert listing_after is None

    def test_delete_non_existing_listing(self):
        """存在しない出品を削除しようとするとFalseが返る"""
        result = self.repository.delete(TradeId(999))
        assert result is False

    def test_find_listings_without_filter_returns_all(self):
        """フィルタなしでfind_listingsを呼び出すと全ての出品が返る"""
        filter_condition = TradeSearchFilter()
        listings, cursor = self.repository.find_listings(filter_condition, limit=50)

        # 全ての出品が返るはず
        all_listings = self.repository.find_all()
        assert len(listings) == len(all_listings)
        assert cursor is None  # 全て取得しているのでcursorはNone

    def test_find_listings_with_limit(self):
        """limitを指定して出品を取得できる"""
        filter_condition = TradeSearchFilter()
        listings, cursor = self.repository.find_listings(filter_condition, limit=5)

        assert len(listings) == 5
        assert cursor is not None  # limit未満ではないのでcursorが存在

    def test_find_listings_with_cursor_pagination(self):
        """find_listingsでカーソルページングが機能する"""
        filter_condition = TradeSearchFilter()

        # 最初のページを取得
        first_page, next_cursor = self.repository.find_listings(filter_condition, limit=3)
        assert len(first_page) == 3
        assert next_cursor is not None

        # 次のページを取得
        second_page, final_cursor = self.repository.find_listings(filter_condition, limit=3, cursor=next_cursor)
        assert len(second_page) == 3
        assert final_cursor is not None

        # 1ページ目の最後の出品より2ページ目の最初の出品の方がIDが小さいことを確認
        assert int(first_page[-1].trade_id) > int(second_page[0].trade_id)

    def test_find_listings_at_end_returns_no_cursor(self):
        """find_listingsで最後のページではcursorがNoneになる"""
        filter_condition = TradeSearchFilter()

        # 全ての出品を取得するだけのlimitを設定
        all_listings = self.repository.find_all()
        listings, cursor = self.repository.find_listings(filter_condition, limit=len(all_listings))

        assert cursor is None

    def test_find_listings_by_item_name(self):
        """アイテム名で出品を検索できる"""
        # 「剣」を含むアイテムを検索
        filter_condition = TradeSearchFilter.by_item_name("剣")
        listings, cursor = self.repository.find_listings(filter_condition, limit=10)

        # 検索結果に「剣」が含まれるアイテムがあることを確認
        sword_found = any("剣" in listing.item_name for listing in listings)
        assert sword_found

        # 全ての結果が「剣」を含むことを確認
        for listing in listings:
            assert "剣" in listing.item_name

    def test_find_listings_by_item_type(self):
        """アイテムタイプで出品を検索できる"""
        # EQUIPMENTタイプの出品を検索
        filter_condition = TradeSearchFilter.by_item_types([ItemType.EQUIPMENT])
        listings, cursor = self.repository.find_listings(filter_condition, limit=20)

        # 全ての出品がEQUIPMENTであることを確認
        for listing in listings:
            assert listing.item_type == ItemType.EQUIPMENT

    def test_find_listings_by_rarity(self):
        """レアリティで出品を検索できる"""
        # RAREレアリティの出品を検索
        filter_condition = TradeSearchFilter(rarities=[Rarity.RARE])
        listings, cursor = self.repository.find_listings(filter_condition, limit=20)

        # 全ての出品がRAREであることを確認
        for listing in listings:
            assert listing.item_rarity == Rarity.RARE

    def test_find_listings_by_price_range(self):
        """価格範囲で出品を検索できる"""
        # 1000-5000ゴールドの範囲で検索
        filter_condition = TradeSearchFilter.by_price_range(min_price=1000, max_price=5000)
        listings, cursor = self.repository.find_listings(filter_condition, limit=20)

        # 全ての出品が価格範囲内であることを確認
        for listing in listings:
            assert 1000 <= listing.requested_gold <= 5000

    def test_find_listings_by_equipment_type(self):
        """装備タイプで出品を検索できる"""
        # WEAPONタイプの出品を検索
        filter_condition = TradeSearchFilter(equipment_types=[EquipmentType.WEAPON])
        listings, cursor = self.repository.find_listings(filter_condition, limit=20)

        # 全ての出品がWEAPONであることを確認
        for listing in listings:
            assert listing.item_equipment_type == EquipmentType.WEAPON

    def test_find_listings_by_multiple_equipment_types(self):
        """複数の装備タイプで出品を検索できる"""
        # WEAPONとSHIELDタイプの出品を検索
        filter_condition = TradeSearchFilter(equipment_types=[EquipmentType.WEAPON, EquipmentType.SHIELD])
        listings, cursor = self.repository.find_listings(filter_condition, limit=20)

        # 全ての出品がWEAPONまたはSHIELDであることを確認
        for listing in listings:
            assert listing.item_equipment_type in [EquipmentType.WEAPON, EquipmentType.SHIELD]

    def test_find_listings_by_status_active(self):
        """ステータスで出品を検索できる（アクティブのみ）"""
        # ACTIVEステータスの出品を検索
        filter_condition = TradeSearchFilter(statuses=[TradeStatus.ACTIVE])
        listings, cursor = self.repository.find_listings(filter_condition, limit=20)

        # 全ての出品がACTIVEであることを確認
        for listing in listings:
            assert listing.status == TradeStatus.ACTIVE

    def test_find_listings_by_status_empty_result(self):
        """存在しないステータスで検索すると空の結果が返る"""
        # CANCELLEDステータスの出品を検索（サンプルデータには存在しない）
        filter_condition = TradeSearchFilter(statuses=[TradeStatus.CANCELLED])
        listings, cursor = self.repository.find_listings(filter_condition, limit=20)

        # 結果が空であることを確認
        assert len(listings) == 0

    def test_find_listings_combined_filters_with_status(self):
        """複数のフィルタ条件（ステータス含む）を組み合わせた検索ができる"""
        # EQUIPMENTタイプで、価格が1000以上、ACTIVEステータスの出品を検索
        filter_condition = TradeSearchFilter(
            item_types=[ItemType.EQUIPMENT],
            min_price=1000,
            statuses=[TradeStatus.ACTIVE]
        )
        listings, cursor = self.repository.find_listings(filter_condition, limit=20)

        # 全ての出品が条件を満たしていることを確認
        for listing in listings:
            assert listing.item_type == ItemType.EQUIPMENT
            assert listing.requested_gold >= 1000
            assert listing.status == TradeStatus.ACTIVE

    def test_find_listings_sorted_by_created_at_descending(self):
        """出品が作成日時の降順でソートされている"""
        filter_condition = TradeSearchFilter()
        listings, cursor = self.repository.find_listings(filter_condition, limit=50)

        # 少なくとも2件以上あることを確認
        assert len(listings) >= 2

        # 作成日時の降順でソートされていることを確認
        for i in range(len(listings) - 1):
            assert listings[i].created_at >= listings[i + 1].created_at

    def test_find_listings_cursor_based_pagination_with_created_at(self):
        """created_atベースのページングが機能する"""
        filter_condition = TradeSearchFilter()

        # 最初のページを取得
        first_page, next_cursor = self.repository.find_listings(filter_condition, limit=3)
        assert len(first_page) == 3
        assert next_cursor is not None

        # 次のページを取得
        second_page, final_cursor = self.repository.find_listings(filter_condition, limit=3, cursor=next_cursor)
        assert len(second_page) == 3
        assert final_cursor is not None

        # 1ページ目の最後の出品より2ページ目の最初の出品の方が古いことを確認
        assert first_page[-1].created_at >= second_page[0].created_at


    def test_find_listings_combined_filters(self):
        """複数のフィルタ条件を組み合わせた検索ができる"""
        # EQUIPMENTタイプで、価格が1000以上の出品を検索
        filter_condition = TradeSearchFilter(
            item_types=[ItemType.EQUIPMENT],
            min_price=1000
        )
        listings, cursor = self.repository.find_listings(filter_condition, limit=20)

        # 全ての出品が条件を満たしていることを確認
        for listing in listings:
            assert listing.item_type == ItemType.EQUIPMENT
            assert listing.requested_gold >= 1000

    def test_count_listings_without_filter(self):
        """フィルタなしでcount_listingsを呼び出すと全ての出品数を返す"""
        filter_condition = TradeSearchFilter()
        count = self.repository.count_listings(filter_condition)

        all_listings = self.repository.find_all()
        assert count == len(all_listings)

    def test_count_listings_by_item_type(self):
        """アイテムタイプで出品数をカウントできる"""
        # EQUIPMENTタイプの出品数をカウント
        filter_condition = TradeSearchFilter.by_item_types([ItemType.EQUIPMENT])
        count = self.repository.count_listings(filter_condition)

        # 対応する出品を取得して比較
        listings, _ = self.repository.find_listings(filter_condition, limit=100)
        assert count == len(listings)

    def test_count_listings_by_price_range(self):
        """価格範囲で出品数をカウントできる"""
        # 1000-5000ゴールドの範囲でカウント
        filter_condition = TradeSearchFilter.by_price_range(min_price=1000, max_price=5000)
        count = self.repository.count_listings(filter_condition)

        # 対応する出品を取得して比較
        listings, _ = self.repository.find_listings(filter_condition, limit=100)
        assert count == len(listings)

    def test_count_listings_combined_filters(self):
        """複数のフィルタ条件を組み合わせたカウントができる"""
        # EQUIPMENTタイプで、価格が1000以上の出品をカウント
        filter_condition = TradeSearchFilter(
            item_types=[ItemType.EQUIPMENT],
            min_price=1000
        )
        count = self.repository.count_listings(filter_condition)

        # 対応する出品を取得して比較
        listings, _ = self.repository.find_listings(filter_condition, limit=100)
        assert count == len(listings)

    def test_clear_removes_all_listings(self):
        """clearですべての出品が削除される"""
        # 削除前に出品が存在することを確認
        assert self.repository.get_listing_count() > 0

        # クリア
        self.repository.clear()

        # 削除後に出品が存在しないことを確認
        assert self.repository.get_listing_count() == 0
        all_listings = self.repository.find_all()
        assert len(all_listings) == 0

    def test_get_listing_count_returns_correct_count(self):
        """get_listing_countで正しい出品数を取得できる"""
        count = self.repository.get_listing_count()
        all_listings = self.repository.find_all()
        assert count == len(all_listings)

    def test_sample_data_has_various_item_types(self):
        """サンプルデータに様々なアイテムタイプが含まれている"""
        all_listings = self.repository.find_all()

        item_types = set(listing.item_type for listing in all_listings)
        assert ItemType.EQUIPMENT in item_types
        assert ItemType.CONSUMABLE in item_types
        assert ItemType.MATERIAL in item_types

    def test_sample_data_has_various_rarities(self):
        """サンプルデータに様々なレアリティが含まれている"""
        all_listings = self.repository.find_all()

        rarities = set(listing.item_rarity for listing in all_listings)
        assert Rarity.COMMON in rarities
        assert Rarity.UNCOMMON in rarities
        assert Rarity.RARE in rarities
        assert Rarity.EPIC in rarities

    def test_sample_data_has_various_price_ranges(self):
        """サンプルデータに様々な価格帯が含まれている"""
        all_listings = self.repository.find_all()

        prices = [listing.requested_gold for listing in all_listings]
        min_price = min(prices)
        max_price = max(prices)

        # 安価なアイテム（50ゴールド）と高価なアイテム（15000ゴールド）が存在することを確認
        assert min_price <= 100
        assert max_price >= 10000

    def test_sample_data_has_durability_info(self):
        """サンプルデータに耐久度情報が含まれている"""
        all_listings = self.repository.find_all()

        # 耐久度を持つアイテムと持たないアイテムが両方存在することを確認
        has_durability = any(listing.has_durability for listing in all_listings)
        no_durability = any(not listing.has_durability for listing in all_listings)

        assert has_durability
        assert no_durability

    def test_sample_data_has_various_equipment_types(self):
        """サンプルデータに様々な装備タイプが含まれている"""
        all_listings = self.repository.find_all()

        equipment_listings = [listing for listing in all_listings if listing.is_equipment]
        equipment_types = set(listing.item_equipment_type for listing in equipment_listings)

        # 少なくともWEAPON, ARMOR, SHIELD, HELMET, ACCESSORYの5種類が存在することを確認
        assert EquipmentType.WEAPON in equipment_types
        assert EquipmentType.ARMOR in equipment_types
        assert EquipmentType.SHIELD in equipment_types
        assert EquipmentType.HELMET in equipment_types
        assert EquipmentType.ACCESSORY in equipment_types

    def test_durability_percentage_calculation(self):
        """耐久度の割合計算が正しく機能する"""
        # 耐久度を持つ出品を見つける
        all_listings = self.repository.find_all()
        equipment_with_durability = None

        for listing in all_listings:
            if listing.has_durability and listing.durability_current is not None and listing.durability_max is not None:
                equipment_with_durability = listing
                break

        assert equipment_with_durability is not None

        # 割合計算が正しいことを確認
        expected_percentage = equipment_with_durability.durability_current / equipment_with_durability.durability_max
        assert equipment_with_durability.durability_percentage == expected_percentage
