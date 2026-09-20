from dataclasses import dataclass
from datetime import datetime

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
    min_price: int | None
    max_price: int | None
    avg_price: float | None
    median_price: int | None

    # 取引統計
    total_trades: int
    success_rate: float
    last_updated: datetime

    @classmethod
    def create_from_statistics(
        cls,
        item_spec_id: ItemSpecId,
        min_price: int | None,
        max_price: int | None,
        avg_price: float | None,
        median_price: int | None,
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
    def price_range(self) -> tuple[int, int] | None:
        """価格範囲（最小, 最大）を返す"""
        if self.min_price is None or self.max_price is None:
            return None
        return (self.min_price, self.max_price)

    @property
    def success_rate_percentage(self) -> float:
        """成功率をパーセントで返す（0.0-100.0）"""
        return self.success_rate * 100.0
