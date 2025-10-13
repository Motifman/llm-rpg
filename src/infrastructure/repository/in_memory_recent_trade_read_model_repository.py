"""
InMemoryRecentTradeReadModelRepository - RecentTradeReadModelを使用するインメモリ実装
"""
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import random
from src.domain.trade.repository.recent_trade_read_model_repository import RecentTradeReadModelRepository
from src.domain.trade.read_model.recent_trade_read_model import RecentTradeReadModel, RecentTradeData
from src.domain.item.value_object.item_spec_id import ItemSpecId


class InMemoryRecentTradeReadModelRepository(RecentTradeReadModelRepository):
    """RecentTradeReadModelを使用するインメモリリポジトリ"""

    def __init__(self):
        self._read_models: Dict[ItemSpecId, RecentTradeReadModel] = {}

        # サンプルデータを設定
        self._setup_sample_data()

    def _setup_sample_data(self):
        """サンプルデータのセットアップ"""
        # 現在の時間を基準に過去の取引を作成
        base_time = datetime.now()

        # 1. 鋼の剣 - 人気アイテム、複数の取引履歴
        sword_trades = self._create_sample_recent_trades(
            item_spec_id=1,
            item_name="鋼の剣",
            base_price=500,
            trade_count=15,
            base_time=base_time
        )
        self._read_models[ItemSpecId(1)] = sword_trades

        # 2. 魔法の杖 - 高価なアイテム
        staff_trades = self._create_sample_recent_trades(
            item_spec_id=2,
            item_name="魔法の杖",
            base_price=1200,
            trade_count=8,
            base_time=base_time
        )
        self._read_models[ItemSpecId(2)] = staff_trades

        # 3. 回復薬 - 安価で大量取引
        potion_trades = self._create_sample_recent_trades(
            item_spec_id=3,
            item_name="回復薬",
            base_price=150,
            trade_count=25,
            base_time=base_time
        )
        self._read_models[ItemSpecId(3)] = potion_trades

        # 4. ドラゴンスケールアーマー - 高額レアアイテム
        armor_trades = self._create_sample_recent_trades(
            item_spec_id=4,
            item_name="ドラゴンスケールアーマー",
            base_price=5000,
            trade_count=3,
            base_time=base_time
        )
        self._read_models[ItemSpecId(4)] = armor_trades

        # 5. 鉄の盾 - 標準的なアイテム
        shield_trades = self._create_sample_recent_trades(
            item_spec_id=5,
            item_name="鉄の盾",
            base_price=300,
            trade_count=12,
            base_time=base_time
        )
        self._read_models[ItemSpecId(5)] = shield_trades

        # 6. 冒険者のブーツ - 新しいアイテム（少ない取引履歴）
        boots_trades = self._create_sample_recent_trades(
            item_spec_id=6,
            item_name="冒険者のブーツ",
            base_price=250,
            trade_count=5,
            base_time=base_time
        )
        self._read_models[ItemSpecId(6)] = boots_trades

        # 7. 魔法の書 - 特殊アイテム
        book_trades = self._create_sample_recent_trades(
            item_spec_id=7,
            item_name="魔法の書",
            base_price=800,
            trade_count=7,
            base_time=base_time
        )
        self._read_models[ItemSpecId(7)] = book_trades

        # 8. 珍しい薬草 - マテリアルアイテム
        herb_trades = self._create_sample_recent_trades(
            item_spec_id=8,
            item_name="珍しい薬草",
            base_price=400,
            trade_count=10,
            base_time=base_time
        )
        self._read_models[ItemSpecId(8)] = herb_trades

        # 9. 丈夫な縄 - 安価アイテム
        rope_trades = self._create_sample_recent_trades(
            item_spec_id=9,
            item_name="丈夫な縄",
            base_price=50,
            trade_count=20,
            base_time=base_time
        )
        self._read_models[ItemSpecId(9)] = rope_trades

        # 10. 伝説の剣 - 超高額アイテム（取引履歴なし）
        # 取引履歴がないアイテムもテスト用に作成
        legendary_sword = RecentTradeReadModel.create_from_item_and_trades(
            item_spec_id=ItemSpecId(10),
            item_name="伝説の剣",
            recent_trades=[],
            last_updated=base_time
        )
        self._read_models[ItemSpecId(10)] = legendary_sword

        # 11. 上級回復薬 - 中価格帯アイテム
        advanced_potion_trades = self._create_sample_recent_trades(
            item_spec_id=11,
            item_name="上級回復薬",
            base_price=600,
            trade_count=6,
            base_time=base_time
        )
        self._read_models[ItemSpecId(11)] = advanced_potion_trades

        # 12. 輝く宝石 - 高価マテリアル
        gem_trades = self._create_sample_recent_trades(
            item_spec_id=12,
            item_name="輝く宝石",
            base_price=2500,
            trade_count=4,
            base_time=base_time
        )
        self._read_models[ItemSpecId(12)] = gem_trades

        # 13. 魔法の盾 - レア装備
        magic_shield_trades = self._create_sample_recent_trades(
            item_spec_id=13,
            item_name="魔法の盾",
            base_price=1800,
            trade_count=2,
            base_time=base_time
        )
        self._read_models[ItemSpecId(13)] = magic_shield_trades

        # 14. 勇者の兜 - ユニークアイテム
        hero_helmet_trades = self._create_sample_recent_trades(
            item_spec_id=14,
            item_name="勇者の兜",
            base_price=750,
            trade_count=9,
            base_time=base_time
        )
        self._read_models[ItemSpecId(14)] = hero_helmet_trades

        # 15. 魔法の指輪 - アクセサリー
        ring_trades = self._create_sample_recent_trades(
            item_spec_id=15,
            item_name="魔法の指輪",
            base_price=3000,
            trade_count=3,
            base_time=base_time
        )
        self._read_models[ItemSpecId(15)] = ring_trades

    def _create_sample_recent_trades(
        self,
        item_spec_id: int,
        item_name: str,
        base_price: int,
        trade_count: int,
        base_time: datetime
    ) -> RecentTradeReadModel:
        """サンプル取引履歴を作成するヘルパーメソッド"""
        recent_trades = []

        # 取引履歴を作成（時系列順: 古い順）
        for i in range(trade_count):
            # 価格の変動をランダムに設定（±20%）
            price_variation = random.uniform(-0.2, 0.2)
            price = int(base_price * (1 + price_variation))
            price = max(1, price)  # 最低価格は1

            # 取引時間をランダムに設定（過去数日以内）
            days_ago = random.uniform(0, 7)  # 0-7日前
            hours_ago = random.uniform(0, 24)  # 追加の時間
            traded_at = base_time - timedelta(days=days_ago, hours=hours_ago)

            # アイテムスペックIDとインデックスを組み合わせたハードコードされた取引IDを使用
            trade_id = item_spec_id * 1000 + i + 1

            trade_data = RecentTradeData(
                trade_id=trade_id,
                price=price,
                traded_at=traded_at
            )
            recent_trades.append(trade_data)

        # 時系列順（新しい順）にソート
        recent_trades.sort(key=lambda x: x.traded_at, reverse=True)

        return RecentTradeReadModel.create_from_item_and_trades(
            item_spec_id=ItemSpecId(item_spec_id),
            item_name=item_name,
            recent_trades=recent_trades,
            last_updated=base_time
        )

    # Repository基本メソッドの実装
    def find_by_id(self, entity_id: ItemSpecId) -> Optional[RecentTradeReadModel]:
        """IDでReadModelを検索"""
        return self._read_models.get(entity_id)

    def find_by_ids(self, entity_ids: List[ItemSpecId]) -> List[RecentTradeReadModel]:
        """IDのリストでReadModelを検索"""
        result = []
        for item_spec_id in entity_ids:
            read_model = self._read_models.get(item_spec_id)
            if read_model:
                result.append(read_model)
        return result

    def save(self, entity: RecentTradeReadModel) -> RecentTradeReadModel:
        """ReadModelを保存"""
        self._read_models[entity.item_spec_id] = entity
        return entity

    def delete(self, entity_id: ItemSpecId) -> bool:
        """ReadModelを削除"""
        if entity_id in self._read_models:
            del self._read_models[entity_id]
            return True
        return False

    def find_all(self) -> List[RecentTradeReadModel]:
        """全てのReadModelを取得"""
        return list(self._read_models.values())


    # RecentTradeReadModelRepository特有メソッドの実装
    def find_by_item_name(self, item_name: str) -> Optional[RecentTradeReadModel]:
        """アイテム名で最近の取引履歴を取得"""
        for read_model in self._read_models.values():
            if read_model.item_name == item_name:
                return read_model
        return None

    # テスト用のヘルパーメソッド
    def clear(self) -> None:
        """全てのReadModelを削除（テスト用）"""
        self._read_models.clear()

    def get_read_model_count(self) -> int:
        """ReadModelの総数を取得"""
        return len(self._read_models)

    def get_items_with_trades(self) -> List[str]:
        """取引履歴があるアイテム名を取得"""
        return [rm.item_name for rm in self._read_models.values() if rm.has_recent_trades]

    def get_items_without_trades(self) -> List[str]:
        """取引履歴がないアイテム名を取得"""
        return [rm.item_name for rm in self._read_models.values() if not rm.has_recent_trades]
