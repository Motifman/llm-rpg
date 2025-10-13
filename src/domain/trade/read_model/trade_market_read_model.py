from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass

from src.domain.item.value_object.item_spec_id import ItemSpecId


@dataclass
class TradeMarketReadModel:
    """取引相場・統計情報用ReadModel

    ItemSpecごとに市場統計情報を保持する。
    CQRSパターンのReadModelとして機能する。
    """

    # 識別子
    item_spec_id: ItemSpecId

    # アイテム基本情報（非正規化）
    item_name: str
    item_type: str
    item_rarity: str

    # 価格統計
    current_market_price: int
    min_price: int
    max_price: int
    avg_price: float
    median_price: int

    # 取引統計
    total_trades: int
    active_listings: int
    completed_trades: int
    success_rate: float

    # 最終更新日時
    last_updated: datetime

    @classmethod
    def create_from_item_spec_and_stats(
        cls,
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
    ) -> "TradeMarketReadModel":
        """アイテムスペックと統計情報からReadModelを作成"""
        return cls(
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

    @property
    def has_active_trades(self) -> bool:
        """アクティブな取引があるかどうか"""
        return self.active_listings > 0

    @property
    def has_completed_trades(self) -> bool:
        """成立した取引があるかどうか"""
        return self.completed_trades > 0

