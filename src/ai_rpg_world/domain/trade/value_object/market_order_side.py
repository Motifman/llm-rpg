"""板の注文の向き (経済統合 Phase 3)。

売り注文と買い注文を**同じ型**で持つ。板の上では「品を出して gold を求める」
「gold を出して品を求める」が対称で、表示も約定も同じ形で書ける。向きを型で
分けると、同じ処理が 2 本に割れて片方だけ直す事故が起きる。
"""

from enum import Enum


class MarketOrderSide(str, Enum):
    """注文の向き。

    SELL: 品を板に預け、gold を求める
    BUY:  gold を板に預け、品を求める
    """

    SELL = "sell"
    BUY = "buy"

    @property
    def opposite(self) -> "MarketOrderSide":
        return MarketOrderSide.BUY if self is MarketOrderSide.SELL else MarketOrderSide.SELL
