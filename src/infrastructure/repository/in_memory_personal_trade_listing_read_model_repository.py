"""
InMemoryPersonalTradeListingReadModelRepository - PersonalTradeListingReadModelを使用するインメモリ実装
"""
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timedelta
import random
from src.domain.trade.repository.personal_trade_listing_read_model_repository import PersonalTradeListingReadModelRepository
from src.domain.trade.read_model.personal_trade_listing_read_model import PersonalTradeListingReadModel
from src.domain.trade.value_object.trade_id import TradeId
from src.domain.trade.repository.cursor import ListingCursor
from src.domain.player.value_object.player_id import PlayerId
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.value_object.item_instance_id import ItemInstanceId
from src.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType


class InMemoryPersonalTradeListingReadModelRepository(PersonalTradeListingReadModelRepository):
    """PersonalTradeListingReadModelを使用するインメモリリポジトリ"""

    def __init__(self):
        self._listings: Dict[TradeId, PersonalTradeListingReadModel] = {}

        # サンプル取引データを作成
        self._setup_sample_data()

    def _setup_sample_data(self):
        """サンプル取引データのセットアップ"""
        # 現在の時間を基準に過去の取引を作成
        base_time = datetime.now()

        # プレイヤー1宛の取引データ
        player_1_id = PlayerId(1)

        # 1. プレイヤー1宛の剣の取引
        sword_listing = self._create_sample_listing(
            trade_id=1,
            item_spec_id=1,
            item_instance_id=1,
            recipient_player_id=player_1_id,
            item_name="鋼の剣",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.COMMON,
            item_equipment_type=EquipmentType.WEAPON,
            created_at=base_time - timedelta(hours=2),
            durability_current=85,
            durability_max=100,
            requested_gold=500,
            seller_name="勇者"
        )
        self._listings[TradeId(1)] = sword_listing

        # 2. プレイヤー1宛の魔法の杖の取引
        staff_listing = self._create_sample_listing(
            trade_id=2,
            item_spec_id=2,
            item_instance_id=2,
            recipient_player_id=player_1_id,
            item_name="魔法の杖",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.UNCOMMON,
            item_equipment_type=EquipmentType.WEAPON,
            created_at=base_time - timedelta(hours=1, minutes=30),
            durability_current=92,
            durability_max=100,
            requested_gold=1200,
            seller_name="賢者"
        )
        self._listings[TradeId(2)] = staff_listing

        # 3. プレイヤー1宛の回復薬の取引
        potion_listing = self._create_sample_listing(
            trade_id=3,
            item_spec_id=3,
            item_instance_id=3,
            recipient_player_id=player_1_id,
            item_name="回復薬",
            item_quantity=5,
            item_type=ItemType.CONSUMABLE,
            item_rarity=Rarity.COMMON,
            item_equipment_type=None,
            created_at=base_time - timedelta(hours=1),
            durability_current=None,
            durability_max=None,
            requested_gold=150,
            seller_name="薬草師"
        )
        self._listings[TradeId(3)] = potion_listing

        # プレイヤー2宛の取引データ
        player_2_id = PlayerId(2)

        # 4. プレイヤー2宛のレア装備の取引
        rare_armor_listing = self._create_sample_listing(
            trade_id=4,
            item_spec_id=4,
            item_instance_id=4,
            recipient_player_id=player_2_id,
            item_name="ドラゴンスケールアーマー",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.RARE,
            item_equipment_type=EquipmentType.ARMOR,
            created_at=base_time - timedelta(minutes=45),
            durability_current=95,
            durability_max=100,
            requested_gold=5000,
            seller_name="トレジャーハンター"
        )
        self._listings[TradeId(4)] = rare_armor_listing

        # 5. プレイヤー2宛の盾の取引
        shield_listing = self._create_sample_listing(
            trade_id=5,
            item_spec_id=5,
            item_instance_id=5,
            recipient_player_id=player_2_id,
            item_name="鉄の盾",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.COMMON,
            item_equipment_type=EquipmentType.SHIELD,
            created_at=base_time - timedelta(minutes=30),
            durability_current=78,
            durability_max=100,
            requested_gold=300,
            seller_name="ガーディアン"
        )
        self._listings[TradeId(5)] = shield_listing

        # プレイヤー1宛の追加取引
        # 6. プレイヤー1宛の低価格アイテム
        cheap_listing = self._create_sample_listing(
            trade_id=6,
            item_spec_id=6,
            item_instance_id=6,
            recipient_player_id=player_1_id,
            item_name="丈夫な縄",
            item_quantity=1,
            item_type=ItemType.MATERIAL,
            item_rarity=Rarity.COMMON,
            item_equipment_type=None,
            created_at=base_time - timedelta(minutes=15),
            durability_current=None,
            durability_max=None,
            requested_gold=50,
            seller_name="トレジャーハンター"
        )
        self._listings[TradeId(6)] = cheap_listing

        # 7. プレイヤー1宛の高額レアアイテム
        epic_listing = self._create_sample_listing(
            trade_id=7,
            item_spec_id=7,
            item_instance_id=7,
            recipient_player_id=player_1_id,
            item_name="伝説の剣",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.EPIC,
            item_equipment_type=EquipmentType.WEAPON,
            created_at=base_time - timedelta(minutes=5),
            durability_current=100,
            durability_max=100,
            requested_gold=15000,
            seller_name="伝説の英雄"
        )
        self._listings[TradeId(7)] = epic_listing

    def _create_sample_listing(self, trade_id: int, item_spec_id: int, item_instance_id: int,
                              recipient_player_id: PlayerId, item_name: str, item_quantity: int,
                              item_type: ItemType, item_rarity: Rarity,
                              item_equipment_type: Optional[EquipmentType], created_at: datetime,
                              durability_current: Optional[int], durability_max: Optional[int],
                              requested_gold: int, seller_name: str) -> PersonalTradeListingReadModel:
        """サンプル取引出品を作成するヘルパーメソッド"""
        return PersonalTradeListingReadModel.create_from_trade_data(
            trade_id=TradeId(trade_id),
            item_spec_id=ItemSpecId(item_spec_id),
            item_instance_id=ItemInstanceId(item_instance_id),
            recipient_player_id=recipient_player_id,
            item_name=item_name,
            item_quantity=item_quantity,
            item_type=item_type,
            item_rarity=item_rarity,
            item_equipment_type=item_equipment_type,
            durability_current=durability_current,
            durability_max=durability_max,
            requested_gold=requested_gold,
            seller_name=seller_name,
            created_at=created_at
        )

    # Repository基本メソッドの実装
    def find_by_id(self, entity_id: TradeId) -> Optional[PersonalTradeListingReadModel]:
        """IDで出品を検索"""
        return self._listings.get(entity_id)

    def find_by_ids(self, entity_ids: List[TradeId]) -> List[PersonalTradeListingReadModel]:
        """IDのリストで出品を検索"""
        result = []
        for listing_id in entity_ids:
            listing = self._listings.get(listing_id)
            if listing:
                result.append(listing)
        return result

    def save(self, entity: PersonalTradeListingReadModel) -> PersonalTradeListingReadModel:
        """出品を保存"""
        self._listings[entity.trade_id] = entity
        return entity

    def delete(self, entity_id: TradeId) -> bool:
        """出品を削除"""
        if entity_id in self._listings:
            del self._listings[entity_id]
            return True
        return False

    def find_all(self) -> List[PersonalTradeListingReadModel]:
        """全ての出品を取得"""
        return list(self._listings.values())

    # PersonalTradeListingReadModelRepository特有メソッドの実装
    def find_for_player(
        self,
        player_id: PlayerId,
        limit: int = 20,
        cursor: Optional[ListingCursor] = None
    ) -> Tuple[List[PersonalTradeListingReadModel], Optional[ListingCursor]]:
        """プレイヤー宛の取引を取得（カーソルベースページング）

        Args:
            player_id: プレイヤーID
            limit: 取得する最大件数
            cursor: ページングカーソル（Noneの場合は最初のページ）

        Returns:
            (取引リスト, 次のページのカーソル)
        """
        # 指定されたプレイヤー宛の取引のみをフィルタリング
        all_listings = list(self._listings.values())
        player_listings = [listing for listing in all_listings if listing.recipient_player_id == player_id]

        # 作成日時の降順でソート（created_atを基準にtrade_idで安定ソート）
        player_listings.sort(key=lambda l: (l.created_at, int(l.trade_id)), reverse=True)

        # カーソルが指定されている場合は、それ以降の出品を取得
        if cursor:
            cursor_filtered_listings = []
            for listing in player_listings:
                if (listing.created_at < cursor.created_at or
                    (listing.created_at == cursor.created_at and int(listing.trade_id) < cursor.listing_id)):
                    cursor_filtered_listings.append(listing)
            player_listings = cursor_filtered_listings

        # limitで制限
        result_listings = player_listings[:limit]

        # 次のページのカーソルを作成
        next_cursor = None
        if len(player_listings) > limit and len(result_listings) > 0:
            last_listing = result_listings[-1]
            next_cursor = ListingCursor(
                created_at=last_listing.created_at,
                listing_id=int(last_listing.trade_id)
            )

        return result_listings, next_cursor

    def count_for_player(self, player_id: PlayerId) -> int:
        """プレイヤー宛の取引数をカウント

        Args:
            player_id: プレイヤーID

        Returns:
            取引数
        """
        all_listings = list(self._listings.values())
        player_listings = [listing for listing in all_listings if listing.recipient_player_id == player_id]
        return len(player_listings)

    # テスト用のヘルパーメソッド
    def clear(self) -> None:
        """全ての出品を削除（テスト用）"""
        self._listings.clear()

    def get_listing_count(self) -> int:
        """出品の総数を取得"""
        return len(self._listings)
