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

from dataclasses import dataclass, replace
from typing import Any, Dict, Optional, Tuple

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
class MarketBoardRow:
    """板の 1 行 (品目 1 つ ぶん)。**見る人の視点で名前を付ける。**

    「売り最安 / 買い最高」ではなく「自分が払う単価 / 自分が受け取る単価」に
    する。売り手視点と買い手視点が混線すると、同じ数字が誰にとっての値なのか
    読み違える。表示も「18G で買える / 15G で売れる」と、**その人が次に打てる
    手の言葉**で出す (文面の組み立ては formatter 側)。

    件数と総数量の両方を持つ。件数だけだと「3 件あるが全部 1 つずつ」と
    「3 件で計 9 つ」が同じに見え、買える総量が読めない。件数は競争の激しさ
    (4 件も出ている = 下げないと売れない) を読む材料にもなる。

    値が ``None`` は「その手は打てない」(買える注文が無い / 買い注文が無い)。
    0 を入れると「0G で買える」と読めてしまうので分ける。
    """

    item_spec_id: int
    #: この品を買うときに払う単価。None なら買えない (出品が無い)。
    buy_price_gold: Optional[int] = None
    #: 買える出品の件数。競争の激しさを読む材料。
    listing_count: int = 0
    #: 買える総数。
    buyable_quantity: int = 0
    #: この品を売るときに受け取る単価。None なら売れない (買い注文が無い)。
    sell_price_gold: Optional[int] = None
    #: 買い注文の件数。
    bid_count: int = 0
    #: 売れる総数。
    sellable_quantity: int = 0
    #: 直近にこの品が成立した単価。None なら一度も約定していない。
    last_trade_price_gold: Optional[int] = None


@dataclass(frozen=True)
class MarketBoardView:
    """ある人から見た板。

    ``rows`` は品目ごとにまとめた需給、``own_orders`` は自分の注文を 1 件ずつ。
    集約だけだと、値を変える・取り下げるときに**どの注文を指すのかを組み立て
    られない**ので、自分のぶんだけは個別に出す。
    """

    rows: Tuple[MarketBoardRow, ...] = ()
    own_orders: Tuple[MarketOrder, ...] = ()


