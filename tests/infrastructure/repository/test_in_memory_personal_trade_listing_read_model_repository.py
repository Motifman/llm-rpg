"""
InMemoryPersonalTradeListingReadModelRepositoryのテスト
"""
import pytest
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

from ai_rpg_world.infrastructure.repository.in_memory_personal_trade_listing_read_model_repository import InMemoryPersonalTradeListingReadModelRepository
from ai_rpg_world.domain.trade.read_model.personal_trade_listing_read_model import PersonalTradeListingReadModel
from ai_rpg_world.domain.trade.repository.cursor import ListingCursor
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType


class TestInMemoryPersonalTradeListingReadModelRepository:
    """InMemoryPersonalTradeListingReadModelRepositoryのテストクラス"""

    def setup_method(self):
        """各テストメソッド実行前に呼ばれる"""
        self.repository = InMemoryPersonalTradeListingReadModelRepository()

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
        assert len(all_listings) >= 7  # サンプルデータが7件以上あるはず

        # 出品IDがユニークであることを確認
        listing_ids = [listing.trade_id for listing in all_listings]
        assert len(listing_ids) == len(set(listing_ids))

    def test_save_and_find_new_listing(self):
        """新しい出品を保存して検索できる"""
        # 新しい出品を作成
        new_listing = PersonalTradeListingReadModel.create_from_trade_data(
            trade_id=TradeId(100),
            item_spec_id=ItemSpecId(100),
            item_instance_id=ItemInstanceId(100),
            recipient_player_id=PlayerId(1),
            item_name="テストアイテム",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.COMMON,
            item_equipment_type=EquipmentType.WEAPON,
            durability_current=100,
            durability_max=100,
            requested_gold=1000,
            seller_name="テスト売り手",
            created_at=datetime.now()
        )

        # 保存
        saved_listing = self.repository.save(new_listing)

        # 検索して確認
        found_listing = self.repository.find_by_id(TradeId(100))
        assert found_listing is not None
        assert found_listing.trade_id == TradeId(100)
        assert found_listing.item_name == "テストアイテム"
        assert found_listing.requested_gold == 1000
        assert found_listing.recipient_player_id == PlayerId(1)

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

    def test_find_for_player_returns_only_player_trades(self):
        """find_for_playerで指定したプレイヤーの取引のみが返る"""
        player_id = PlayerId(1)
        listings, cursor = self.repository.find_for_player(player_id, limit=20)

        # プレイヤー1宛の取引のみが返ることを確認
        for listing in listings:
            assert listing.recipient_player_id == player_id

    def test_find_for_player_with_limit(self):
        """limitを指定してプレイヤーの取引を取得できる"""
        player_id = PlayerId(1)
        listings, cursor = self.repository.find_for_player(player_id, limit=2)

        assert len(listings) == 2
        assert cursor is not None  # limit未満ではないのでcursorが存在

    def test_find_for_player_with_cursor_pagination(self):
        """find_for_playerでカーソルページングが機能する"""
        player_id = PlayerId(1)

        # 最初のページを取得
        first_page, next_cursor = self.repository.find_for_player(player_id, limit=2)
        assert len(first_page) == 2
        assert next_cursor is not None

        # 次のページを取得
        second_page, final_cursor = self.repository.find_for_player(player_id, limit=2, cursor=next_cursor)
        assert len(second_page) == 2
        assert final_cursor is not None

        # 1ページ目の最後の出品より2ページ目の最初の出品の方がIDが小さいことを確認
        assert int(first_page[-1].trade_id) > int(second_page[0].trade_id)

    def test_find_for_player_at_end_returns_no_cursor(self):
        """find_for_playerで最後のページではcursorがNoneになる"""
        player_id = PlayerId(1)

        # プレイヤーの全取引を取得するだけのlimitを設定
        player_trade_count = self.repository.count_for_player(player_id)
        listings, cursor = self.repository.find_for_player(player_id, limit=player_trade_count)

        assert cursor is None

    def test_find_for_player_sorted_by_created_at_descending(self):
        """プレイヤーの取引が作成日時の降順でソートされている"""
        player_id = PlayerId(1)
        listings, cursor = self.repository.find_for_player(player_id, limit=10)

        # 少なくとも2件以上あることを確認
        assert len(listings) >= 2

        # 作成日時の降順でソートされていることを確認
        for i in range(len(listings) - 1):
            assert listings[i].created_at >= listings[i + 1].created_at

    def test_find_for_player_different_players_get_different_results(self):
        """異なるプレイヤーに対して異なる取引が返る"""
        player_1_id = PlayerId(1)
        player_2_id = PlayerId(2)

        player_1_trades, _ = self.repository.find_for_player(player_1_id, limit=20)
        player_2_trades, _ = self.repository.find_for_player(player_2_id, limit=20)

        # 両方のプレイヤーに取引があることを確認
        assert len(player_1_trades) > 0
        assert len(player_2_trades) > 0

        # プレイヤー1の取引にプレイヤー2の取引が含まれていないことを確認
        player_1_trade_ids = {listing.trade_id for listing in player_1_trades}
        player_2_trade_ids = {listing.trade_id for listing in player_2_trades}

        assert len(player_1_trade_ids & player_2_trade_ids) == 0  # 共通の取引がない

    def test_find_for_player_no_trades_for_player(self):
        """取引のないプレイヤーに対して空の結果が返る"""
        non_existing_player_id = PlayerId(999)
        listings, cursor = self.repository.find_for_player(non_existing_player_id, limit=20)

        assert len(listings) == 0
        assert cursor is None

    def test_count_for_player_returns_correct_count(self):
        """count_for_playerで正しい取引数を取得できる"""
        player_id = PlayerId(1)
        count = self.repository.count_for_player(player_id)

        # 対応する取引を取得して比較
        listings, _ = self.repository.find_for_player(player_id, limit=100)
        assert count == len(listings)

    def test_count_for_player_no_trades_for_player(self):
        """取引のないプレイヤーに対してcount_for_playerが0を返す"""
        non_existing_player_id = PlayerId(999)
        count = self.repository.count_for_player(non_existing_player_id)

        assert count == 0

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

        # 少なくともWEAPON, ARMOR, SHIELDの3種類が存在することを確認
        assert EquipmentType.WEAPON in equipment_types
        assert EquipmentType.ARMOR in equipment_types
        assert EquipmentType.SHIELD in equipment_types

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

    def test_sample_data_has_correct_recipient_players(self):
        """サンプルデータに正しい受信者プレイヤーが設定されている"""
        all_listings = self.repository.find_all()

        recipient_ids = set(listing.recipient_player_id for listing in all_listings)
        assert PlayerId(1) in recipient_ids  # プレイヤー1宛の取引がある
        assert PlayerId(2) in recipient_ids  # プレイヤー2宛の取引がある
