"""
InMemoryRecentTradeReadModelRepositoryのテスト
"""
import pytest
from datetime import datetime, timedelta
from typing import List

from src.infrastructure.repository.in_memory_recent_trade_read_model_repository import InMemoryRecentTradeReadModelRepository
from src.domain.trade.read_model.recent_trade_read_model import RecentTradeReadModel, RecentTradeData
from src.domain.item.value_object.item_spec_id import ItemSpecId


class TestInMemoryRecentTradeReadModelRepository:
    """InMemoryRecentTradeReadModelRepositoryのテストクラス"""

    def setup_method(self):
        """各テストメソッド実行前に呼ばれる"""
        self.repository = InMemoryRecentTradeReadModelRepository()

    def test_setup_creates_sample_data(self):
        """初期化時にサンプルデータが作成される"""
        all_read_models = self.repository.find_all()
        assert len(all_read_models) == 15

        # 取引履歴があるアイテムとないアイテムが混在していることを確認
        items_with_trades = self.repository.get_items_with_trades()
        items_without_trades = self.repository.get_items_without_trades()

        assert len(items_with_trades) == 14
        assert len(items_without_trades) == 1
        assert "伝説の剣" in items_without_trades

    def test_find_by_id_existing_read_model(self):
        """存在するReadModelをIDで検索できる"""
        read_model = self.repository.find_by_id(ItemSpecId(1))

        assert read_model is not None
        assert read_model.item_spec_id == ItemSpecId(1)
        assert read_model.item_name == "鋼の剣"
        assert len(read_model.recent_trades) == 15

    def test_find_by_id_non_existing_read_model(self):
        """存在しないReadModelをIDで検索するとNoneが返る"""
        read_model = self.repository.find_by_id(ItemSpecId(999))
        assert read_model is None

    def test_find_by_ids_multiple_read_models(self):
        """複数のReadModelをIDリストで検索できる"""
        item_spec_ids = [ItemSpecId(1), ItemSpecId(2), ItemSpecId(999)]
        read_models = self.repository.find_by_ids(item_spec_ids)

        assert len(read_models) == 2
        assert read_models[0].item_spec_id == ItemSpecId(1)
        assert read_models[1].item_spec_id == ItemSpecId(2)

    def test_find_all_returns_all_read_models(self):
        """find_allですべてのReadModelを取得できる"""
        all_read_models = self.repository.find_all()
        assert len(all_read_models) == 15

        # 全てのReadModelが正しい構造を持っていることを確認
        for read_model in all_read_models:
            assert isinstance(read_model, RecentTradeReadModel)
            assert isinstance(read_model.item_spec_id, ItemSpecId)
            assert isinstance(read_model.item_name, str)
            assert isinstance(read_model.recent_trades, List)
            assert isinstance(read_model.last_updated, datetime)

    def test_save_new_read_model(self):
        """新しいReadModelを保存できる"""
        # 新しいReadModelを作成
        new_trades = [
            RecentTradeData(trade_id=1001, price=1000, traded_at=datetime.now())
        ]
        new_read_model = RecentTradeReadModel.create_from_item_and_trades(
            item_spec_id=ItemSpecId(100),
            item_name="テストアイテム",
            recent_trades=new_trades,
            last_updated=datetime.now()
        )

        saved_read_model = self.repository.save(new_read_model)

        # 保存されたReadModelを取得して確認
        retrieved = self.repository.find_by_id(ItemSpecId(100))
        assert retrieved is not None
        assert retrieved.item_name == "テストアイテム"
        assert len(retrieved.recent_trades) == 1
        assert retrieved.recent_trades[0].price == 1000

    def test_save_existing_read_model_updates(self):
        """既存のReadModelを更新できる"""
        # 既存のReadModelを取得して更新
        read_model = self.repository.find_by_id(ItemSpecId(1))
        assert read_model is not None

        # 取引履歴を追加
        new_trade = RecentTradeData(
            trade_id=9999,
            price=999,
            traded_at=datetime.now()
        )
        updated_trades = read_model.recent_trades + [new_trade]

        updated_read_model = RecentTradeReadModel.create_from_item_and_trades(
            item_spec_id=read_model.item_spec_id,
            item_name=read_model.item_name,
            recent_trades=updated_trades,
            last_updated=datetime.now()
        )

        self.repository.save(updated_read_model)

        # 更新されたことを確認
        retrieved = self.repository.find_by_id(ItemSpecId(1))
        assert retrieved is not None
        assert len(retrieved.recent_trades) == 16  # 元の15件 + 1件
        assert retrieved.recent_trades[-1].price == 999

    def test_delete_existing_read_model(self):
        """既存のReadModelを削除できる"""
        # 削除前の確認
        read_model = self.repository.find_by_id(ItemSpecId(1))
        assert read_model is not None

        # 削除実行
        result = self.repository.delete(ItemSpecId(1))
        assert result is True

        # 削除されたことを確認
        deleted_read_model = self.repository.find_by_id(ItemSpecId(1))
        assert deleted_read_model is None

    def test_delete_non_existing_read_model(self):
        """存在しないReadModelを削除しようとするとFalseが返る"""
        result = self.repository.delete(ItemSpecId(999))
        assert result is False


    def test_find_by_item_name_existing_item(self):
        """存在するアイテム名でReadModelを検索できる"""
        read_model = self.repository.find_by_item_name("鋼の剣")

        assert read_model is not None
        assert read_model.item_name == "鋼の剣"
        assert read_model.item_spec_id == ItemSpecId(1)
        assert len(read_model.recent_trades) == 15

    def test_find_by_item_name_non_existing_item(self):
        """存在しないアイテム名で検索するとNoneが返る"""
        read_model = self.repository.find_by_item_name("存在しないアイテム")
        assert read_model is None

    def test_find_by_item_name_case_sensitive(self):
        """アイテム名検索は大文字小文字を区別する"""
        # 小文字で検索
        read_model_lower = self.repository.find_by_item_name("鋼の剣")
        assert read_model_lower is not None

        # 大文字で検索（存在しないはず）
        read_model_upper = self.repository.find_by_item_name("鋼の剣")  # 同じ文字列なので同じ結果
        assert read_model_upper is not None

        # 異なるケースのアイテム名で検索
        read_model_different = self.repository.find_by_item_name("Steel Sword")
        assert read_model_different is None

    def test_sample_data_trade_count_variation(self):
        """サンプルデータの取引件数が期待通りである"""
        test_cases = [
            ("鋼の剣", 15),
            ("魔法の杖", 8),
            ("回復薬", 25),
            ("ドラゴンスケールアーマー", 3),
            ("鉄の盾", 12),
            ("冒険者のブーツ", 5),
            ("魔法の書", 7),
            ("珍しい薬草", 10),
            ("丈夫な縄", 20),
            ("伝説の剣", 0),  # 取引履歴なし
            ("上級回復薬", 6),
            ("輝く宝石", 4),
            ("魔法の盾", 2),
            ("勇者の兜", 9),
            ("魔法の指輪", 3),
        ]

        for item_name, expected_count in test_cases:
            read_model = self.repository.find_by_item_name(item_name)
            assert read_model is not None, f"Item {item_name} not found"
            assert len(read_model.recent_trades) == expected_count, \
                f"Item {item_name} has {len(read_model.recent_trades)} trades, expected {expected_count}"

    def test_sample_data_trades_ordered_by_time_descending(self):
        """サンプルデータの取引が時系列順（新しい順）に並んでいる"""
        read_model = self.repository.find_by_item_name("鋼の剣")
        assert read_model is not None
        assert len(read_model.recent_trades) > 1

        # 時系列順（新しい順）に並んでいることを確認
        for i in range(len(read_model.recent_trades) - 1):
            assert read_model.recent_trades[i].traded_at >= read_model.recent_trades[i + 1].traded_at

    def test_sample_data_price_variation_within_range(self):
        """サンプルデータの価格変動が期待範囲内である"""
        # 鋼の剣の場合（基準価格500、±20%変動）
        read_model = self.repository.find_by_item_name("鋼の剣")
        assert read_model is not None

        prices = [trade.price for trade in read_model.recent_trades]
        min_price = min(prices)
        max_price = max(prices)

        # ±20%の変動範囲内であることを確認
        assert min_price >= int(500 * 0.8)  # 最低400
        assert max_price <= int(500 * 1.2)  # 最高600

    def test_sample_data_trade_ids_unique(self):
        """サンプルデータの取引IDがユニークである"""
        all_trade_ids = []
        for read_model in self.repository.find_all():
            for trade in read_model.recent_trades:
                all_trade_ids.append(trade.trade_id)

        # 重複がないことを確認
        assert len(all_trade_ids) == len(set(all_trade_ids))

    def test_clear_removes_all_data(self):
        """clearですべてのデータを削除できる"""
        # 初期状態を確認
        assert self.repository.get_read_model_count() == 15

        # クリア実行
        self.repository.clear()

        # クリアされたことを確認
        assert self.repository.get_read_model_count() == 0
        assert len(self.repository.find_all()) == 0

        # 検索しても何も見つからない
        read_model = self.repository.find_by_item_name("鋼の剣")
        assert read_model is None


    def test_get_items_with_trades_returns_correct_items(self):
        """get_items_with_tradesが取引履歴があるアイテムのみを返す"""
        items_with_trades = self.repository.get_items_with_trades()

        assert len(items_with_trades) == 14
        assert "鋼の剣" in items_with_trades
        assert "伝説の剣" not in items_with_trades

        # 実際に取引履歴があることを確認
        for item_name in items_with_trades:
            read_model = self.repository.find_by_item_name(item_name)
            assert read_model is not None
            assert len(read_model.recent_trades) > 0

    def test_get_items_without_trades_returns_correct_items(self):
        """get_items_without_tradesが取引履歴がないアイテムのみを返す"""
        items_without_trades = self.repository.get_items_without_trades()

        assert len(items_without_trades) == 1
        assert "伝説の剣" in items_without_trades

        # 実際に取引履歴がないことを確認
        read_model = self.repository.find_by_item_name("伝説の剣")
        assert read_model is not None
        assert len(read_model.recent_trades) == 0

    def test_read_model_properties_calculated_correctly(self):
        """ReadModelのプロパティが正しく計算される"""
        # 取引履歴があるアイテム
        read_model_with_trades = self.repository.find_by_item_name("鋼の剣")
        assert read_model_with_trades is not None
        assert read_model_with_trades.has_recent_trades is True
        assert read_model_with_trades.latest_trade_price > 0
        assert read_model_with_trades.total_recent_trades == 15

        # 取引履歴がないアイテム
        read_model_without_trades = self.repository.find_by_item_name("伝説の剣")
        assert read_model_without_trades is not None
        assert read_model_without_trades.has_recent_trades is False
        assert read_model_without_trades.latest_trade_price == 0
        assert read_model_without_trades.total_recent_trades == 0
