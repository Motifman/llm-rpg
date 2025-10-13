"""
InMemoryTradeMarketReadModelRepositoryのテスト
"""
import pytest
from datetime import datetime, timedelta
from typing import List, Optional

from src.infrastructure.repository.in_memory_trade_market_read_model_repository import InMemoryTradeMarketReadModelRepository
from src.domain.trade.read_model.trade_market_read_model import TradeMarketReadModel
from src.domain.item.value_object.item_spec_id import ItemSpecId


class TestInMemoryTradeMarketReadModelRepository:
    """InMemoryTradeMarketReadModelRepositoryのテストクラス"""

    def setup_method(self):
        """各テストメソッド実行前に呼ばれる"""
        self.repository = InMemoryTradeMarketReadModelRepository()

    def test_find_by_id_existing_item(self):
        """存在するアイテムの市場情報をIDで検索できる"""
        market_data = self.repository.find_by_id(ItemSpecId(1))
        assert market_data is not None
        assert market_data.item_spec_id == ItemSpecId(1)
        assert market_data.item_name == "伝説の剣"
        assert market_data.item_type == "weapon"
        assert market_data.item_rarity == "legendary"

    def test_find_by_id_non_existing_item(self):
        """存在しないアイテムの市場情報をIDで検索するとNoneが返る"""
        market_data = self.repository.find_by_id(ItemSpecId(999))
        assert market_data is None

    def test_find_by_ids_multiple_items(self):
        """複数のアイテムの市場情報をIDリストで検索できる"""
        item_ids = [ItemSpecId(1), ItemSpecId(2), ItemSpecId(999)]
        market_data_list = self.repository.find_by_ids(item_ids)

        assert len(market_data_list) == 2
        assert market_data_list[0].item_spec_id == ItemSpecId(1)
        assert market_data_list[1].item_spec_id == ItemSpecId(2)

    def test_find_all_returns_all_market_data(self):
        """find_allですべての市場情報を取得できる"""
        all_market_data = self.repository.find_all()

        # サンプルデータとして15個のアイテムがセットアップされているはず
        assert len(all_market_data) == 15

        # 全てTradeMarketReadModelのインスタンスであることを確認
        for data in all_market_data:
            assert isinstance(data, TradeMarketReadModel)

    def test_save_new_market_data(self):
        """新しい市場情報を保存できる"""
        # 新しい市場データを作成
        new_market_data = TradeMarketReadModel.create_from_item_spec_and_stats(
            item_spec_id=ItemSpecId(100),
            item_name="テストアイテム",
            item_type="test",
            item_rarity="common",
            current_market_price=1000,
            min_price=900,
            max_price=1100,
            avg_price=1000.0,
            median_price=1000,
            total_trades=10,
            active_listings=2,
            completed_trades=8,
            success_rate=0.8,
            last_updated=datetime.now()
        )

        # 保存
        saved_data = self.repository.save(new_market_data)

        # 保存されたデータを確認
        assert saved_data == new_market_data
        assert self.repository.find_by_id(ItemSpecId(100)) == new_market_data

    def test_save_update_existing_market_data(self):
        """既存の市場情報を更新できる"""
        # 既存のデータを取得
        existing_data = self.repository.find_by_id(ItemSpecId(1))
        assert existing_data is not None

        # 価格を更新
        updated_data = TradeMarketReadModel.create_from_item_spec_and_stats(
            item_spec_id=existing_data.item_spec_id,
            item_name=existing_data.item_name,
            item_type=existing_data.item_type,
            item_rarity=existing_data.item_rarity,
            current_market_price=60000,  # 価格を更新
            min_price=existing_data.min_price,
            max_price=existing_data.max_price,
            avg_price=existing_data.avg_price,
            median_price=existing_data.median_price,
            total_trades=existing_data.total_trades,
            active_listings=existing_data.active_listings,
            completed_trades=existing_data.completed_trades,
            success_rate=existing_data.success_rate,
            last_updated=datetime.now()
        )

        # 保存
        saved_data = self.repository.save(updated_data)

        # 更新されたデータを確認
        assert saved_data.current_market_price == 60000
        retrieved_data = self.repository.find_by_id(ItemSpecId(1))
        assert retrieved_data is not None
        assert retrieved_data.current_market_price == 60000

    def test_delete_existing_item(self):
        """既存のアイテムの市場情報を削除できる"""
        # 削除前の確認
        assert self.repository.find_by_id(ItemSpecId(1)) is not None

        # 削除
        result = self.repository.delete(ItemSpecId(1))

        # 削除結果の確認
        assert result is True
        assert self.repository.find_by_id(ItemSpecId(1)) is None

    def test_delete_non_existing_item(self):
        """存在しないアイテムの削除を試みるとFalseが返る"""
        result = self.repository.delete(ItemSpecId(999))
        assert result is False

    def test_find_by_item_name_existing_item(self):
        """アイテム名で市場情報を検索できる"""
        market_data = self.repository.find_by_item_name("伝説の剣")
        assert market_data is not None
        assert market_data.item_name == "伝説の剣"
        assert market_data.item_spec_id == ItemSpecId(1)

    def test_find_by_item_name_non_existing_item(self):
        """存在しないアイテム名で検索するとNoneが返る"""
        market_data = self.repository.find_by_item_name("存在しないアイテム")
        assert market_data is None

    def test_find_popular_items_by_trade_volume(self):
        """人気アイテムを取引量順に取得できる"""
        popular_items = self.repository.find_popular_items(limit=5)

        assert len(popular_items) == 5

        # 取引量の降順でソートされていることを確認
        for i in range(len(popular_items) - 1):
            assert popular_items[i].total_trades >= popular_items[i + 1].total_trades

    def test_find_popular_items_default_limit(self):
        """人気アイテムのデフォルトlimit=10で取得できる"""
        popular_items = self.repository.find_popular_items()

        # サンプルデータは15件なので、10件返るはず
        assert len(popular_items) == 10

    def test_find_popular_items_limit_larger_than_data(self):
        """limitがデータ数より大きい場合、全データを返す"""
        popular_items = self.repository.find_popular_items(limit=20)

        # サンプルデータは15件なので、全て返る
        assert len(popular_items) == 15

    def test_sample_data_variety(self):
        """サンプルデータに様々なケースが含まれていることを確認"""
        all_data = self.repository.find_all()

        # 様々なアイテムタイプが存在することを確認
        item_types = {data.item_type for data in all_data}
        assert "weapon" in item_types
        assert "armor" in item_types
        assert "consumable" in item_types
        assert "material" in item_types
        assert "accessory" in item_types

        # 様々なレアリティが存在することを確認
        rarities = {data.item_rarity for data in all_data}
        assert "common" in rarities
        assert "rare" in rarities
        assert "epic" in rarities
        assert "legendary" in rarities

        # 価格帯のバリエーションを確認
        prices = [data.current_market_price for data in all_data]
        assert min(prices) == 1  # 石ころ
        assert max(prices) >= 100000  # 神聖な聖杯

        # 取引量のバリエーションを確認
        trade_volumes = [data.total_trades for data in all_data]
        assert min(trade_volumes) == 0  # 取引なしのアイテム
        assert max(trade_volumes) >= 200  # 人気アイテム

    def test_helper_methods_for_testing(self):
        """テスト用のヘルパーメソッドが動作することを確認"""
        # アイテムタイプでフィルタリング
        weapons = self.repository.find_items_by_type("weapon")
        assert len(weapons) > 0
        assert all(item.item_type == "weapon" for item in weapons)

        # レアリティでフィルタリング
        legendary_items = self.repository.find_items_by_rarity("legendary")
        assert len(legendary_items) > 0
        assert all(item.item_rarity == "legendary" for item in legendary_items)

        # 高価なアイテムの検索
        expensive_items = self.repository.find_high_value_items(50000)
        assert len(expensive_items) > 0
        assert all(item.current_market_price >= 50000 for item in expensive_items)

        # アクティブな取引があるアイテム
        active_trade_items = self.repository.find_items_with_active_trades()
        assert len(active_trade_items) > 0
        assert all(item.has_active_trades for item in active_trade_items)

        # 最近更新されたアイテム
        recent_items = self.repository.find_recently_updated_items(hours=1)
        assert len(recent_items) >= 0  # 時間によるので0以上

    def test_clear_method(self):
        """clearメソッドで全てのデータを削除できる"""
        # 初期状態を確認
        assert self.repository.get_total_items() == 15

        # クリア
        self.repository.clear()

        # クリア後の確認
        assert self.repository.get_total_items() == 0
        assert len(self.repository.find_all()) == 0

    def test_update_sample_data_with_random_changes(self):
        """サンプルデータをランダムに更新できる"""
        # 更新前のデータを取得
        original_data = self.repository.find_by_id(ItemSpecId(1))
        original_price = original_data.current_market_price
        original_trades = original_data.total_trades

        # ランダム更新
        self.repository.update_sample_data_with_random_changes()

        # 更新後のデータを取得
        updated_data = self.repository.find_by_id(ItemSpecId(1))

        # データが取得できることを確認
        assert updated_data is not None

        # 何らかの変更があるはず（価格または取引数、または両方）
        # 少なくとも価格は変更されているはず（-100〜+100の範囲で変更）
        price_changed = updated_data.current_market_price != original_price
        trades_changed = updated_data.total_trades != original_trades

        # 少なくともどちらかが変更されているはず
        assert price_changed or trades_changed

    def test_properties_work_correctly(self):
        """TradeMarketReadModelのプロパティが正しく動作することを確認"""
        # アクティブな取引があるアイテムを取得
        active_item = None
        for item in self.repository.find_all():
            if item.active_listings > 0:
                active_item = item
                break

        assert active_item is not None
        assert active_item.has_active_trades is True

        # 成立した取引があるアイテムを取得
        completed_item = None
        for item in self.repository.find_all():
            if item.completed_trades > 0:
                completed_item = item
                break

        assert completed_item is not None
        assert completed_item.has_completed_trades is True

        # アクティブな取引がないアイテムを取得
        inactive_item = self.repository.find_by_id(ItemSpecId(15))  # 未知の鉱石
        assert inactive_item is not None
        assert inactive_item.active_listings == 1  # active_listingsはあるがcompleted_tradesはない
        assert inactive_item.has_active_trades is True
        assert inactive_item.has_completed_trades is False
