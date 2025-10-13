"""
InMemoryTradeMarketReadModelRepository - TradeMarketReadModelを使用するインメモリ実装
"""
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import random

from src.domain.trade.repository.trade_market_read_model_repository import TradeMarketReadModelRepository
from src.domain.trade.read_model.trade_market_read_model import TradeMarketReadModel
from src.domain.item.value_object.item_spec_id import ItemSpecId


class InMemoryTradeMarketReadModelRepository(TradeMarketReadModelRepository):
    """TradeMarketReadModelを使用するインメモリリポジトリ"""

    def __init__(self):
        self._market_data: Dict[ItemSpecId, TradeMarketReadModel] = {}

        # サンプル市場データをセットアップ
        self._setup_sample_market_data()

    def _setup_sample_market_data(self):
        """サンプル市場データのセットアップ"""
        base_time = datetime.now()

        # 人気武器アイテム - 高い取引量と成功率
        self._create_sample_market_data(
            ItemSpecId(1),
            "伝説の剣",
            "weapon",
            "legendary",
            current_market_price=50000,
            min_price=45000,
            max_price=55000,
            avg_price=48500.0,
            median_price=48000,
            total_trades=150,
            active_listings=12,
            completed_trades=145,
            success_rate=0.967,
            last_updated=base_time - timedelta(minutes=30)
        )

        # 一般的な武器 - 中程度の取引量
        self._create_sample_market_data(
            ItemSpecId(2),
            "鉄の剣",
            "weapon",
            "common",
            current_market_price=1500,
            min_price=1200,
            max_price=1800,
            avg_price=1450.0,
            median_price=1400,
            total_trades=80,
            active_listings=8,
            completed_trades=75,
            success_rate=0.938,
            last_updated=base_time - timedelta(hours=1)
        )

        # 希少な鎧 - 高い価格、低い取引量
        self._create_sample_market_data(
            ItemSpecId(3),
            "ドラゴンスケールアーマー",
            "armor",
            "epic",
            current_market_price=75000,
            min_price=70000,
            max_price=80000,
            avg_price=74500.0,
            median_price=75000,
            total_trades=25,
            active_listings=3,
            completed_trades=24,
            success_rate=0.960,
            last_updated=base_time - timedelta(hours=2)
        )

        # 安価な消耗品 - 高い取引量、低い価格
        self._create_sample_market_data(
            ItemSpecId(4),
            "ヒーリングポーション",
            "consumable",
            "common",
            current_market_price=100,
            min_price=80,
            max_price=120,
            avg_price=98.0,
            median_price=100,
            total_trades=200,
            active_listings=25,
            completed_trades=190,
            success_rate=0.950,
            last_updated=base_time - timedelta(minutes=15)
        )

        # レア素材 - 中程度の価格と取引量
        self._create_sample_market_data(
            ItemSpecId(5),
            "ミスリルのインゴット",
            "material",
            "rare",
            current_market_price=8000,
            min_price=7500,
            max_price=8500,
            avg_price=7920.0,
            median_price=7900,
            total_trades=60,
            active_listings=7,
            completed_trades=58,
            success_rate=0.967,
            last_updated=base_time - timedelta(hours=3)
        )

        # 人気アクセサリー - 高い取引量
        self._create_sample_market_data(
            ItemSpecId(6),
            "幸運の指輪",
            "accessory",
            "rare",
            current_market_price=12000,
            min_price=10000,
            max_price=15000,
            avg_price=11800.0,
            median_price=12000,
            total_trades=95,
            active_listings=10,
            completed_trades=90,
            success_rate=0.947,
            last_updated=base_time - timedelta(hours=4)
        )

        # 取引が少ないアイテム - 低い成功率
        self._create_sample_market_data(
            ItemSpecId(7),
            "呪いのアミュレット",
            "accessory",
            "rare",
            current_market_price=3000,
            min_price=2500,
            max_price=3500,
            avg_price=2950.0,
            median_price=3000,
            total_trades=12,
            active_listings=2,
            completed_trades=8,
            success_rate=0.667,
            last_updated=base_time - timedelta(days=1)
        )

        # 新しいアイテム - 最近の取引のみ
        self._create_sample_market_data(
            ItemSpecId(8),
            "魔法のクリスタル",
            "material",
            "epic",
            current_market_price=25000,
            min_price=24000,
            max_price=26000,
            avg_price=24900.0,
            median_price=25000,
            total_trades=8,
            active_listings=5,
            completed_trades=8,
            success_rate=1.000,
            last_updated=base_time - timedelta(minutes=5)
        )

        # 高価だが取引が少ないアイテム
        self._create_sample_market_data(
            ItemSpecId(9),
            "神聖な聖杯",
            "accessory",
            "legendary",
            current_market_price=100000,
            min_price=95000,
            max_price=105000,
            avg_price=99500.0,
            median_price=100000,
            total_trades=5,
            active_listings=1,
            completed_trades=5,
            success_rate=1.000,
            last_updated=base_time - timedelta(days=2)
        )

        # 一般的な防具
        self._create_sample_market_data(
            ItemSpecId(10),
            "革の鎧",
            "armor",
            "common",
            current_market_price=800,
            min_price=700,
            max_price=900,
            avg_price=785.0,
            median_price=800,
            total_trades=45,
            active_listings=6,
            completed_trades=42,
            success_rate=0.933,
            last_updated=base_time - timedelta(hours=5)
        )

        # 人気の消耗品 - 魔法関連
        self._create_sample_market_data(
            ItemSpecId(11),
            "マナポーション",
            "consumable",
            "common",
            current_market_price=150,
            min_price=120,
            max_price=180,
            avg_price=148.0,
            median_price=150,
            total_trades=180,
            active_listings=20,
            completed_trades=175,
            success_rate=0.972,
            last_updated=base_time - timedelta(minutes=45)
        )

        # レア武器
        self._create_sample_market_data(
            ItemSpecId(12),
            "エルフの弓",
            "weapon",
            "rare",
            current_market_price=25000,
            min_price=22000,
            max_price=28000,
            avg_price=24800.0,
            median_price=25000,
            total_trades=35,
            active_listings=4,
            completed_trades=33,
            success_rate=0.943,
            last_updated=base_time - timedelta(hours=6)
        )

        # 非常に安価なアイテム
        self._create_sample_market_data(
            ItemSpecId(13),
            "石ころ",
            "material",
            "common",
            current_market_price=1,
            min_price=1,
            max_price=5,
            avg_price=1.2,
            median_price=1,
            total_trades=500,
            active_listings=50,
            completed_trades=480,
            success_rate=0.960,
            last_updated=base_time - timedelta(hours=12)
        )

        # エピック武器 - 高価格
        self._create_sample_market_data(
            ItemSpecId(14),
            "雷神の槌",
            "weapon",
            "epic",
            current_market_price=85000,
            min_price=80000,
            max_price=90000,
            avg_price=84500.0,
            median_price=85000,
            total_trades=20,
            active_listings=2,
            completed_trades=19,
            success_rate=0.950,
            last_updated=base_time - timedelta(hours=8)
        )

        # 取引が全くない新しいアイテム
        self._create_sample_market_data(
            ItemSpecId(15),
            "未知の鉱石",
            "material",
            "rare",
            current_market_price=5000,
            min_price=5000,
            max_price=5000,
            avg_price=5000.0,
            median_price=5000,
            total_trades=0,
            active_listings=1,
            completed_trades=0,
            success_rate=0.0,
            last_updated=base_time - timedelta(days=7)
        )

    def _create_sample_market_data(
        self,
        item_spec_id: ItemSpecId,
        item_name: str,
        item_type: str,
        item_rarity: str,
        current_market_price: int,
        min_price: int,
        max_price: int,
        avg_price: float,
        median_price: int,
        total_trades: int,
        active_listings: int,
        completed_trades: int,
        success_rate: float,
        last_updated: datetime
    ):
        """サンプル市場データを作成して保存"""
        market_data = TradeMarketReadModel.create_from_item_spec_and_stats(
            item_spec_id=item_spec_id,
            item_name=item_name,
            item_type=item_type,
            item_rarity=item_rarity,
            current_market_price=current_market_price,
            min_price=min_price,
            max_price=max_price,
            avg_price=avg_price,
            median_price=median_price,
            total_trades=total_trades,
            active_listings=active_listings,
            completed_trades=completed_trades,
            success_rate=success_rate,
            last_updated=last_updated
        )
        self._market_data[item_spec_id] = market_data

    # Repository基幹クラスのメソッド実装

    def find_by_id(self, entity_id: ItemSpecId) -> Optional[TradeMarketReadModel]:
        """ItemSpecIdで市場情報を検索"""
        return self._market_data.get(entity_id)

    def find_by_ids(self, entity_ids: List[ItemSpecId]) -> List[TradeMarketReadModel]:
        """複数のItemSpecIdで市場情報を検索"""
        result = []
        for entity_id in entity_ids:
            market_data = self._market_data.get(entity_id)
            if market_data:
                result.append(market_data)
        return result

    def save(self, entity: TradeMarketReadModel) -> TradeMarketReadModel:
        """市場情報を保存"""
        self._market_data[entity.item_spec_id] = entity
        return entity

    def delete(self, entity_id: ItemSpecId) -> bool:
        """市場情報を削除"""
        if entity_id in self._market_data:
            del self._market_data[entity_id]
            return True
        return False

    def find_all(self) -> List[TradeMarketReadModel]:
        """全ての市場情報を取得"""
        return list(self._market_data.values())

    # TradeMarketReadModelRepository特有のメソッド実装

    def find_by_item_name(self, item_name: str) -> Optional[TradeMarketReadModel]:
        """アイテム名で市場情報を検索

        Args:
            item_name: アイテム名

        Returns:
            アイテムの市場情報（存在しない場合はNone）
        """
        for market_data in self._market_data.values():
            if market_data.item_name == item_name:
                return market_data
        return None

    def find_popular_items(self, limit: int = 10) -> List[TradeMarketReadModel]:
        """人気アイテムの市場情報を取得（取引量順）

        Args:
            limit: 取得する最大件数

        Returns:
            人気アイテムの市場情報リスト（取引量の降順）
        """
        # 総取引数で降順ソート
        sorted_items = sorted(
            self._market_data.values(),
            key=lambda x: x.total_trades,
            reverse=True
        )
        return sorted_items[:limit]

    # テスト・デモ用ヘルパーメソッド

    def clear(self) -> None:
        """全ての市場データを削除（テスト用）"""
        self._market_data.clear()

    def get_total_items(self) -> int:
        """登録されているアイテムの総数を取得"""
        return len(self._market_data)

    def find_items_by_type(self, item_type: str) -> List[TradeMarketReadModel]:
        """アイテムタイプでフィルタリング"""
        return [item for item in self._market_data.values() if item.item_type == item_type]

    def find_items_by_rarity(self, rarity: str) -> List[TradeMarketReadModel]:
        """レアリティでフィルタリング"""
        return [item for item in self._market_data.values() if item.item_rarity == rarity]

    def find_high_value_items(self, min_price: int) -> List[TradeMarketReadModel]:
        """指定価格以上のアイテムを取得"""
        return [item for item in self._market_data.values() if item.current_market_price >= min_price]

    def find_items_with_active_trades(self) -> List[TradeMarketReadModel]:
        """アクティブな取引があるアイテムを取得"""
        return [item for item in self._market_data.values() if item.has_active_trades]

    def find_recently_updated_items(self, hours: int = 24) -> List[TradeMarketReadModel]:
        """指定時間内に更新されたアイテムを取得"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [item for item in self._market_data.values() if item.last_updated >= cutoff_time]

    def update_sample_data_with_random_changes(self) -> None:
        """サンプルデータをランダムに更新（テスト用）"""
        for item in self._market_data.values():
            # 価格を少し変動させる
            price_change = random.randint(-100, 100)
            new_price = max(1, item.current_market_price + price_change)
            item.current_market_price = new_price

            # 取引数を少し増やす
            if random.random() < 0.3:  # 30%の確率で取引増加
                item.total_trades += 1
                item.completed_trades += 1
                # 成功率を再計算
                if item.total_trades > 0:
                    item.success_rate = item.completed_trades / item.total_trades

            # 更新時間を現在に
            item.last_updated = datetime.now()
