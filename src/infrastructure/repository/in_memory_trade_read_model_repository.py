"""
InMemoryTradeReadModelRepository - TradeReadModelを使用するインメモリ実装
"""
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timedelta
import random
from src.domain.trade.repository.trade_read_model_repository import TradeReadModelRepository, TradeCursor
from src.domain.trade.read_model.trade_read_model import TradeReadModel
from src.domain.trade.value_object.trade_id import TradeId
from src.domain.trade.value_object.trade_search_filter import TradeSearchFilter
from src.domain.player.value_object.player_id import PlayerId
from src.domain.item.value_object.item_instance_id import ItemInstanceId
from src.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType
from src.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
from src.domain.trade.enum.trade_enum import TradeStatus


class InMemoryTradeReadModelRepository(TradeReadModelRepository):
    """TradeReadModelを使用するインメモリリポジトリ"""

    def __init__(self):
        self._trades: Dict[TradeId, TradeReadModel] = {}

        # サンプル取引データを作成
        self._setup_sample_data()

    def _setup_sample_data(self):
        """サンプル取引データのセットアップ"""
        # 現在の時間を基準に過去の取引を作成
        base_time = datetime.now()

        # 様々なアイテムタイプとレアリティの組み合わせで取引を作成

        # 1. 剣の取引（アクティブ）
        sword_trade = self._create_sample_trade(
            trade_id=1,
            seller_id=1,
            seller_name="勇者アルス",
            buyer_id=None,
            buyer_name=None,
            item_instance_id=1,
            item_name="鋼の剣",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.COMMON,
            item_description="基本的な剣。冒険者の必需品。",
            item_equipment_type=EquipmentType.WEAPON,
            durability_current=85,
            durability_max=100,
            requested_gold=500,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(hours=2)
        )
        self._trades[TradeId(1)] = sword_trade

        # 2. 魔法の杖の取引（アクティブ）
        staff_trade = self._create_sample_trade(
            trade_id=2,
            seller_id=2,
            seller_name="賢者メリア",
            buyer_id=None,
            buyer_name=None,
            item_instance_id=2,
            item_name="魔法の杖",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.UNCOMMON,
            item_description="魔法力を増幅する杖。魔法使いにおすすめ。",
            item_equipment_type=EquipmentType.WEAPON,
            durability_current=92,
            durability_max=100,
            requested_gold=1200,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(hours=1, minutes=30)
        )
        self._trades[TradeId(2)] = staff_trade

        # 3. 回復薬の取引（アクティブ）
        potion_trade = self._create_sample_trade(
            trade_id=3,
            seller_id=3,
            seller_name="薬草師リナ",
            buyer_id=None,
            buyer_name=None,
            item_instance_id=3,
            item_name="回復薬",
            item_quantity=5,
            item_type=ItemType.CONSUMABLE,
            item_rarity=Rarity.COMMON,
            item_description="HPを50回復する薬。戦闘中に役立つ。",
            item_equipment_type=None,
            durability_current=None,
            durability_max=None,
            requested_gold=150,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(hours=1)
        )
        self._trades[TradeId(3)] = potion_trade

        # 4. レア装備の取引（アクティブ、高額）
        rare_armor_trade = self._create_sample_trade(
            trade_id=4,
            seller_id=4,
            seller_name="トレジャーハンター",
            buyer_id=None,
            buyer_name=None,
            item_instance_id=4,
            item_name="ドラゴンスケールアーマー",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.RARE,
            item_description="ドラゴンの鱗で作られた強力な鎧。防御力が高い。",
            item_equipment_type=EquipmentType.ARMOR,
            durability_current=95,
            durability_max=100,
            requested_gold=5000,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(minutes=45)
        )
        self._trades[TradeId(4)] = rare_armor_trade

        # 5. 盾の取引（アクティブ）
        shield_trade = self._create_sample_trade(
            trade_id=5,
            seller_id=5,
            seller_name="ガーディアン",
            buyer_id=None,
            buyer_name=None,
            item_instance_id=5,
            item_name="鉄の盾",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.COMMON,
            item_description="基本的な盾。防御に役立つ。",
            item_equipment_type=EquipmentType.SHIELD,
            durability_current=78,
            durability_max=100,
            requested_gold=300,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(minutes=30)
        )
        self._trades[TradeId(5)] = shield_trade

        # 6. 勇者への取引（成立済み）
        completed_trade = self._create_sample_trade(
            trade_id=6,
            seller_id=1,
            seller_name="勇者アルス",
            buyer_id=6,
            buyer_name="冒険者新人",
            item_instance_id=6,
            item_name="冒険者のブーツ",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.COMMON,
            item_description="丈夫なブーツ。長距離移動に最適。",
            item_equipment_type=EquipmentType.BOOTS,
            durability_current=88,
            durability_max=100,
            requested_gold=250,
            status=TradeStatus.COMPLETED,
            created_at=base_time - timedelta(hours=3)
        )
        self._trades[TradeId(6)] = completed_trade

        # 7. 賢者への取引（成立済み）
        another_completed_trade = self._create_sample_trade(
            trade_id=7,
            seller_id=2,
            seller_name="賢者メリア",
            buyer_id=7,
            buyer_name="若き魔法使い",
            item_instance_id=7,
            item_name="魔法の書",
            item_quantity=1,
            item_type=ItemType.CONSUMABLE,
            item_rarity=Rarity.UNCOMMON,
            item_description="魔法の知識が記された書物。一度読むと消える。",
            item_equipment_type=None,
            durability_current=None,
            durability_max=None,
            requested_gold=800,
            status=TradeStatus.COMPLETED,
            created_at=base_time - timedelta(hours=2, minutes=30)
        )
        self._trades[TradeId(7)] = another_completed_trade

        # 8. キャンセルされた取引
        cancelled_trade = self._create_sample_trade(
            trade_id=8,
            seller_id=3,
            seller_name="薬草師リナ",
            buyer_id=None,
            buyer_name=None,
            item_instance_id=8,
            item_name="珍しい薬草",
            item_quantity=3,
            item_type=ItemType.MATERIAL,
            item_rarity=Rarity.UNCOMMON,
            item_description="珍しい薬草。薬の材料になる。",
            item_equipment_type=None,
            durability_current=None,
            durability_max=None,
            requested_gold=400,
            status=TradeStatus.CANCELLED,
            created_at=base_time - timedelta(hours=4)
        )
        self._trades[TradeId(8)] = cancelled_trade

        # 9. 別のアクティブ取引（低価格）
        cheap_trade = self._create_sample_trade(
            trade_id=9,
            seller_id=8,
            seller_name="雑貨商人",
            buyer_id=None,
            buyer_name=None,
            item_instance_id=9,
            item_name="丈夫な縄",
            item_quantity=1,
            item_type=ItemType.MATERIAL,
            item_rarity=Rarity.COMMON,
            item_description="冒険に役立つ丈夫な縄。",
            item_equipment_type=None,
            durability_current=None,
            durability_max=None,
            requested_gold=50,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(minutes=15)
        )
        self._trades[TradeId(9)] = cheap_trade

        # 10. 高額レアアイテム
        epic_trade = self._create_sample_trade(
            trade_id=10,
            seller_id=9,
            seller_name="伝説の商人",
            buyer_id=None,
            buyer_name=None,
            item_instance_id=10,
            item_name="伝説の剣",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.EPIC,
            item_description="古代の英雄が使っていたという伝説の剣。",
            item_equipment_type=EquipmentType.WEAPON,
            durability_current=100,
            durability_max=100,
            requested_gold=15000,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(minutes=5)
        )
        self._trades[TradeId(10)] = epic_trade

        # 11-15. 追加の取引データ（様々なパターンをカバー）
        # 勇者が出品している別のアイテム
        hero_trade_2 = self._create_sample_trade(
            trade_id=11,
            seller_id=1,
            seller_name="勇者アルス",
            buyer_id=None,
            buyer_name=None,
            item_instance_id=11,
            item_name="勇者の兜",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.UNCOMMON,
            item_description="勇者が愛用していた兜。",
            item_equipment_type=EquipmentType.HELMET,
            durability_current=90,
            durability_max=100,
            requested_gold=750,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(hours=1, minutes=45)
        )
        self._trades[TradeId(11)] = hero_trade_2

        # 賢者が出品している別のアイテム
        mage_trade_2 = self._create_sample_trade(
            trade_id=12,
            seller_id=2,
            seller_name="賢者メリア",
            buyer_id=None,
            buyer_name=None,
            item_instance_id=12,
            item_name="魔法の指輪",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.RARE,
            item_description="魔法力を高める指輪。",
            item_equipment_type=EquipmentType.ACCESSORY,
            durability_current=100,
            durability_max=100,
            requested_gold=3000,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(hours=1, minutes=15)
        )
        self._trades[TradeId(12)] = mage_trade_2

        # 薬草師の成立済み取引
        herbalist_completed = self._create_sample_trade(
            trade_id=13,
            seller_id=3,
            seller_name="薬草師リナ",
            buyer_id=10,
            buyer_name="治癒師",
            item_instance_id=13,
            item_name="上級回復薬",
            item_quantity=2,
            item_type=ItemType.CONSUMABLE,
            item_rarity=Rarity.UNCOMMON,
            item_description="HPを100回復する上級薬。",
            item_equipment_type=None,
            durability_current=None,
            durability_max=None,
            requested_gold=600,
            status=TradeStatus.COMPLETED,
            created_at=base_time - timedelta(hours=1, minutes=30)
        )
        self._trades[TradeId(13)] = herbalist_completed

        # トレジャーハンターの成立済み取引
        hunter_completed = self._create_sample_trade(
            trade_id=14,
            seller_id=4,
            seller_name="トレジャーハンター",
            buyer_id=11,
            buyer_name="貴族",
            item_instance_id=14,
            item_name="輝く宝石",
            item_quantity=1,
            item_type=ItemType.MATERIAL,
            item_rarity=Rarity.RARE,
            item_description="美しい輝きを放つ宝石。",
            item_equipment_type=None,
            durability_current=None,
            durability_max=None,
            requested_gold=2500,
            status=TradeStatus.COMPLETED,
            created_at=base_time - timedelta(hours=2)
        )
        self._trades[TradeId(14)] = hunter_completed

        # ガーディアンのキャンセルされた取引
        guardian_cancelled = self._create_sample_trade(
            trade_id=15,
            seller_id=5,
            seller_name="ガーディアン",
            buyer_id=None,
            buyer_name=None,
            item_instance_id=15,
            item_name="魔法の盾",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.RARE,
            item_description="魔法を防ぐ特殊な盾。",
            item_equipment_type=EquipmentType.SHIELD,
            durability_current=85,
            durability_max=100,
            requested_gold=1800,
            status=TradeStatus.CANCELLED,
            created_at=base_time - timedelta(hours=3, minutes=30)
        )
        self._trades[TradeId(15)] = guardian_cancelled

    def _create_sample_trade(self, trade_id: int, seller_id: int, seller_name: str,
                           buyer_id: Optional[int], buyer_name: Optional[str],
                           item_instance_id: int, item_name: str, item_quantity: int,
                           item_type: ItemType, item_rarity: Rarity,
                           item_description: str, item_equipment_type: Optional[EquipmentType],
                           durability_current: Optional[int], durability_max: Optional[int],
                           requested_gold: int, status: TradeStatus, created_at: datetime) -> TradeReadModel:
        """サンプル取引を作成するヘルパーメソッド"""
        return TradeReadModel.create_from_trade_and_item(
            trade_id=TradeId(trade_id),
            seller_id=PlayerId(seller_id),
            seller_name=seller_name,
            buyer_id=PlayerId(buyer_id) if buyer_id else None,
            buyer_name=buyer_name,
            item_instance_id=ItemInstanceId(item_instance_id),
            item_name=item_name,
            item_quantity=item_quantity,
            item_type=item_type,
            item_rarity=item_rarity,
            item_description=item_description,
            item_equipment_type=item_equipment_type,
            durability_current=durability_current,
            durability_max=durability_max,
            requested_gold=TradeRequestedGold(requested_gold),
            status=status,
            created_at=created_at
        )

    # Repository基本メソッドの実装
    def find_by_id(self, entity_id: TradeId) -> Optional[TradeReadModel]:
        """IDで取引を検索"""
        return self._trades.get(entity_id)

    def find_by_ids(self, entity_ids: List[TradeId]) -> List[TradeReadModel]:
        """IDのリストで取引を検索"""
        result = []
        for trade_id in entity_ids:
            trade = self._trades.get(trade_id)
            if trade:
                result.append(trade)
        return result

    def save(self, entity: TradeReadModel) -> TradeReadModel:
        """取引を保存"""
        self._trades[TradeId(int(entity.trade_id))] = entity
        return entity

    def delete(self, entity_id: TradeId) -> bool:
        """取引を削除"""
        if entity_id in self._trades:
            del self._trades[entity_id]
            return True
        return False

    def find_all(self) -> List[TradeReadModel]:
        """全ての取引を取得"""
        return list(self._trades.values())

    # TradeReadModelRepository特有メソッドの実装
    def find_recent_trades(self, limit: int = 10, cursor: Optional[TradeCursor] = None) -> Tuple[List[TradeReadModel], Optional[TradeCursor]]:
        """最新の取引を取得（カーソルベースページング）"""
        all_trades = list(self._trades.values())

        # 作成日時の降順でソート
        all_trades.sort(key=lambda t: t.created_at, reverse=True)

        # カーソルが指定されている場合は、それ以降の取引を取得
        if cursor:
            filtered_trades = []
            for trade in all_trades:
                if (trade.created_at < cursor.created_at or
                    (trade.created_at == cursor.created_at and trade.trade_id > cursor.trade_id)):
                    filtered_trades.append(trade)
            all_trades = filtered_trades

        # limitで制限
        result_trades = all_trades[:limit]

        # 次のページのカーソルを作成
        next_cursor = None
        if len(all_trades) > limit and len(result_trades) > 0:
            last_trade = result_trades[-1]
            next_cursor = TradeCursor(
                created_at=last_trade.created_at,
                trade_id=int(last_trade.trade_id)
            )

        return result_trades, next_cursor

    def find_trades_for_player(self, player_id: PlayerId, limit: int = 10, cursor: Optional[TradeCursor] = None) -> Tuple[List[TradeReadModel], Optional[TradeCursor]]:
        """プレイヤー宛の取引を取得（カーソルベースページング）"""
        # プレイヤーが関与している取引（出品者または購入者）を検索
        player_trades = [
            trade for trade in self._trades.values()
            if trade.seller_id == int(player_id) or trade.buyer_id == int(player_id)
        ]

        # 作成日時の降順でソート
        player_trades.sort(key=lambda t: t.created_at, reverse=True)

        # カーソルが指定されている場合は、それ以降の取引を取得
        if cursor:
            filtered_trades = []
            for trade in player_trades:
                if (trade.created_at < cursor.created_at or
                    (trade.created_at == cursor.created_at and trade.trade_id > cursor.trade_id)):
                    filtered_trades.append(trade)
            player_trades = filtered_trades

        # limitで制限
        result_trades = player_trades[:limit]

        # 次のページのカーソルを作成
        next_cursor = None
        if len(player_trades) > limit and len(result_trades) > 0:
            last_trade = result_trades[-1]
            next_cursor = TradeCursor(
                created_at=last_trade.created_at,
                trade_id=int(last_trade.trade_id)
            )

        return result_trades, next_cursor

    def find_active_trades(self, limit: int = 50, cursor: Optional[TradeCursor] = None) -> Tuple[List[TradeReadModel], Optional[TradeCursor]]:
        """アクティブな取引を取得（カーソルベースページング）"""
        active_trades = [trade for trade in self._trades.values() if trade.is_active]

        # 作成日時の降順でソート
        active_trades.sort(key=lambda t: t.created_at, reverse=True)

        # カーソルが指定されている場合は、それ以降の取引を取得
        if cursor:
            filtered_trades = []
            for trade in active_trades:
                if (trade.created_at < cursor.created_at or
                    (trade.created_at == cursor.created_at and trade.trade_id > cursor.trade_id)):
                    filtered_trades.append(trade)
            active_trades = filtered_trades

        # limitで制限
        result_trades = active_trades[:limit]

        # 次のページのカーソルを作成
        next_cursor = None
        if len(active_trades) > limit and len(result_trades) > 0:
            last_trade = result_trades[-1]
            next_cursor = TradeCursor(
                created_at=last_trade.created_at,
                trade_id=int(last_trade.trade_id)
            )

        return result_trades, next_cursor

    def search_trades(self, filter: TradeSearchFilter, limit: int = 20, cursor: Optional[TradeCursor] = None) -> Tuple[List[TradeReadModel], Optional[TradeCursor]]:
        """フィルタ条件で取引を検索（カーソルベースページング）"""
        all_trades = list(self._trades.values())

        # フィルタ条件を適用
        filtered_trades = []
        for trade in all_trades:
            if self._matches_filter(trade, filter):
                filtered_trades.append(trade)

        # 作成日時の降順でソート
        filtered_trades.sort(key=lambda t: t.created_at, reverse=True)

        # カーソルが指定されている場合は、それ以降の取引を取得
        if cursor:
            cursor_filtered_trades = []
            for trade in filtered_trades:
                if (trade.created_at < cursor.created_at or
                    (trade.created_at == cursor.created_at and trade.trade_id > cursor.trade_id)):
                    cursor_filtered_trades.append(trade)
            filtered_trades = cursor_filtered_trades

        # limitで制限
        result_trades = filtered_trades[:limit]

        # 次のページのカーソルを作成
        next_cursor = None
        if len(filtered_trades) > limit and len(result_trades) > 0:
            last_trade = result_trades[-1]
            next_cursor = TradeCursor(
                created_at=last_trade.created_at,
                trade_id=int(last_trade.trade_id)
            )

        return result_trades, next_cursor

    def _matches_filter(self, trade: TradeReadModel, filter: TradeSearchFilter) -> bool:
        """取引がフィルタ条件に一致するかチェック"""
        # アイテム名検索
        if filter.item_name:
            if filter.item_name.lower() not in trade.item_name.lower():
                return False

        # アイテムタイプフィルタ
        if filter.item_types:
            if trade.item_type not in [t.value for t in filter.item_types]:
                return False

        # レアリティフィルタ
        if filter.rarities:
            if trade.item_rarity not in [r.value for r in filter.rarities]:
                return False

        # 装備タイプフィルタ
        if filter.equipment_types:
            if trade.item_equipment_type is None or trade.item_equipment_type not in [et.value for et in filter.equipment_types]:
                return False

        # 価格範囲フィルタ
        if filter.min_price is not None and trade.requested_gold < filter.min_price:
            return False
        if filter.max_price is not None and trade.requested_gold > filter.max_price:
            return False

        # ステータスフィルタ
        if filter.statuses:
            if trade.status not in [s.name for s in filter.statuses]:
                return False

        return True

    # テスト用のヘルパーメソッド
    def clear(self) -> None:
        """全ての取引を削除（テスト用）"""
        self._trades.clear()

    def get_trade_count(self) -> int:
        """取引の総数を取得"""
        return len(self._trades)

    def get_active_trade_count(self) -> int:
        """アクティブな取引の数を取得"""
        return len([trade for trade in self._trades.values() if trade.is_active])

    def get_completed_trade_count(self) -> int:
        """成立済み取引の数を取得"""
        return len([trade for trade in self._trades.values() if trade.is_completed])
