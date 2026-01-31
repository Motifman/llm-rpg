"""
InMemoryItemTradeStatisticsReadModelRepository - ItemTradeStatisticsReadModelを使用するインメモリ実装
"""
from typing import List, Optional, Dict
from datetime import datetime, timedelta

from src.domain.trade.repository.item_trade_statistics_read_model_repository import ItemTradeStatisticsReadModelRepository
from src.domain.trade.read_model.item_trade_statistics_read_model import ItemTradeStatisticsReadModel
from src.domain.item.value_object.item_spec_id import ItemSpecId


class InMemoryItemTradeStatisticsReadModelRepository(ItemTradeStatisticsReadModelRepository):
    """ItemTradeStatisticsReadModelを使用するインメモリリポジトリ"""

    def __init__(self):
        self._statistics: Dict[ItemSpecId, ItemTradeStatisticsReadModel] = {}

        # サンプル統計データを作成
        self._setup_sample_data()

    def _setup_sample_data(self):
        """サンプル統計データのセットアップ"""
        # 現在の時間を基準に統計データを作成
        base_time = datetime.now()

        # 様々なアイテムの統計情報を作成

        # 1. 鋼の剣の統計（取引履歴あり）
        sword_stats = self._create_sample_statistics(
            item_spec_id=1,
            min_price=400,
            max_price=600,
            avg_price=485.0,
            median_price=480,
            total_trades=15,
            success_rate=0.87,
            last_updated=base_time - timedelta(hours=1)
        )
        self._statistics[ItemSpecId(1)] = sword_stats

        # 2. 魔法の杖の統計（取引履歴あり）
        staff_stats = self._create_sample_statistics(
            item_spec_id=2,
            min_price=1000,
            max_price=1500,
            avg_price=1180.0,
            median_price=1150,
            total_trades=8,
            success_rate=0.75,
            last_updated=base_time - timedelta(minutes=30)
        )
        self._statistics[ItemSpecId(2)] = staff_stats

        # 3. 回復薬の統計（取引履歴あり）
        potion_stats = self._create_sample_statistics(
            item_spec_id=3,
            min_price=120,
            max_price=200,
            avg_price=156.0,
            median_price=150,
            total_trades=45,
            success_rate=0.92,
            last_updated=base_time - timedelta(minutes=15)
        )
        self._statistics[ItemSpecId(3)] = potion_stats

        # 4. ドラゴンスケールアーマーの統計（取引履歴あり、レア）
        armor_stats = self._create_sample_statistics(
            item_spec_id=4,
            min_price=4500,
            max_price=5500,
            avg_price=4980.0,
            median_price=4950,
            total_trades=3,
            success_rate=0.67,
            last_updated=base_time - timedelta(hours=2)
        )
        self._statistics[ItemSpecId(4)] = armor_stats

        # 5. 鉄の盾の統計（取引履歴あり）
        shield_stats = self._create_sample_statistics(
            item_spec_id=5,
            min_price=250,
            max_price=350,
            avg_price=295.0,
            median_price=290,
            total_trades=12,
            success_rate=0.83,
            last_updated=base_time - timedelta(hours=1, minutes=30)
        )
        self._statistics[ItemSpecId(5)] = shield_stats

        # 6. 輝く宝石の統計（取引履歴あり、高額）
        gem_stats = self._create_sample_statistics(
            item_spec_id=6,
            min_price=2000,
            max_price=3000,
            avg_price=2480.0,
            median_price=2450,
            total_trades=5,
            success_rate=0.80,
            last_updated=base_time - timedelta(hours=3)
        )
        self._statistics[ItemSpecId(6)] = gem_stats

        # 7. 伝説の剣の統計（取引履歴なし - 新規アイテム）
        legendary_sword_stats = self._create_sample_statistics(
            item_spec_id=7,
            min_price=None,
            max_price=None,
            avg_price=None,
            median_price=None,
            total_trades=0,
            success_rate=0.0,
            last_updated=base_time - timedelta(days=1)
        )
        self._statistics[ItemSpecId(7)] = legendary_sword_stats

        # 8. 上級回復薬の統計（取引履歴あり）
        advanced_potion_stats = self._create_sample_statistics(
            item_spec_id=10,
            min_price=500,
            max_price=700,
            avg_price=598.0,
            median_price=600,
            total_trades=20,
            success_rate=0.85,
            last_updated=base_time - timedelta(hours=45)
        )
        self._statistics[ItemSpecId(10)] = advanced_potion_stats

    def _create_sample_statistics(self, item_spec_id: int, min_price: Optional[int],
                                 max_price: Optional[int], avg_price: Optional[float],
                                 median_price: Optional[int], total_trades: int,
                                 success_rate: float, last_updated: datetime) -> ItemTradeStatisticsReadModel:
        """サンプル統計情報を作成するヘルパーメソッド"""
        return ItemTradeStatisticsReadModel.create_from_statistics(
            item_spec_id=ItemSpecId(item_spec_id),
            min_price=min_price,
            max_price=max_price,
            avg_price=avg_price,
            median_price=median_price,
            total_trades=total_trades,
            success_rate=success_rate,
            last_updated=last_updated
        )

    # Repository基本メソッドの実装
    def find_by_id(self, entity_id: ItemSpecId) -> Optional[ItemTradeStatisticsReadModel]:
        """IDで統計情報を検索"""
        return self._statistics.get(entity_id)

    def find_by_ids(self, entity_ids: List[ItemSpecId]) -> List[ItemTradeStatisticsReadModel]:
        """IDのリストで統計情報を検索"""
        result = []
        for stats_id in entity_ids:
            stats = self._statistics.get(stats_id)
            if stats:
                result.append(stats)
        return result

    def save(self, entity: ItemTradeStatisticsReadModel) -> ItemTradeStatisticsReadModel:
        """統計情報を保存"""
        self._statistics[entity.item_spec_id] = entity
        return entity

    def delete(self, entity_id: ItemSpecId) -> bool:
        """統計情報を削除"""
        if entity_id in self._statistics:
            del self._statistics[entity_id]
            return True
        return False

    def find_all(self) -> List[ItemTradeStatisticsReadModel]:
        """全ての統計情報を取得"""
        return list(self._statistics.values())

    # ItemTradeStatisticsReadModelRepository特有メソッドの実装
    def find_statistics(self, item_spec_id: ItemSpecId) -> Optional[ItemTradeStatisticsReadModel]:
        """アイテムスペックIDで統計情報を取得

        Args:
            item_spec_id: アイテムスペックID

        Returns:
            統計情報（存在しない場合はNone）
        """
        return self._statistics.get(item_spec_id)

    # テスト用のヘルパーメソッド
    def clear(self) -> None:
        """全ての統計情報を削除（テスト用）"""
        self._statistics.clear()

    def get_statistics_count(self) -> int:
        """統計情報の総数を取得"""
        return len(self._statistics)
