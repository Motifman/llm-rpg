"""市場の掲示板 (経済統合 Phase 3)。

## 自動では約定しない

売り 20G と買い 22G が板に並んでも、engine は潰さない。理由は、**手番の外で
持ち物が変わると、エージェントから見て「自分が知らないうちに世界が変わった」
ことになる**から。この世界は観測駆動で、自己の継続性を大事にしている。取引は
必ず誰かの手番の決定として起きる。

値の交差した注文が板に残るのは欠陥ではなく**機会**として見える (「買い 22G が
出ている、自分の 20G を受ければ 2G 得だ」)。それを自力で見つけて取れる
エージェントが居るかどうかは、この実験の観測点の 1 つ。人間が trace を読んだ
とき「約定漏れのバグ」に見えるので、意図であることをここに書いておく。

## 板は不変オブジェクト

注文の追加・取り下げ・約定はすべて**新しい板**を返す。板の書き換えを許すと、
snapshot の捕獲中に変わる・観測の発火順と食い違う、といった追いにくい事故が
入り込む。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ai_rpg_world.domain.trade.aggregate.market_order import MarketOrder
from ai_rpg_world.domain.trade.exception.trade_exception import (
    MarketBoardStateException,
)
from ai_rpg_world.domain.trade.value_object.market_order_id import MarketOrderId
from ai_rpg_world.domain.trade.value_object.market_order_side import MarketOrderSide
from ai_rpg_world.domain.trade.value_object.market_participant import MarketParticipant


@dataclass(frozen=True)
class MarketTrade:
    """約定 1 件。価格の時系列を後から引くための一次データ。

    ``taker_side`` は「どちらが相手の掲示を受けたか」。値を決めたのがどちらかを
    読むために要る。売り注文が受けられたなら値は売り手が付けた値、買い注文が
    受けられたなら買い手が付けた値。これが無いと、時系列は引けても「誰が値を
    動かしたか」が読めない。
    """

    resting_order_id: MarketOrderId
    item_spec_id: int
    quantity: int
    unit_price_gold: int
    seller: MarketParticipant
    buyer: MarketParticipant
    taker_side: MarketOrderSide
    at_tick: int

    @property
    def total_gold(self) -> int:
        return self.unit_price_gold * self.quantity


@dataclass(frozen=True)
class MarketBoard:
    """板に並んでいる注文の全体。"""

    orders: Tuple[MarketOrder, ...] = ()

    @classmethod
    def empty(cls) -> "MarketBoard":
        return cls(orders=())

    # ── 参照 ────────────────────────────────────────────────────────────

    def find(self, order_id: MarketOrderId) -> Optional[MarketOrder]:
        for order in self.orders:
            if order.order_id == order_id:
                return order
        return None

    def orders_visible_to(
        self, viewer: MarketParticipant
    ) -> Tuple[MarketOrder, ...]:
        """その人から見える注文を返す。

        引き取り待ちの行は他人からは買えないので見せない。ただし**持ち主には
        見える**。見えないと、期限切れの通知を 1 回見落とした時点で預けた物を
        取り戻す手がかりが消える (静かな失敗)。
        """
        return tuple(
            order
            for order in self.orders
            if not order.is_awaiting_collection or order.owner == viewer
        )

    def expired_orders(self, current_tick: int) -> Tuple[MarketOrder, ...]:
        """その手番で期限を過ぎている注文を返す (板は変えない)。

        状態遷移と観測の発火は呼び出し側 (tick stage) の仕事にする。板が観測を
        持つと、保存・復元のたびに「流れた」が二重に届きうる。引き取り待ちは
        既に一度流れているので、二度目は返さない。
        """
        return tuple(
            order
            for order in self.orders
            if not order.is_awaiting_collection and order.is_expired_at(current_tick)
        )

    # ── 更新 (どれも新しい板を返す) ────────────────────────────────────

    def with_order(self, order: MarketOrder) -> "MarketBoard":
        """注文を 1 件置いた板を返す。"""
        if self.find(order.order_id) is not None:
            raise MarketBoardStateException(
                f"同じ注文 ID は二度置けません (order_id={order.order_id.value})"
            )
        return MarketBoard(orders=self.orders + (order,))

    def cancelled(
        self, order_id: MarketOrderId, *, by: MarketParticipant
    ) -> "MarketBoard":
        """その人の注文を取り下げた板を返す。"""
        order = self._require_order(order_id)
        if order.owner != by:
            raise MarketBoardStateException(
                f"他人の注文は取り下げられません (order_id={order_id.value})"
            )
        return self._without(order_id)

    def awaiting_collection(self, order_id: MarketOrderId) -> "MarketBoard":
        """その注文を引き取り待ちにした板を返す。"""
        order = self._require_order(order_id)
        return self._replace_order(order.awaiting_collection())

    def taken(
        self,
        order_id: MarketOrderId,
        *,
        by: MarketParticipant,
        quantity: int,
        at_tick: int,
    ) -> Tuple["MarketBoard", MarketTrade]:
        """板の注文を受けた結果の板と、約定 1 件を返す。"""
        order = self._require_order(order_id)
        if order.owner == by:
            # gold と品が自分の中で往復するだけなのに、板には「約定した」
            # 履歴が値として残る。価格の時系列に偽の値が混ざる。
            raise MarketBoardStateException(
                f"自分の注文は自分で受けられません (order_id={order_id.value})"
            )
        remaining = order.filled_by(quantity)
        board = (
            self._without(order_id)
            if remaining.is_exhausted
            else self._replace_order(remaining)
        )
        seller = order.owner if order.side is MarketOrderSide.SELL else by
        buyer = by if order.side is MarketOrderSide.SELL else order.owner
        trade = MarketTrade(
            resting_order_id=order_id,
            item_spec_id=order.item_spec_id,
            quantity=quantity,
            unit_price_gold=order.unit_price_gold,
            seller=seller,
            buyer=buyer,
            taker_side=order.side.opposite,
            at_tick=at_tick,
        )
        return board, trade

    # ── 内部 ────────────────────────────────────────────────────────────

    def _require_order(self, order_id: MarketOrderId) -> MarketOrder:
        order = self.find(order_id)
        if order is None:
            raise MarketBoardStateException(
                f"その注文は板にありません (order_id={order_id.value})"
            )
        return order

    def _without(self, order_id: MarketOrderId) -> "MarketBoard":
        return MarketBoard(
            orders=tuple(o for o in self.orders if o.order_id != order_id)
        )

    def _replace_order(self, order: MarketOrder) -> "MarketBoard":
        return MarketBoard(
            orders=tuple(
                order if o.order_id == order.order_id else o for o in self.orders
            )
        )


__all__ = ["MarketBoard", "MarketTrade"]
