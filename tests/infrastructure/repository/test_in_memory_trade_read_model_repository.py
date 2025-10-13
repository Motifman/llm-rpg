"""
InMemoryTradeReadModelRepositoryのテスト
"""
import pytest
from datetime import datetime, timedelta
from typing import List, Tuple, Optional

from src.infrastructure.repository.in_memory_trade_read_model_repository import InMemoryTradeReadModelRepository
from src.domain.trade.read_model.trade_read_model import TradeReadModel
from src.domain.trade.repository.trade_read_model_repository import TradeCursor
from src.domain.trade.value_object.trade_id import TradeId
from src.domain.trade.value_object.trade_search_filter import TradeSearchFilter
from src.domain.player.value_object.player_id import PlayerId
from src.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType
from src.domain.trade.enum.trade_enum import TradeStatus
from src.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
from src.domain.item.value_object.item_instance_id import ItemInstanceId


class TestInMemoryTradeReadModelRepository:
    """InMemoryTradeReadModelRepositoryのテストクラス"""

    def setup_method(self):
        """各テストメソッド実行前に呼ばれる"""
        self.repository = InMemoryTradeReadModelRepository()

    def test_find_by_id_existing_trade(self):
        """存在する取引をIDで検索できる"""
        trade = self.repository.find_by_id(TradeId(1))
        assert trade is not None
        assert trade.trade_id == 1
        assert trade.seller_name == "勇者アルス"

    def test_find_by_id_non_existing_trade(self):
        """存在しない取引をIDで検索するとNoneが返る"""
        trade = self.repository.find_by_id(TradeId(999))
        assert trade is None

    def test_find_by_ids_multiple_trades(self):
        """複数の取引をIDリストで検索できる"""
        trade_ids = [TradeId(1), TradeId(2), TradeId(999)]
        trades = self.repository.find_by_ids(trade_ids)

        assert len(trades) == 2
        assert trades[0].trade_id == 1
        assert trades[1].trade_id == 2

    def test_find_all_returns_all_trades(self):
        """find_allですべての取引を取得できる"""
        all_trades = self.repository.find_all()
        assert len(all_trades) >= 15  # サンプルデータが15件以上あるはず

        # 取引IDがユニークであることを確認
        trade_ids = [trade.trade_id for trade in all_trades]
        assert len(trade_ids) == len(set(trade_ids))

    def test_save_and_find_new_trade(self):
        """新しい取引を保存して検索できる"""
        # 新しい取引を作成
        new_trade = TradeReadModel.create_from_trade_and_item(
            trade_id=TradeId(100),
            seller_id=PlayerId(100),
            seller_name="テスト商人",
            buyer_id=None,
            buyer_name=None,
            item_instance_id=ItemInstanceId(100),
            item_name="テストアイテム",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.COMMON,
            item_description="テスト用のアイテム",
            item_equipment_type=EquipmentType.WEAPON,
            durability_current=100,
            durability_max=100,
            requested_gold=TradeRequestedGold(1000),
            status=TradeStatus.ACTIVE,
            created_at=datetime.now()
        )

        # 保存
        saved_trade = self.repository.save(new_trade)

        # 検索して確認
        found_trade = self.repository.find_by_id(TradeId(100))
        assert found_trade is not None
        assert found_trade.trade_id == 100
        assert found_trade.seller_name == "テスト商人"
        assert found_trade.item_name == "テストアイテム"

    def test_delete_existing_trade(self):
        """存在する取引を削除できる"""
        # 削除前に存在することを確認
        trade_before = self.repository.find_by_id(TradeId(1))
        assert trade_before is not None

        # 削除
        result = self.repository.delete(TradeId(1))
        assert result is True

        # 削除後に存在しないことを確認
        trade_after = self.repository.find_by_id(TradeId(1))
        assert trade_after is None

    def test_delete_non_existing_trade(self):
        """存在しない取引を削除しようとするとFalseが返る"""
        result = self.repository.delete(TradeId(999))
        assert result is False


    def test_find_recent_trades_returns_recent_first(self):
        """find_recent_tradesで最新の取引が先頭に返る"""
        trades, cursor = self.repository.find_recent_trades(limit=5)

        assert len(trades) == 5
        # 作成日時で降順ソートされていることを確認
        for i in range(len(trades) - 1):
            assert trades[i].created_at >= trades[i + 1].created_at

    def test_find_recent_trades_with_cursor_pagination(self):
        """find_recent_tradesでカーソルページングが機能する"""
        # 最初のページを取得
        first_page, next_cursor = self.repository.find_recent_trades(limit=3)
        assert len(first_page) == 3
        assert next_cursor is not None

        # 次のページを取得
        second_page, final_cursor = self.repository.find_recent_trades(limit=3, cursor=next_cursor)
        assert len(second_page) == 3
        assert final_cursor is not None

        # 1ページ目の最後の取引より2ページ目の最初の取引の方が古いことを確認
        assert first_page[-1].created_at >= second_page[0].created_at

    def test_find_recent_trades_at_end_returns_no_cursor(self):
        """find_recent_tradesで最後のページではcursorがNoneになる"""
        # 全ての取引を取得するだけのlimitを設定
        all_trades = self.repository.find_all()
        trades, cursor = self.repository.find_recent_trades(limit=len(all_trades))

        assert cursor is None

    def test_find_trades_for_player_returns_player_trades(self):
        """find_trades_for_playerで指定プレイヤーの取引を取得できる"""
        # 勇者アルス（プレイヤーID=1）の取引を取得
        trades, cursor = self.repository.find_trades_for_player(PlayerId(1), limit=10)

        # 勇者は出品者として複数の取引を持っているはず
        assert len(trades) >= 2  # サンプルデータで少なくとも2件

        # 全ての取引がプレイヤー1に関連していることを確認
        for trade in trades:
            assert trade.seller_id == 1 or trade.buyer_id == 1

    def test_find_trades_for_player_with_pagination(self):
        """find_trades_for_playerでページングが機能する"""
        # 最初のページを取得
        first_page, next_cursor = self.repository.find_trades_for_player(PlayerId(1), limit=1)
        assert len(first_page) == 1
        assert next_cursor is not None

        # 次のページを取得
        second_page, final_cursor = self.repository.find_trades_for_player(PlayerId(1), limit=1, cursor=next_cursor)
        assert len(second_page) == 1

        # 異なる取引であることを確認
        assert first_page[0].trade_id != second_page[0].trade_id

    def test_find_active_trades_returns_only_active(self):
        """find_active_tradesでアクティブな取引のみ取得できる"""
        trades, cursor = self.repository.find_active_trades(limit=50)

        # 全ての取引がアクティブであることを確認
        for trade in trades:
            assert trade.is_active
            assert trade.status == "ACTIVE"

        # アクティブな取引の総数を取得して比較
        expected_count = self.repository.get_active_trade_count()
        assert len(trades) <= expected_count

    def test_find_active_trades_with_pagination(self):
        """find_active_tradesでページングが機能する"""
        active_count = self.repository.get_active_trade_count()

        if active_count > 1:
            # 最初のページを取得
            first_page, next_cursor = self.repository.find_active_trades(limit=1)
            assert len(first_page) == 1
            assert next_cursor is not None

            # 次のページを取得
            second_page, final_cursor = self.repository.find_active_trades(limit=1, cursor=next_cursor)
            assert len(second_page) == 1

    def test_search_trades_by_item_name(self):
        """アイテム名で取引を検索できる"""
        # 「剣」を含むアイテムを検索
        filter = TradeSearchFilter.by_item_name("剣")
        trades, cursor = self.repository.search_trades(filter, limit=10)

        # 検索結果に「剣」が含まれるアイテムがあることを確認
        sword_found = any("剣" in trade.item_name for trade in trades)
        assert sword_found

    def test_search_trades_by_item_type(self):
        """アイテムタイプで取引を検索できる"""
        # EQUIPMENTタイプの取引を検索
        filter = TradeSearchFilter.by_item_types([ItemType.EQUIPMENT])
        trades, cursor = self.repository.search_trades(filter, limit=20)

        # 全ての取引がEQUIPMENTであることを確認
        for trade in trades:
            assert trade.item_type == "equipment"

    def test_search_trades_by_rarity(self):
        """レアリティで取引を検索できる"""
        # RAREレアリティの取引を検索
        filter = TradeSearchFilter(rarities=[Rarity.RARE])
        trades, cursor = self.repository.search_trades(filter, limit=20)

        # 全ての取引がRAREであることを確認
        for trade in trades:
            assert trade.item_rarity == "rare"

    def test_search_trades_by_price_range(self):
        """価格範囲で取引を検索できる"""
        # 1000-5000ゴールドの範囲で検索
        filter = TradeSearchFilter.by_price_range(min_price=1000, max_price=5000)
        trades, cursor = self.repository.search_trades(filter, limit=20)

        # 全ての取引が価格範囲内であることを確認
        for trade in trades:
            assert 1000 <= trade.requested_gold <= 5000

    def test_search_trades_by_status(self):
        """ステータスで取引を検索できる"""
        # アクティブな取引のみ検索
        filter = TradeSearchFilter.active_only()
        trades, cursor = self.repository.search_trades(filter, limit=20)

        # 全ての取引がACTIVEであることを確認
        for trade in trades:
            assert trade.status == "ACTIVE"

    def test_search_trades_combined_filters(self):
        """複数のフィルタ条件を組み合わせた検索ができる"""
        # EQUIPMENTタイプで、価格が1000以上、アクティブな取引を検索
        filter = TradeSearchFilter(
            item_types=[ItemType.EQUIPMENT],
            min_price=1000,
            statuses=[TradeStatus.ACTIVE]
        )
        trades, cursor = self.repository.search_trades(filter, limit=20)

        # 全ての取引が条件を満たしていることを確認
        for trade in trades:
            assert trade.item_type == "equipment"
            assert trade.requested_gold >= 1000
            assert trade.status == "ACTIVE"

    def test_search_trades_with_pagination(self):
        """search_tradesでページングが機能する"""
        # アクティブな取引を検索
        filter = TradeSearchFilter.active_only()

        # アクティブな取引の総数を取得
        active_count = self.repository.get_active_trade_count()

        if active_count >= 4:
            # アクティブな取引が4件以上ある場合のみページングテスト
            # 最初のページを取得
            first_page, next_cursor = self.repository.search_trades(filter, limit=2)
            assert len(first_page) == 2
            assert next_cursor is not None

            # 次のページを取得
            second_page, final_cursor = self.repository.search_trades(filter, limit=2, cursor=next_cursor)
            assert len(second_page) == 2
        else:
            # アクティブな取引が少ない場合は、少なくとも1件以上取得できることを確認
            first_page, next_cursor = self.repository.search_trades(filter, limit=2)
            assert len(first_page) > 0

    def test_clear_removes_all_trades(self):
        """clearですべての取引が削除される"""
        # 削除前に取引が存在することを確認
        assert self.repository.get_trade_count() > 0

        # クリア
        self.repository.clear()

        # 削除後に取引が存在しないことを確認
        assert self.repository.get_trade_count() == 0
        all_trades = self.repository.find_all()
        assert len(all_trades) == 0

    def test_get_trade_count_returns_correct_count(self):
        """get_trade_countで正しい取引数を取得できる"""
        count = self.repository.get_trade_count()
        all_trades = self.repository.find_all()
        assert count == len(all_trades)

    def test_get_active_trade_count_returns_only_active(self):
        """get_active_trade_countでアクティブな取引数のみを取得できる"""
        active_count = self.repository.get_active_trade_count()
        completed_count = self.repository.get_completed_trade_count()

        total_count = self.repository.get_trade_count()
        assert active_count + completed_count <= total_count  # CANCELLEDも存在する

    def test_sample_data_has_various_item_types(self):
        """サンプルデータに様々なアイテムタイプが含まれている"""
        all_trades = self.repository.find_all()

        item_types = set(trade.item_type for trade in all_trades)
        assert "equipment" in item_types
        assert "consumable" in item_types
        assert "material" in item_types

    def test_sample_data_has_various_rarities(self):
        """サンプルデータに様々なレアリティが含まれている"""
        all_trades = self.repository.find_all()

        rarities = set(trade.item_rarity for trade in all_trades)
        assert "common" in rarities
        assert "uncommon" in rarities
        assert "rare" in rarities
        assert "epic" in rarities

    def test_sample_data_has_various_statuses(self):
        """サンプルデータに様々なステータスが含まれている"""
        all_trades = self.repository.find_all()

        statuses = set(trade.status for trade in all_trades)
        assert "ACTIVE" in statuses
        assert "COMPLETED" in statuses
        assert "CANCELLED" in statuses

    def test_sample_data_has_various_price_ranges(self):
        """サンプルデータに様々な価格帯が含まれている"""
        all_trades = self.repository.find_all()

        prices = [trade.requested_gold for trade in all_trades]
        min_price = min(prices)
        max_price = max(prices)

        # 安価なアイテム（50ゴールド）と高価なアイテム（15000ゴールド）が存在することを確認
        assert min_price <= 100
        assert max_price >= 10000
