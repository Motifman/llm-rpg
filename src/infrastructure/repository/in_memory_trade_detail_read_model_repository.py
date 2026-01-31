"""
InMemoryTradeDetailReadModelRepository - TradeDetailReadModelを使用するインメモリ実装
"""
from typing import List, Optional, Dict
from datetime import datetime, timedelta

from src.domain.trade.repository.trade_detail_read_model_repository import TradeDetailReadModelRepository
from src.domain.trade.read_model.trade_detail_read_model import TradeDetailReadModel
from src.domain.trade.value_object.trade_id import TradeId
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.value_object.item_instance_id import ItemInstanceId
from src.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType
from src.domain.trade.enum.trade_enum import TradeStatus


class InMemoryTradeDetailReadModelRepository(TradeDetailReadModelRepository):
    """TradeDetailReadModelを使用するインメモリリポジトリ"""

    def __init__(self):
        self._details: Dict[TradeId, TradeDetailReadModel] = {}

        # サンプル取引データを作成
        self._setup_sample_data()

    def _setup_sample_data(self):
        """サンプル取引データのセットアップ"""
        # 現在の時間を基準に過去の取引を作成
        base_time = datetime.now()

        # 様々な取引ステータスとアイテムの組み合わせで取引を作成

        # 1. アクティブな取引（鋼の剣）
        sword_detail = self._create_sample_detail(
            trade_id=1,
            item_spec_id=1,
            item_instance_id=1,
            item_name="鋼の剣",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.COMMON,
            item_equipment_type=EquipmentType.WEAPON,
            item_description="鋭い切れ味の剣",
            durability_current=85,
            durability_max=100,
            requested_gold=500,
            seller_name="勇者",
            buyer_name=None,
            status=TradeStatus.ACTIVE
        )
        self._details[TradeId(1)] = sword_detail

        # 2. アクティブな取引（魔法の杖）
        staff_detail = self._create_sample_detail(
            trade_id=2,
            item_spec_id=2,
            item_instance_id=2,
            item_name="魔法の杖",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.UNCOMMON,
            item_equipment_type=EquipmentType.WEAPON,
            item_description="魔法の力を増幅する杖",
            durability_current=92,
            durability_max=100,
            requested_gold=1200,
            seller_name="賢者",
            buyer_name=None,
            status=TradeStatus.ACTIVE
        )
        self._details[TradeId(2)] = staff_detail

        # 3. アクティブな取引（回復薬）
        potion_detail = self._create_sample_detail(
            trade_id=3,
            item_spec_id=3,
            item_instance_id=3,
            item_name="回復薬",
            item_quantity=5,
            item_type=ItemType.CONSUMABLE,
            item_rarity=Rarity.COMMON,
            item_equipment_type=None,
            item_description="HPを50回復する薬",
            durability_current=None,
            durability_max=None,
            requested_gold=150,
            seller_name="薬草師",
            buyer_name=None,
            status=TradeStatus.ACTIVE
        )
        self._details[TradeId(3)] = potion_detail

        # 4. 完了した取引（ドラゴンスケールアーマー）
        armor_detail = self._create_sample_detail(
            trade_id=4,
            item_spec_id=4,
            item_instance_id=4,
            item_name="ドラゴンスケールアーマー",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.RARE,
            item_equipment_type=EquipmentType.ARMOR,
            item_description="ドラゴンの鱗で作られた強靭な鎧",
            durability_current=95,
            durability_max=100,
            requested_gold=5000,
            seller_name="ドラゴンスレイヤー",
            buyer_name="騎士団長",
            status=TradeStatus.COMPLETED
        )
        self._details[TradeId(4)] = armor_detail

        # 5. キャンセルされた取引（鉄の盾）
        shield_detail = self._create_sample_detail(
            trade_id=5,
            item_spec_id=5,
            item_instance_id=5,
            item_name="鉄の盾",
            item_quantity=1,
            item_type=ItemType.EQUIPMENT,
            item_rarity=Rarity.COMMON,
            item_equipment_type=EquipmentType.SHIELD,
            item_description="堅牢な防御力を持つ盾",
            durability_current=78,
            durability_max=100,
            requested_gold=300,
            seller_name="ガーディアン",
            buyer_name=None,
            status=TradeStatus.CANCELLED
        )
        self._details[TradeId(5)] = shield_detail

        # 6. 完了した取引（輝く宝石）
        gem_detail = self._create_sample_detail(
            trade_id=6,
            item_spec_id=6,
            item_instance_id=6,
            item_name="輝く宝石",
            item_quantity=1,
            item_type=ItemType.MATERIAL,
            item_rarity=Rarity.RARE,
            item_equipment_type=None,
            item_description="魔法の力を秘めた輝く宝石",
            durability_current=None,
            durability_max=None,
            requested_gold=2500,
            seller_name="トレジャーハンター",
            buyer_name="魔法使い",
            status=TradeStatus.COMPLETED
        )
        self._details[TradeId(6)] = gem_detail

    def _create_sample_detail(self, trade_id: int, item_spec_id: int, item_instance_id: int,
                             item_name: str, item_quantity: int, item_type: ItemType,
                             item_rarity: Rarity, item_equipment_type: Optional[EquipmentType],
                             item_description: str, durability_current: Optional[int],
                             durability_max: Optional[int], requested_gold: int,
                             seller_name: str, buyer_name: Optional[str], status: TradeStatus) -> TradeDetailReadModel:
        """サンプル取引詳細を作成するヘルパーメソッド"""
        return TradeDetailReadModel.create_from_trade_data(
            trade_id=TradeId(trade_id),
            item_spec_id=ItemSpecId(item_spec_id),
            item_instance_id=ItemInstanceId(item_instance_id),
            item_name=item_name,
            item_quantity=item_quantity,
            item_type=item_type,
            item_rarity=item_rarity,
            item_equipment_type=item_equipment_type,
            item_description=item_description,
            durability_current=durability_current,
            durability_max=durability_max,
            requested_gold=requested_gold,
            seller_name=seller_name,
            buyer_name=buyer_name,
            status=status.value  # Enumを文字列に変換
        )

    # Repository基本メソッドの実装
    def find_by_id(self, entity_id: TradeId) -> Optional[TradeDetailReadModel]:
        """IDで取引詳細を検索"""
        return self._details.get(entity_id)

    def find_by_ids(self, entity_ids: List[TradeId]) -> List[TradeDetailReadModel]:
        """IDのリストで取引詳細を検索"""
        result = []
        for detail_id in entity_ids:
            detail = self._details.get(detail_id)
            if detail:
                result.append(detail)
        return result

    def save(self, entity: TradeDetailReadModel) -> TradeDetailReadModel:
        """取引詳細を保存"""
        self._details[entity.trade_id] = entity
        return entity

    def delete(self, entity_id: TradeId) -> bool:
        """取引詳細を削除"""
        if entity_id in self._details:
            del self._details[entity_id]
            return True
        return False

    def find_all(self) -> List[TradeDetailReadModel]:
        """全ての取引詳細を取得"""
        return list(self._details.values())

    # TradeDetailReadModelRepository特有メソッドの実装
    def find_detail(self, trade_id: TradeId) -> Optional[TradeDetailReadModel]:
        """取引IDで詳細情報を取得

        Args:
            trade_id: 取引ID

        Returns:
            取引詳細情報（存在しない場合はNone）
        """
        return self._details.get(trade_id)

    # テスト用のヘルパーメソッド
    def clear(self) -> None:
        """全ての取引詳細を削除（テスト用）"""
        self._details.clear()

    def get_detail_count(self) -> int:
        """取引詳細の総数を取得"""
        return len(self._details)
