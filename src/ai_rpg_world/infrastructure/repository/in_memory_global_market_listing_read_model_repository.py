"""
InMemoryGlobalMarketListingReadModelRepository - GlobalMarketListingReadModelを使用するインメモリ実装
"""
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timedelta
import random
from ai_rpg_world.domain.trade.repository.global_market_listing_read_model_repository import GlobalMarketListingReadModelRepository
from ai_rpg_world.domain.trade.read_model.global_market_listing_read_model import GlobalMarketListingReadModel
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_search_filter import TradeSearchFilter
from ai_rpg_world.domain.trade.repository.cursor import ListingCursor
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType


class InMemoryGlobalMarketListingReadModelRepository(GlobalMarketListingReadModelRepository):
    """GlobalMarketListingReadModelを使用するインメモリリポジトリ"""

    def __init__(self):
        self._listings: Dict[TradeId, GlobalMarketListingReadModel] = {}

        # サンプル取引データを作成
        self._setup_sample_data()

    def _setup_sample_data(self):
        """サンプル取引データのセットアップ"""
        # 現在の時間を基準に過去の取引を作成
        base_time = datetime.now()

        # 様々なアイテムタイプとレアリティの組み合わせで取引を作成

        # 1. 剣の取引（アクティブ）
        sword_listing = self._create_sample_listing(
            trade_id=1,
            item_spec_id=1,
            item_instance_id=1,
            item_name="鋼の剣",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.COMMON,
            item_equipment_type=EquipmentType.WEAPON,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(hours=2),
            durability_current=85,
            durability_max=100,
            requested_gold=500
        )
        self._listings[TradeId(1)] = sword_listing

        # 2. 魔法の杖の取引（アクティブ）
        staff_listing = self._create_sample_listing(
            trade_id=2,
            item_spec_id=2,
            item_instance_id=2,
            item_name="魔法の杖",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.UNCOMMON,
            item_equipment_type=EquipmentType.WEAPON,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(hours=1, minutes=30),
            durability_current=92,
            durability_max=100,
            requested_gold=1200
        )
        self._listings[TradeId(2)] = staff_listing

        # 3. 回復薬の取引（アクティブ）
        potion_listing = self._create_sample_listing(
            trade_id=3,
            item_spec_id=3,
            item_instance_id=3,
            item_name="回復薬",
            item_quantity=5,
            item_type=ItemType.CONSUMABLE,
            item_rarity=Rarity.COMMON,
            item_equipment_type=None,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(hours=1),
            durability_current=None,
            durability_max=None,
            requested_gold=150
        )
        self._listings[TradeId(3)] = potion_listing

        # 4. レア装備の取引（アクティブ、高額）
        rare_armor_listing = self._create_sample_listing(
            trade_id=4,
            item_spec_id=4,
            item_instance_id=4,
            item_name="ドラゴンスケールアーマー",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.RARE,
            item_equipment_type=EquipmentType.ARMOR,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(minutes=45),
            durability_current=95,
            durability_max=100,
            requested_gold=5000
        )
        self._listings[TradeId(4)] = rare_armor_listing

        # 5. 盾の取引（アクティブ）
        shield_listing = self._create_sample_listing(
            trade_id=5,
            item_spec_id=5,
            item_instance_id=5,
            item_name="鉄の盾",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.COMMON,
            item_equipment_type=EquipmentType.SHIELD,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(minutes=30),
            durability_current=78,
            durability_max=100,
            requested_gold=300
        )
        self._listings[TradeId(5)] = shield_listing

        # 6. 別のアクティブ取引（低価格）
        cheap_listing = self._create_sample_listing(
            trade_id=6,
            item_spec_id=6,
            item_instance_id=6,
            item_name="丈夫な縄",
            item_quantity=1,
            item_type=ItemType.MATERIAL,
            item_rarity=Rarity.COMMON,
            item_equipment_type=None,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(minutes=15),
            durability_current=None,
            durability_max=None,
            requested_gold=50
        )
        self._listings[TradeId(6)] = cheap_listing

        # 7. 高額レアアイテム
        epic_listing = self._create_sample_listing(
            trade_id=7,
            item_spec_id=7,
            item_instance_id=7,
            item_name="伝説の剣",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.EPIC,
            item_equipment_type=EquipmentType.WEAPON,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(minutes=5),
            durability_current=100,
            durability_max=100,
            requested_gold=15000
        )
        self._listings[TradeId(7)] = epic_listing

        # 8-12. 追加の取引データ（様々なパターンをカバー）
        # 勇者が出品している別のアイテム
        hero_listing_2 = self._create_sample_listing(
            trade_id=8,
            item_spec_id=8,
            item_instance_id=8,
            item_name="勇者の兜",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.UNCOMMON,
            item_equipment_type=EquipmentType.HELMET,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(hours=1, minutes=45),
            durability_current=90,
            durability_max=100,
            requested_gold=750
        )
        self._listings[TradeId(8)] = hero_listing_2

        # 賢者が出品している別のアイテム
        mage_listing_2 = self._create_sample_listing(
            trade_id=9,
            item_spec_id=9,
            item_instance_id=9,
            item_name="魔法の指輪",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.RARE,
            item_equipment_type=EquipmentType.ACCESSORY,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(hours=1, minutes=15),
            durability_current=100,
            durability_max=100,
            requested_gold=3000
        )
        self._listings[TradeId(9)] = mage_listing_2

        # 薬草師が出品しているアイテム
        herbalist_listing = self._create_sample_listing(
            trade_id=10,
            item_spec_id=10,
            item_instance_id=10,
            item_name="上級回復薬",
            item_quantity=2,
            item_type=ItemType.CONSUMABLE,
            item_rarity=Rarity.UNCOMMON,
            item_equipment_type=None,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(hours=1, minutes=30),
            durability_current=None,
            durability_max=None,
            requested_gold=600
        )
        self._listings[TradeId(10)] = herbalist_listing

        # トレジャーハンターが出品しているアイテム
        hunter_listing = self._create_sample_listing(
            trade_id=11,
            item_spec_id=11,
            item_instance_id=11,
            item_name="輝く宝石",
            item_quantity=1,
            item_type=ItemType.MATERIAL,
            item_rarity=Rarity.RARE,
            item_equipment_type=None,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(hours=2),
            durability_current=None,
            durability_max=None,
            requested_gold=2500
        )
        self._listings[TradeId(11)] = hunter_listing

        # ガーディアンが出品しているアイテム
        guardian_listing = self._create_sample_listing(
            trade_id=12,
            item_spec_id=12,
            item_instance_id=12,
            item_name="魔法の盾",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.RARE,
            item_equipment_type=EquipmentType.SHIELD,
            status=TradeStatus.ACTIVE,
            created_at=base_time - timedelta(hours=3, minutes=30),
            durability_current=85,
            durability_max=100,
            requested_gold=1800
        )
        self._listings[TradeId(12)] = guardian_listing

    def _create_sample_listing(self, trade_id: int, item_spec_id: int, item_instance_id: int,
                              item_name: str, item_quantity: int, item_type: ItemType,
                              item_rarity: Rarity, item_equipment_type: Optional[EquipmentType],
                              status: TradeStatus, created_at: datetime,
                              durability_current: Optional[int], durability_max: Optional[int],
                              requested_gold: int) -> GlobalMarketListingReadModel:
        """サンプル取引出品を作成するヘルパーメソッド"""
        return GlobalMarketListingReadModel.create_from_trade_data(
            trade_id=TradeId(trade_id),
            item_spec_id=ItemSpecId(item_spec_id),
            item_instance_id=ItemInstanceId(item_instance_id),
            item_name=item_name,
            item_quantity=item_quantity,
            item_type=item_type,
            item_rarity=item_rarity,
            item_equipment_type=item_equipment_type,
            status=status,
            created_at=created_at,
            durability_current=durability_current,
            durability_max=durability_max,
            requested_gold=requested_gold
        )

    # Repository基本メソッドの実装
    def find_by_id(self, entity_id: TradeId) -> Optional[GlobalMarketListingReadModel]:
        """IDで出品を検索"""
        return self._listings.get(entity_id)

    def find_by_ids(self, entity_ids: List[TradeId]) -> List[GlobalMarketListingReadModel]:
        """IDのリストで出品を検索"""
        result = []
        for listing_id in entity_ids:
            listing = self._listings.get(listing_id)
            if listing:
                result.append(listing)
        return result

    def save(self, entity: GlobalMarketListingReadModel) -> GlobalMarketListingReadModel:
        """出品を保存"""
        self._listings[entity.trade_id] = entity
        return entity

    def delete(self, entity_id: TradeId) -> bool:
        """出品を削除"""
        if entity_id in self._listings:
            del self._listings[entity_id]
            return True
        return False

    def find_all(self) -> List[GlobalMarketListingReadModel]:
        """全ての出品を取得"""
        return list(self._listings.values())

    # GlobalMarketListingReadModelRepository特有メソッドの実装
    def find_listings(
        self,
        filter_condition: TradeSearchFilter,
        limit: int = 50,
        cursor: Optional[ListingCursor] = None
    ) -> Tuple[List[GlobalMarketListingReadModel], Optional[ListingCursor]]:
        """フィルタ条件で出品を取得（カーソルベースページング）

        Args:
            filter_condition: フィルタ条件
            limit: 取得する最大件数
            cursor: ページングカーソル（Noneの場合は最初のページ）

        Returns:
            (出品リスト, 次のページのカーソル)
        """
        all_listings = list(self._listings.values())

        # フィルタ条件を適用
        filtered_listings = []
        for listing in all_listings:
            if self._matches_filter(listing, filter_condition):
                filtered_listings.append(listing)

        # 作成日時の降順でソート（created_atを基準にtrade_idで安定ソート）
        filtered_listings.sort(key=lambda l: (l.created_at, int(l.trade_id)), reverse=True)

        # カーソルが指定されている場合は、それ以降の出品を取得
        if cursor:
            cursor_filtered_listings = []
            for listing in filtered_listings:
                if (listing.created_at < cursor.created_at or
                    (listing.created_at == cursor.created_at and int(listing.trade_id) < cursor.listing_id)):
                    cursor_filtered_listings.append(listing)
            filtered_listings = cursor_filtered_listings

        # limitで制限
        result_listings = filtered_listings[:limit]

        # 次のページのカーソルを作成
        next_cursor = None
        if len(filtered_listings) > limit and len(result_listings) > 0:
            last_listing = result_listings[-1]
            next_cursor = ListingCursor(
                created_at=last_listing.created_at,
                listing_id=int(last_listing.trade_id)
            )

        return result_listings, next_cursor

    def count_listings(self, filter_condition: TradeSearchFilter) -> int:
        """フィルタ条件に一致する出品数をカウント

        Args:
            filter_condition: フィルタ条件

        Returns:
            出品数
        """
        all_listings = list(self._listings.values())

        # フィルタ条件を適用してカウント
        count = 0
        for listing in all_listings:
            if self._matches_filter(listing, filter_condition):
                count += 1

        return count

    def _matches_filter(self, listing: GlobalMarketListingReadModel, filter_condition: TradeSearchFilter) -> bool:
        """出品がフィルタ条件に一致するかチェック"""
        # アイテム名検索
        if filter_condition.item_name:
            if filter_condition.item_name.lower() not in listing.item_name.lower():
                return False

        # アイテムタイプフィルタ
        if filter_condition.item_types:
            if listing.item_type not in filter_condition.item_types:
                return False

        # レアリティフィルタ
        if filter_condition.rarities:
            if listing.item_rarity not in filter_condition.rarities:
                return False

        # 装備タイプフィルタ（装備品の場合のみ）
        if filter_condition.equipment_types:
            if listing.item_equipment_type is None or listing.item_equipment_type not in filter_condition.equipment_types:
                return False

        # 価格範囲フィルタ
        if filter_condition.min_price is not None and listing.requested_gold < filter_condition.min_price:
            return False
        if filter_condition.max_price is not None and listing.requested_gold > filter_condition.max_price:
            return False

        # ステータスフィルタ
        if filter_condition.statuses:
            if listing.status not in filter_condition.statuses:
                return False

        return True

    # テスト用のヘルパーメソッド
    def clear(self) -> None:
        """全ての出品を削除（テスト用）"""
        self._listings.clear()

    def get_listing_count(self) -> int:
        """出品の総数を取得"""
        return len(self._listings)
