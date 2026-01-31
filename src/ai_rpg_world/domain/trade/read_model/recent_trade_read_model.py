from datetime import datetime
from typing import List
from dataclasses import dataclass

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId


@dataclass
class RecentTradeData:
    """最近の取引データ"""
    trade_id: int
    price: int
    traded_at: datetime


@dataclass
class RecentTradeReadModel:
    """アイテム別最近取引履歴用ReadModel

    CQRSパターンのReadModelとして機能し、特定のアイテムの最近取引履歴を保持する。
    """

    # 識別子
    item_spec_id: ItemSpecId

    # アイテム情報（非正規化）
    item_name: str

    # 最近の取引データ（時系列順）
    recent_trades: List[RecentTradeData]

    # 最終更新日時
    last_updated: datetime

    @classmethod
    def create_from_item_and_trades(
        cls,
        item_spec_id: ItemSpecId,
        item_name: str,
        recent_trades: List[RecentTradeData],
        last_updated: datetime
    ) -> "RecentTradeReadModel":
        """アイテム情報と取引データからReadModelを作成"""
        return cls(
            item_spec_id=item_spec_id,
            item_name=item_name,
            recent_trades=recent_trades,
            last_updated=last_updated
        )

    @property
    def has_recent_trades(self) -> bool:
        """最近の取引があるかどうか"""
        return len(self.recent_trades) > 0

    @property
    def latest_trade_price(self) -> int:
        """最新の取引価格"""
        if not self.has_recent_trades:
            return 0
        return self.recent_trades[0].price

    @property
    def total_recent_trades(self) -> int:
        """最近の取引総数"""
        return len(self.recent_trades)
