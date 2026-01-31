from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId


@dataclass
class ItemTradeStatisticsReadModel:
    """アイテム取引統計情報用ReadModel

    アイテムごとの取引統計情報を保持する。
    CQRSパターンのReadModelとして機能する。
    """

    # アイテム識別子
    item_spec_id: ItemSpecId

    # 価格統計
    min_price: Optional[int]
    max_price: Optional[int]
    avg_price: Optional[float]
    median_price: Optional[int]

    # 取引統計
    total_trades: int
    success_rate: float
    last_updated: datetime

    @classmethod
    def create_from_statistics(
        cls,
        item_spec_id: ItemSpecId,
        min_price: Optional[int],
        max_price: Optional[int],
        avg_price: Optional[float],
        median_price: Optional[int],
        total_trades: int,
        success_rate: float,
        last_updated: datetime
    ) -> "ItemTradeStatisticsReadModel":
        """統計情報からReadModelを作成"""
        return cls(
            item_spec_id=item_spec_id,
            min_price=min_price,
            max_price=max_price,
            avg_price=avg_price,
            median_price=median_price,
            total_trades=total_trades,
            success_rate=success_rate,
            last_updated=last_updated
        )

    @property
    def has_trade_history(self) -> bool:
        """取引履歴があるかどうか"""
        return self.total_trades > 0

    @property
    def has_price_data(self) -> bool:
        """価格データがあるかどうか"""
        return self.min_price is not None and self.max_price is not None

    @property
    def price_range(self) -> Optional[tuple[int, int]]:
        """価格範囲（最小, 最大）を返す"""
        if not self.has_price_data:
            return None
        return (self.min_price, self.max_price)

    @property
    def success_rate_percentage(self) -> float:
        """成功率をパーセントで返す（0.0-100.0）"""
        return self.success_rate * 100.0