@dataclass(frozen=True)
class MarketBoard:
    """板に並んでいる注文と、品目ごとの直近の約定。"""

    orders: Tuple[MarketOrder, ...] = ()
    #: 品目ごとに直近の約定 1 件。**約定を作れるのは ``taken`` だけ**で、
    #: そこが同時に新しい板を返すので、記録し忘れた板を作る道が無い。
    #: service 側で記録する形にすると、約定の経路 (`buy_best` / `sell_best` /
    #: `take_order`) が増えたときに片方だけ忘れる。
    last_trades: Tuple[MarketTrade, ...] = ()

    @classmethod
    def empty(cls) -> "MarketBoard":
        return cls(orders=())

    # ── 参照 ────────────────────────────────────────────────────────────

    def last_trade_price_of(self, item_spec_id: int) -> Optional[int]:
        """その品が直近に成立した単価。一度も約定していなければ None。

        0 を返さない。0 は「0G で成立した」と読める値で、**一度も成立して
        いない**とは別のことを言う。
        """
        for trade in self.last_trades:
            if trade.item_spec_id == item_spec_id:
                return trade.unit_price_gold
        return None

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

    def rows_for(self, viewer: MarketParticipant) -> MarketBoardView:
        """その人から見た板を返す。

        **読み出しは必ず見る人を引数に取る。** いまの検証シナリオ (品目 4〜5 種)
        では誰から見ても同じ行が出るので、絞り込みはまだ書かない (YAGNI)。それでも
        引数の形を先に決めるのは、品目が増えたときに「全件を見せて絞らせる」形が
        破綻するため。旧マーケットボードのページ送り 11 ツールはその問題への解
        だったが、画面遷移で手番が溶ける形だったので不採用にした。将来は
        「一覧をやめて関心で絞る」(自分の出品 / 自分の買い注文 / 自分の所持品 /
        自分の職能で作れる品 / 買い注文が出ている品) + 名前引きの検索 1 つを
        想定していて、**見る人を引数に取らない実装だとそのとき全部書き直しになる**。

        見る人が今すでに効いている点も 2 つある。自分の注文は自分で受けられない
        ので、集約の値からは自分の注文を外す (買えない値を相場として読ませない)。
        引き取り待ちの行は他人には出さず、持ち主の ``own_orders`` にだけ出す。
        """
        rows: Dict[int, Dict[str, Any]] = {}
        for order in self.orders:
            if order.is_awaiting_collection or order.owner == viewer:
                # 前者は誰にも買えない。後者は自分では受けられないので、
                # 需給の集約には数えない (自分の欄には別に出る)。
                continue
            bucket = rows.setdefault(order.item_spec_id, {})
            # **注文の向きと、見る人にとっての手は逆になる。** 板に出ている
            # 売り注文は、見る人にとっては「買える」。ここを取り違えると値が
            # 反対側に出る。
            is_listing = order.side is MarketOrderSide.SELL
            count_key = "listing_count" if is_listing else "bid_count"
            qty_key = "buyable_quantity" if is_listing else "sellable_quantity"
            price_key = "buy_price_gold" if is_listing else "sell_price_gold"
            bucket[count_key] = bucket.get(count_key, 0) + 1
            bucket[qty_key] = bucket.get(qty_key, 0) + order.quantity
            best = bucket.get(price_key)
            price = order.unit_price_gold
            if best is None:
                bucket[price_key] = price
            elif is_listing:
                # 買う側は安いほうが良い。
                bucket[price_key] = min(best, price)
            else:
                # 売る側は高いほうが良い。
                bucket[price_key] = max(best, price)

        for trade in self.last_trades:
            # **注文が 1 件も無くても、成立した値は行として出す。** 板が空でも
            # 「直近 9G で売れた」は次に打てる手 (その値で出す) を作る。
            rows.setdefault(trade.item_spec_id, {})

        own = tuple(order for order in self.orders if order.owner == viewer)
        # 自分の注文しか無い品目も行として出す。需給は空でも「その品が板に
        # 出ている」ことは見えていてよい。
        for order in own:
            rows.setdefault(order.item_spec_id, {})
        return MarketBoardView(
            rows=tuple(
                MarketBoardRow(
                    item_spec_id=spec_id,
                    last_trade_price_gold=self.last_trade_price_of(spec_id),
                    **bucket,
                )
                for spec_id, bucket in sorted(rows.items())
            ),
            own_orders=own,
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
        return replace(self, orders=self.orders + (order,))

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

    def with_repriced(self, order: MarketOrder) -> "MarketBoard":
        """値を変えた注文で差し替えた板を返す。"""
        self._require_order(order.order_id)
        return self._replace_order(order)

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
        return replace(board, last_trades=board._with_last(trade)), trade

    # ── 内部 ────────────────────────────────────────────────────────────

    def _require_order(self, order_id: MarketOrderId) -> MarketOrder:
        order = self.find(order_id)
        if order is None:
            raise MarketBoardStateException(
                f"その注文は板にありません (order_id={order_id.value})"
            )
        return order

    def _without(self, order_id: MarketOrderId) -> "MarketBoard":
        return replace(
            self, orders=tuple(o for o in self.orders if o.order_id != order_id)
        )

    def _replace_order(self, order: MarketOrder) -> "MarketBoard":
        return replace(
            self,
            orders=tuple(
                order if o.order_id == order.order_id else o for o in self.orders
            ),
        )

    def _with_last(self, trade: MarketTrade) -> Tuple[MarketTrade, ...]:
        """その品目の直近の約定を差し替えた並びを返す。

        品目ごとに 1 件だけ持つ。全件を持つと板が run のあいだ単調に太り、
        snapshot も同じだけ太る。**時系列は trace の仕事**で、板が持つのは
        「いまの値付けの材料」だけでよい。
        """
        return tuple(
            t for t in self.last_trades if t.item_spec_id != trade.item_spec_id
        ) + (trade,)


__all__ = ["MarketBoard", "MarketBoardRow", "MarketBoardView", "MarketTrade"]
