"""市場の板に注文を出し、受け、取り下げ、期限で戻す (経済統合 Phase 3)。

## 板は預かる (凍結ではない)

出品した品は所持品から消えて板へ移り、買い注文を出したら gold は残高から
引かれて板へ移る。Phase 2 の同席取引は凍結 (手元に残したまま予約する) だったが、
板は預ける方を選んだ。凍結だと「持っているが使えない」状態ができて所持品の
表示と実際に使える量がずれ、Phase 2 ではそこで二重減算のバグが生まれた。
預ければ、**物がどこにあるかが観測と一致する**。

## 商人は世界の外との出入り口

商人が買い取った品は世界から消え、商人へ払った gold も世界から消える。
Phase 1 で商人の gold を無限と決めたのと同じ一本の理由から出ている。在庫を
持たせると「商人を経由した転売」が最短の稼ぎ方になり、板での価格形成が商人に
緩衝される。

## 受け取れないときは約定させない

`PlayerInventoryAggregate.acquire_item` は満杯だと**黙って品を捨てる** (溢れ
イベントを出して return する)。代金だけ払って品が消えるのは、いちばん質の
悪い静かな失敗になるので、受ける前に空きを確かめる。

期限切れの返却でも同じ問題が起きるが、こちらは断る相手が居ない。返せない
ぶんは板に「引き取り待ち」として残し、空きを作ってから `market_cancel` で
引き取れるようにする。消すと静かな失敗になる。
"""

from __future__ import annotations

import logging

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
    remove_items_of_specs_from_inventory,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.aggregate.market_board import MarketBoard, MarketTrade
from ai_rpg_world.domain.trade.aggregate.market_order import MarketOrder
from ai_rpg_world.domain.trade.value_object.market_order_id import MarketOrderId
from ai_rpg_world.domain.trade.value_object.market_order_side import MarketOrderSide
from ai_rpg_world.domain.trade.value_object.market_participant import MarketParticipant
from ai_rpg_world.domain.trade.value_object.market_reach import MarketReach

logger = logging.getLogger(__name__)

#: gold の増減 trace で使う出所。merchant_buy / merchant_sell / trade_settle と
#: 並ぶ 4 つ目の源泉。
MARKET_GOLD_SOURCE = "market_settle"

#: 板の既定の期限 (手番)。世界の広さで決まる値なのでシナリオが上書きする。
DEFAULT_ORDER_EXPIRES_IN_TICKS = 40


class MarketException(Exception):
    """市場の操作が通らなかった。"""

    error_code = "MARKET_FAILED"


class MarketUnknownItemError(MarketException):
    error_code = "MARKET_UNKNOWN_ITEM"

    def __init__(self, *, item_label: str) -> None:
        super().__init__(
            f"この世界に「{item_label}」という品はありません。名前を確かめてください。"
        )


class MarketItemNotOwnedError(MarketException):
    error_code = "MARKET_ITEM_NOT_OWNED"

    def __init__(self, *, item_name: str, quantity: int, owned: int) -> None:
        super().__init__(
            f"{item_name}を{quantity}つ出そうとしましたが、いま出せるのは{owned}つです。"
        )


class MarketGoldNotEnoughError(MarketException):
    error_code = "MARKET_GOLD_NOT_ENOUGH"

    def __init__(self, *, needed: int, available: int) -> None:
        super().__init__(
            f"{needed}G が要りますが、いま使えるのは{available}G です。"
        )


class MarketDuplicateOrderError(MarketException):
    error_code = "MARKET_DUPLICATE_ORDER"

    def __init__(self, *, item_name: str, action: str) -> None:
        super().__init__(
            f"{item_name}の{action}は既に板に出ています。"
            "値を変えたいなら出し直しではなく値の付け直しを、"
            "やめるなら取り下げてください。"
        )


class MarketOrderAwaitingCollectionError(MarketException):
    error_code = "MARKET_ORDER_AWAITING_COLLECTION"

    def __init__(self, *, item_name: str) -> None:
        super().__init__(
            f"板には、期限切れで預けたままの{item_name}が残っています。"
            "先にそれを引き取ってから出し直してください。"
        )


class MarketInventoryFullError(MarketException):
    error_code = "MARKET_INVENTORY_FULL"

    def __init__(self, *, needed: int, free: int) -> None:
        super().__init__(
            f"受け取るのに{needed}つぶんの空きが要りますが、空いているのは{free}つです。"
            "何かを置くか使ってから受け直してください。"
        )


class MarketBoardNotHereError(MarketException):
    error_code = "MARKET_BOARD_NOT_HERE"

    def __init__(self) -> None:
        super().__init__(
            "市場の掲示板はこの場所にありません。"
            "板のある場所まで移動してから使ってください。"
        )


class MarketNothingToBuyError(MarketException):
    error_code = "MARKET_NOTHING_TO_BUY"

    def __init__(self, *, item_name: str) -> None:
        super().__init__(
            f"{item_name}は板に 1 つも出ていません。誰かが出すのを待つか、"
            "買い注文を出して待ってください。"
        )


class MarketOnlyYourOwnListingError(MarketException):
    error_code = "MARKET_ONLY_YOUR_OWN"

    def __init__(self, *, item_name: str) -> None:
        super().__init__(
            f"板に出ている{item_name}は自分の出品だけです。自分の注文は自分で"
            "受けられません。値を下げて誰かが買うのを待つか、取り下げてください。"
        )


class MarketNothingToSellError(MarketException):
    error_code = "MARKET_NOTHING_TO_SELL"

    def __init__(self, *, item_name: str) -> None:
        super().__init__(
            f"{item_name}を求める買い注文は板に出ていません。誰かが求めるのを"
            "待つか、自分で売り注文を出して待ってください。"
        )


class MarketOnlyYourOwnBidError(MarketException):
    error_code = "MARKET_ONLY_YOUR_OWN_BID"

    def __init__(self, *, item_name: str) -> None:
        super().__init__(
            f"{item_name}を求めているのは自分の買い注文だけです。自分の注文は"
            "自分で受けられません。値を上げて誰かが売るのを待つか、"
            "取り下げてください。"
        )


class MarketNoSuchOrderError(MarketException):
    error_code = "MARKET_NO_SUCH_ORDER"

    def __init__(self, *, item_name: str, action: str) -> None:
        super().__init__(
            f"{item_name}の{action}は板に出ていません。"
            "「あなたの出品」に出ている品の名前を指定してください。"
        )


@dataclass(frozen=True)
class MarketPurchase:
    """1 回の買い物。複数の注文にまたがることがある。

    ``requested_quantity`` を残すのは、**求めた数と買えた数の両方**が読める
    ようにするため。買えた数だけだと、読む側は自分の意図が満たされたか判断
    できない。
    """

    item_spec_id: int
    item_name: str
    requested_quantity: int
    settlements: Tuple["MarketSettlement", ...]

    @property
    def bought_quantity(self) -> int:
        return sum(s.trade.quantity for s in self.settlements)

    @property
    def total_gold(self) -> int:
        return sum(s.trade.total_gold for s in self.settlements)

    @property
    def is_partial(self) -> bool:
        return self.bought_quantity < self.requested_quantity


@dataclass(frozen=True)
class MarketSale:
    """1 回の売り。複数の買い注文にまたがることがある。

    ``requested_quantity`` を残すのは買いと同じ理由で、**求めた数と売れた数の
    両方**が読めるようにするため。
    """

    item_spec_id: int
    item_name: str
    requested_quantity: int
    settlements: Tuple["MarketSettlement", ...]

    @property
    def sold_quantity(self) -> int:
        return sum(s.trade.quantity for s in self.settlements)

    @property
    def total_gold(self) -> int:
        return sum(s.trade.total_gold for s in self.settlements)

    @property
    def is_partial(self) -> bool:
        return self.sold_quantity < self.requested_quantity


@dataclass(frozen=True)
class MarketSettlement:
    """成立した約定 1 件。trace と観測はここから作る。"""

    trade: MarketTrade
    seller_name: str
    buyer_name: str
    item_name: str


@dataclass(frozen=True)
class MarketOrderExpiryResult:
    """注文一件の期限切れ処理で確定した状態と観測材料。"""

    order: MarketOrder
    deposit_returned: bool

    @property
    def event_kind(self) -> str:
        return "expired_returned" if self.deposit_returned else "expired_awaiting"


class MarketService:
    """板の注文の受付・約定・取り下げ・期限切れを実行する。"""

    def __init__(
        self,
        *,
        market_board_store: Any,
        spot_graph_repository: Optional[Any] = None,
        player_inventory_repository: Any,
        player_status_repository: Any,
        item_repository: Any,
        item_spec_repository: Any,
        item_spec_name_resolver: Optional[Any] = None,
        entity_name_resolver: Optional[Any] = None,
        event_publisher: Optional[Any] = None,
        trace_recorder: Optional[Any] = None,
        current_tick_provider: Optional[Any] = None,
        expires_in_ticks: int = DEFAULT_ORDER_EXPIRES_IN_TICKS,
        overflow_sink: Any = None,
        delivery_overflow_sink: Any = None,
        reach: MarketReach = MarketReach.AT_SPOT,
    ) -> None:
        self._store = market_board_store
        self._graph = spot_graph_repository
        self._inventories = player_inventory_repository
        self._statuses = player_status_repository
        self._items = item_repository
        self._item_specs = item_spec_repository
        self._item_name = item_spec_name_resolver
        self._entity_name = entity_name_resolver
        self._events = event_publisher
        self._trace = trace_recorder
        self._now = current_tick_provider
        self._expires_in_ticks = expires_in_ticks
        self._overflow_sink = overflow_sink
        # 買い注文の相手へ品を渡すときだけ使う行き先。受け取れなければ
        # **板の足元**へ置く (買い手の居場所に依存させない)。
        self._delivery_overflow_sink = delivery_overflow_sink
        # 届く範囲は世界の規則で、run のあいだ変わらない。板の状態ではない
        # ので store には置かず、snapshot にも載せない。
        self._reach = reach

    def set_trace_recorder(self, trace_recorder: Any, current_tick_provider: Any) -> None:
        """値動きの一次データを残す先を後付けで注入する。

        recorder は runtime を組み終えてからしか作れない。注入前は trace が
        出ない — **run 後に価格の時系列が引けない**状態なので、配線漏れは
        時系列を組み立てるテストで落ちる。
        """
        self._trace = trace_recorder
        self._now = current_tick_provider
        self._record_board_snapshot()

    def _record_board_snapshot(self) -> None:
        """recorder が付いた時点の板を、1 注文 1 行で残す。

        **初期注文は recorder が付く前に置かれる。** そのままだと trace には
        1 行も残らず、`docs/trace_format.md` に書いた「価格の時系列が引ける」が
        半分嘘になる。実 run では、初期注文への約定が「`listed` の無い注文への
        `settled`」になり、復元器が**黙って読み飛ばした**。

        `listed` としては流さない。同じ kind にすると、分析側が「その手番に
        全員が同時に出品した」と読む。**出品は出来事だが、スナップショットは
        出来事ではない。**

        板が空なら 1 行も出さない。板の無い世界の trace を太らせないため。
        """
        for order in self._store.board().orders:
            self._record(
                kind="board_snapshot",
                item_spec_id=order.item_spec_id,
                side=order.side.value,
                quantity=order.quantity,
                unit_price=order.unit_price_gold,
                actor_name=self._name_of(order.owner),
                order_id=order.order_id.value,
                expires_at_tick=order.expires_at_tick,
            )

    def set_event_publisher(self, event_publisher: Any) -> None:
        """観測を出す先を後付けで注入する。

        publisher は runtime を組み終えてからしか作れないので、商人・同席取引と
        同じく setter で後付けする。注入前は観測が出ない — 板が動いても誰にも
        見えない状態なので、配線漏れは第三者観測のテストで落ちる。
        """
        self._events = event_publisher

    def for_expiry_repositories(
        self,
        *,
        player_inventory_repository: Any,
        player_status_repository: Any,
        item_repository: Any,
    ) -> "MarketService":
        """期限切れcommand用repositoryへ差し替えた副作用なしの複製を返す。"""
        return MarketService(
            market_board_store=self._store,
            spot_graph_repository=self._graph,
            player_inventory_repository=player_inventory_repository,
            player_status_repository=player_status_repository,
            item_repository=item_repository,
            item_spec_repository=self._item_specs,
            item_spec_name_resolver=self._item_name,
            entity_name_resolver=self._entity_name,
            event_publisher=None,
            trace_recorder=None,
            current_tick_provider=self._now,
            expires_in_ticks=self._expires_in_ticks,
            overflow_sink=self._overflow_sink,
            delivery_overflow_sink=self._delivery_overflow_sink,
            reach=self._reach,
        )

    # ── 参照 ────────────────────────────────────────────────────────────

    def board(self) -> MarketBoard:
        return self._store.board()

    def board_view_for(self, player_id: PlayerId):
        """その人から見た板を返す。

        見る人を引数に取るのは板の側の規約 (自分の注文は自分で受けられない
        ので集約から外れ、引き取り待ちは持ち主にだけ見える)。呼ぶ側に
        ``MarketParticipant`` を組み立てさせない。
        """
        return self._store.board().rows_for(MarketParticipant.player(player_id))

    def item_display_name(self, item_spec_id: int) -> str:
        """品名を表示名で引く。引けない品は識別子ではなく畳んだ名前にする。

        識別子を出すと、プロンプトに engine のキーが漏れる。
        """
        if self._item_name is None:
            return "(名前不明のもの)"
        try:
            return self._item_name(int(item_spec_id)) or "(名前不明のもの)"
        except Exception:  # noqa: BLE001
            return "(名前不明のもの)"

    @property
    def reach(self) -> MarketReach:
        """板がどこまで届くか。表示と `market_view` の場所判定が読む。"""
        return self._reach

    @property
    def board_spot_id(self) -> Optional[Any]:
        """板の置いてある場所。板の無い世界では None。

        表示の側が「板がここにあるか」を判断するのに使う。store を直接読ませる
        と、表示が store の形に依存する。
        """
        return getattr(self._store, "board_spot_id", None)

    # ── 出品・入札 ──────────────────────────────────────────────────────

    def place_sell_order(
        self,
        player_id: PlayerId,
        *,
        item_label: str,
        quantity: int,
        unit_price: int,
        current_tick: int,
    ) -> MarketOrder:
        """品を板へ預けて売り注文を出す。"""
        self._require_at_board(player_id)
        spec_id = self._item_spec_id_by_label(item_label)
        self._require_no_order_yet(player_id, spec_id, MarketOrderSide.SELL)
        self._require_holds(player_id, spec_id, quantity)
        order = self._new_order(
            side=MarketOrderSide.SELL,
            owner=MarketParticipant.player(player_id),
            item_spec_id=spec_id,
            quantity=quantity,
            unit_price=unit_price,
            current_tick=current_tick,
        )
        self._take_items_from(player_id, spec_id, quantity)
        self._store.save(self._store.board().with_order(order))
        self._publish(
            player_id, kind="listed", side=MarketOrderSide.SELL, item_spec_id=spec_id,
            quantity=order.quantity, unit_price=order.unit_price_gold,
        )
        self._record(
            kind="listed", item_spec_id=spec_id, side=MarketOrderSide.SELL.value,
            quantity=order.quantity, unit_price=order.unit_price_gold,
            actor_name=self._name_of(MarketParticipant.player(player_id)),
            order_id=order.order_id.value,
            expires_at_tick=order.expires_at_tick,
        )
        return order

    def place_buy_order(
        self,
        player_id: PlayerId,
        *,
        item_label: str,
        quantity: int,
        unit_price: int,
        current_tick: int,
    ) -> MarketOrder:
        """gold を板へ預けて買い注文を出す。"""
        self._require_at_board(player_id)
        spec_id = self._item_spec_id_by_label(item_label)
        self._require_no_order_yet(player_id, spec_id, MarketOrderSide.BUY)
        # 払えるかを、注文を作る前に市場の言葉で確かめる。ここを省くと
        # `pay_gold` の InsufficientGoldException がそのまま外へ出て、
        # 呼び出し側は「市場の失敗」と「所持金集約の失敗」を区別できない。
        self._require_gold(player_id, int(quantity) * int(unit_price))
        order = self._new_order(
            side=MarketOrderSide.BUY,
            owner=MarketParticipant.player(player_id),
            item_spec_id=spec_id,
            quantity=quantity,
            unit_price=unit_price,
            current_tick=current_tick,
        )
        self._take_gold_from(player_id, order.total_gold)
        self._store.save(self._store.board().with_order(order))
        self._publish(
            player_id, kind="listed", side=MarketOrderSide.BUY, item_spec_id=spec_id,
            quantity=order.quantity, unit_price=order.unit_price_gold,
        )
        self._record(
            kind="listed", item_spec_id=spec_id, side=MarketOrderSide.BUY.value,
            quantity=order.quantity, unit_price=order.unit_price_gold,
            actor_name=self._name_of(MarketParticipant.player(player_id)),
            order_id=order.order_id.value,
            expires_at_tick=order.expires_at_tick,
        )
        return order

    def place_merchant_sell_order(
        self,
        *,
        merchant_id: int,
        item_spec_id: int,
        quantity: int,
        unit_price: int,
        current_tick: int,
        expires_in_ticks: Optional[int] = None,
    ) -> MarketOrder:
        """商人の売り注文を板へ置く (預けるものは無い — 世界の外から来る)。"""
        return self._place_merchant_order(
            side=MarketOrderSide.SELL,
            merchant_id=merchant_id,
            item_spec_id=item_spec_id,
            quantity=quantity,
            unit_price=unit_price,
            expires_in_ticks=expires_in_ticks,
            current_tick=current_tick,
        )

    def place_merchant_buy_order(
        self,
        *,
        merchant_id: int,
        item_spec_id: int,
        quantity: int,
        unit_price: int,
        current_tick: int,
        expires_in_ticks: Optional[int] = None,
    ) -> MarketOrder:
        """商人の買い注文を板へ置く (gold は無限なので預けない)。"""
        return self._place_merchant_order(
            side=MarketOrderSide.BUY,
            merchant_id=merchant_id,
            item_spec_id=item_spec_id,
            quantity=quantity,
            unit_price=unit_price,
            current_tick=current_tick,
            expires_in_ticks=expires_in_ticks,
        )

    # ── 約定 ────────────────────────────────────────────────────────────

    def take_order(
        self,
        player_id: PlayerId,
        *,
        order_id: MarketOrderId,
        quantity: int,
        current_tick: int,
    ) -> MarketSettlement:
        """板の注文を受ける。"""
        board = self._store.board()
        order = board.find(order_id)
        if order is not None:
            # 何かを動かす前に受けられるかを確かめる。板に無い注文はここを
            # 素通りさせ、下の taken に「その注文はありません」を投げさせる
            # (存在しない注文への失敗を 2 箇所で書かない)。
            self._require_can_take(player_id, order, quantity)

        after, trade = board.taken(
            order_id,
            by=MarketParticipant.player(player_id),
            quantity=quantity,
            at_tick=current_tick,
        )
        self._settle(board.find(order_id), trade, taker=player_id)
        self._store.save(after)
        self._publish(
            player_id, kind="bought", side=order.side, item_spec_id=trade.item_spec_id,
            quantity=trade.quantity, unit_price=trade.unit_price_gold,
            counterparty=trade.seller,
            # 売り手が板に居なくても「売れた」は届ける。届かないと、次に板へ
            # 寄るまで自分の持ち物が変わった理由が分からない。
            notify=trade.seller,
        )
        self._record(
            kind="settled", item_spec_id=trade.item_spec_id,
            quantity=trade.quantity, unit_price=trade.unit_price_gold,
            total_gold=trade.total_gold,
            seller_name=self._name_of(trade.seller),
            buyer_name=self._name_of(trade.buyer),
            # 値を決めたのがどちらかを読むために要る。売り注文が受けられたなら
            # 値は売り手が付けた値。
            taker_side=trade.taker_side.value,
            resting_order_id=trade.resting_order_id.value,
        )
        return MarketSettlement(
            trade=trade,
            seller_name=self._name_of(trade.seller),
            buyer_name=self._name_of(trade.buyer),
            item_name=self._item_display_name(trade.item_spec_id),
        )

    def buy_best(
        self,
        player_id: PlayerId,
        *,
        item_label: str,
        quantity: int,
        current_tick: int,
    ) -> MarketPurchase:
        """安い出品から順に買う。

        エージェントは注文を選ばない。**品と数だけを指定する**。表示が
        「18G で買える (出品 3件)」と集約されているので、どの注文を指すかを
        表示から組み立てられないため。実際の取引所の「最安を買う」と同じ形。

        自分の出品は飛ばす (自己約定の禁止がここで効く)。

        板の在庫が足りないときは**買えるだけ買う**。板の中身は他人の手番で
        変わるので、「あるだけ買う」が自然。逆に gold が足りないときは
        **1 つも買わずに断る** — 所持金は自分で見える自分の状態なので、
        足りないのは自分の計算違いで、黙って数を減らすと意図と違う買い物が
        成立する。
        """
        self._require_at_board(player_id)
        spec_id = self._item_spec_id_by_label(item_label)
        me = MarketParticipant.player(player_id)
        wanted = int(quantity)

        offers = [
            order
            for order in self._store.board().orders
            if order.item_spec_id == spec_id
            and order.side is MarketOrderSide.SELL
            and not order.is_awaiting_collection
        ]
        if not offers:
            raise MarketNothingToBuyError(item_name=self._item_display_name(spec_id))
        # **価格優先 → 時間優先。** 決めずに書くと engine が黙って選び、
        # 値の時系列に「なぜその注文が先に消えたか」の根拠が無くなる。
        #
        # 時間優先は `order_id` が板の中で単調に増えることに乗っている。
        # UUID や払い出しの変更は突き合わせの規則を変えることになるので、
        # `test_the_ids_only_ever_increase` が単調性そのものを見張る。
        #
        # **値を変えても順番は失わない。** 値を動かす人を後ろへ回すと
        # 「下げたのに順番で負けて売れない」が起き、値を下げても報われない
        # という読みを作る。この世界で見たいのは値が動くことなので、目的と
        # 逆を向く。代償として**先に雑な値で並んでおいて後から直す**のが
        # 有利になる — 板が厚くなったら見直す点。
        takeable = sorted(
            (o for o in offers if o.owner != me),
            key=lambda o: (o.unit_price_gold, o.order_id.value),
        )
        if not takeable:
            # 「誰も出していない」と分ける。次の一手が違う (待つ / 値を下げる)。
            raise MarketOnlyYourOwnListingError(
                item_name=self._item_display_name(spec_id),
            )

        plan = []
        remaining = wanted
        for order in takeable:
            if remaining <= 0:
                break
            take = min(remaining, order.quantity)
            plan.append((order.order_id, take))
            remaining -= take

        # 払えるかは**買う前に**、買う総額に対して確かめる。途中で足りなく
        # なると、半分だけ成立した状態が残る。
        self._require_gold(
            player_id,
            sum(
                self._store.board().find(order_id).unit_price_gold * take
                for order_id, take in plan
            ),
        )
        self._require_room(player_id, sum(take for _order_id, take in plan))

        settlements = [
            self.take_order(
                player_id, order_id=order_id, quantity=take, current_tick=current_tick,
            )
            for order_id, take in plan
        ]
        return MarketPurchase(
            item_spec_id=spec_id,
            item_name=self._item_display_name(spec_id),
            requested_quantity=wanted,
            settlements=tuple(settlements),
        )

    def find_my_order_price(
        self, player_id: PlayerId, *, item_label: str, side: MarketOrderSide,
    ) -> int:
        """自分の注文の、いまの単価を返す。

        値の付け直しの結果文と trace に**旧値と新値の両方**を載せるために要る。
        「下げた」という方向が読めないと、値動きが出来事にならない。
        """
        spec_id = self._item_spec_id_by_label(item_label)
        return self._my_order(
            player_id, spec_id, side, action="値を変える注文",
        ).unit_price_gold

    def sell_best(
        self,
        player_id: PlayerId,
        *,
        item_label: str,
        quantity: int,
        current_tick: int,
    ) -> MarketSale:
        """高い買い注文から順に売る。``buy_best`` の鏡像。

        **鏡像は 2 つに分かれる。** 「求めたとおりにできない」理由が両側にある
        ため。板が求めている数が少なければその数だけ、自分の持っている数が
        少なければ持っている数だけ売る。どちらも外から見えている値との食い違い
        ではないので、あるだけ応じる。

        買いの gold 不足だけ構えが違う (断る) のは、所持金が**自分で見えて
        いる自分の状態**だから (design_decisions #117)。
        """
        self._require_at_board(player_id)
        spec_id = self._item_spec_id_by_label(item_label)
        me = MarketParticipant.player(player_id)
        wanted = int(quantity)

        bids = [
            order
            for order in self._store.board().orders
            if order.item_spec_id == spec_id
            and order.side is MarketOrderSide.BUY
            and not order.is_awaiting_collection
        ]
        if not bids:
            raise MarketNothingToSellError(item_name=self._item_display_name(spec_id))
        takeable = sorted(
            (o for o in bids if o.owner != me),
            # 価格優先 → 時間優先。買う側と対称 (高い買い注文が先)。
            # 根拠は `buy_best` の並べ替えに書いてある。
            key=lambda o: (-o.unit_price_gold, o.order_id.value),
        )
        if not takeable:
            raise MarketOnlyYourOwnBidError(item_name=self._item_display_name(spec_id))

        owned = self._owned_counts(player_id).get(spec_id, 0)
        if owned <= 0:
            # 「売れるだけ売る」が 0 個になると、何も起きないのに成功と返る。
            raise MarketItemNotOwnedError(
                item_name=self._item_display_name(spec_id), quantity=wanted, owned=0,
            )

        plan = []
        remaining = min(wanted, owned)
        for order in takeable:
            if remaining <= 0:
                break
            take = min(remaining, order.quantity)
            plan.append((order.order_id, take))
            remaining -= take

        settlements = [
            self.take_order(
                player_id, order_id=order_id, quantity=take, current_tick=current_tick,
            )
            for order_id, take in plan
        ]
        return MarketSale(
            item_spec_id=spec_id,
            item_name=self._item_display_name(spec_id),
            requested_quantity=wanted,
            settlements=tuple(settlements),
        )

    def reprice_order(
        self,
        player_id: PlayerId,
        *,
        item_label: str,
        side: MarketOrderSide,
        new_unit_price: int,
    ) -> MarketOrder:
        """自分の注文の単価だけを変える。

        **品も gold も動かさないので、所持品が満杯でも打てる。** 取り下げは
        預けた品を引き取るため満杯だと断られ、「同じ品目・同じ向きは 1 件まで」
        と合わさって**値を変えられない**詰まりが生まれていた。値下げはこの実験で
        いちばん見たい行動なので、品を動かさずに打てる手を用意する。

        期限は動かさない。伸びると値下げが**期限の延命**に使え、板に居座り
        続ける注文を作れてしまう。
        """
        self._require_at_board(player_id)
        spec_id = self._item_spec_id_by_label(item_label)
        order = self._my_order(player_id, spec_id, side, action="値を変える注文")
        if side is MarketOrderSide.BUY:
            # **買い注文では gold が動く。** 預ける額が変わるため、売り注文の
            # 「品も gold も動かないので満杯でも打てる」はここには当てはまら
            # ない。値を上げるなら差額を預け、下げるなら余りを返す。
            delta = (int(new_unit_price) - order.unit_price_gold) * order.quantity
            if delta > 0:
                self._require_gold(player_id, delta)
                self._take_gold_from(player_id, delta)
            elif delta < 0:
                self._pay(MarketParticipant.player(player_id), -delta)
        repriced = order.repriced(int(new_unit_price))
        self._store.save(self._store.board().with_repriced(repriced))
        self._publish(
            player_id, kind="repriced", side=side, item_spec_id=spec_id,
            quantity=repriced.quantity, unit_price=repriced.unit_price_gold,
            old_unit_price=order.unit_price_gold,
        )
        self._record(
            kind="repriced", item_spec_id=spec_id, side=side.value,
            quantity=repriced.quantity, unit_price=repriced.unit_price_gold,
            old_unit_price=order.unit_price_gold,
            actor_name=self._name_of(MarketParticipant.player(player_id)),
            order_id=repriced.order_id.value,
        )
        return repriced

    # ── 取り下げ・期限切れ ──────────────────────────────────────────────

    def cancel_order(
        self, player_id: PlayerId, *, order_id: MarketOrderId,
    ) -> MarketOrder:
        """自分の注文を取り下げ、預けたものを引き取る。"""
        board = self._store.board()
        owner = MarketParticipant.player(player_id)
        # 板に無い注文・他人の注文はここで落ちる (預けたものを動かす前)。
        after = board.cancelled(order_id, by=owner)
        order = board.find(order_id)
        returned = self._return_deposit(order)
        if returned:
            self._publish(
                player_id, kind="cancelled", side=order.side,
                item_spec_id=order.item_spec_id,
                quantity=order.quantity, unit_price=order.unit_price_gold,
            )
            self._record(
                kind="cancelled", item_spec_id=order.item_spec_id,
                side=order.side.value,
                quantity=order.quantity, unit_price=order.unit_price_gold,
                actor_name=self._name_of(MarketParticipant.player(player_id)),
                order_id=order.order_id.value,
            )
        if not returned:
            # 引き取り待ちにするのは期限切れの話で、取り下げは本人の意思。
            # 受け取れないなら取り下げ自体を断る (板の状態を変えない)。
            raise MarketInventoryFullError(
                needed=order.quantity, free=self._free_slots(player_id),
            )
        self._store.save(after)
        return order

    def cancel_by(
        self, player_id: PlayerId, *, item_label: str, side: MarketOrderSide,
    ) -> MarketOrder:
        """品名と向きで、自分の注文を取り下げる。

        「同じ品目・同じ向きは 1 件まで」の制限があるので一意に決まる。
        番号で指す形は「表示に出ている名前をそのまま渡す」規約から外れる。
        """
        self._require_at_board(player_id)
        spec_id = self._item_spec_id_by_label(item_label)
        order = self._my_order(player_id, spec_id, side, action="取り下げる注文")
        return self.cancel_order(player_id, order_id=order.order_id)

    def expire_orders(self, *, current_tick: int) -> Tuple[MarketOrder, ...]:
        """期限を過ぎた注文を板から下げ、預けたものを持ち主へ返す。"""
        expired = self.expired_orders(current_tick=current_tick)
        completed = []
        for order in expired:
            result = self.expire_order(
                order_id=order.order_id,
                current_tick=current_tick,
            )
            if result is None:
                continue
            completed.append(result.order)
            self.observe_expiry(result)
        return tuple(completed)

    def expired_orders(self, *, current_tick: int) -> Tuple[MarketOrder, ...]:
        """期限を過ぎ、まだ引き取り待ちでない注文をID順で返す。"""
        return tuple(
            sorted(
                self._store.board().expired_orders(current_tick),
                key=lambda order: order.order_id.value,
            )
        )

    def expire_order(
        self,
        *,
        order_id: MarketOrderId,
        current_tick: int,
    ) -> Optional[MarketOrderExpiryResult]:
        """現在も期限切れである注文一件だけを返却・板更新する。"""
        board = self._store.board()
        order = board.find(order_id)
        if (
            order is None
            or order.is_awaiting_collection
            or not order.is_expired_at(current_tick)
        ):
            return None
        returned = self._return_deposit(order)
        if returned:
            board = board.cancelled(order.order_id, by=order.owner)
        else:
            # 返せないぶんは消さない。消すと預けた品が黙って世界から
            # 消える。板に残して、空きを作ってから引き取れるようにする。
            board = board.awaiting_collection(order.order_id)
        self._store.save(board)
        return MarketOrderExpiryResult(order=order, deposit_returned=returned)

    def observe_expiry(self, result: MarketOrderExpiryResult) -> None:
        """確定済み期限切れをtraceと当事者観測へ通知する。"""
        self._publish_expiry(result.order, kind=result.event_kind)

    # ── 内部 ────────────────────────────────────────────────────────────

    def _record(self, *, kind: str, item_spec_id: int, **payload: Any) -> None:
        # ``kind`` は recorder 自身の引数名なので、payload では
        # ``market_event`` に置き換える。同名で渡すと record() が TypeError に
        # なり、**行がまるごと消える** (action_result の予約名と同じ問題)。
        """板の動きを 1 行 trace へ残す。

        **品目ごとの (tick, 単価) を、1 種類の行から組み立てられる形にする。**
        run が終わったあとに値動きを読むのがこの実験の目的なので、ここが
        一次データになる。
        """
        if self._trace is None:
            return
        from ai_rpg_world.application.trace.events import TraceEventKind

        try:
            tick = int(self._now()) if self._now is not None else None
        except Exception:  # noqa: BLE001
            tick = None
        try:
            self._trace.record(
                TraceEventKind.MARKET_ACTIVITY,
                tick=tick,
                market_event=kind,
                item_spec_id=int(item_spec_id),
                item_name=self._item_display_name(item_spec_id),
                **payload,
            )
        except Exception:  # noqa: BLE001
            # 実験は止めない (trace は分析用で、世界の進行には要らない) が、
            # **黙って落とさない**。落ちたことが見えないと、run が終わってから
            # 「値動きが引けない」でしか気づけない。
            logger.warning(
                "市場の trace を記録できなかった: kind=%s item_spec_id=%s",
                kind, item_spec_id, exc_info=True,
            )

    def _publish(
        self,
        actor: PlayerId,
        *,
        kind: str,
        side: MarketOrderSide = MarketOrderSide.SELL,
        item_spec_id: int,
        quantity: int,
        unit_price: int,
        old_unit_price: Optional[int] = None,
        counterparty: Optional[MarketParticipant] = None,
        notify: Optional[MarketParticipant] = None,
    ) -> None:
        """板の上の 1 手を、世界の出来事として出す。

        ``notify`` は**その場に居なくても届けたい相手**。板越しの取引では
        売り手がその場に居ないまま自分の品が売れる。商人は世界の外の存在
        なので、届け先にはしない。
        """
        if self._events is None:
            return
        board_spot = getattr(self._store, "board_spot_id", None)
        if board_spot is None:
            return
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
            MarketBoardActivityEvent,
        )
        from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

        def _entity(participant: Optional[MarketParticipant]):
            if participant is None or participant.is_merchant:
                return None
            return EntityId.create(int(participant.player_id))

        if self._graph is None:
            return
        graph = self._graph.find_graph()
        self._events.publish_all(
            [
                MarketBoardActivityEvent.create(
                    aggregate_id=graph.graph_id,
                    aggregate_type="SpotGraphAggregate",
                    entity_id=EntityId.create(int(actor)),
                    spot_id=board_spot,
                    kind=kind,
                    side=side.value,
                    item_name=self._item_display_name(item_spec_id),
                    quantity=int(quantity),
                    unit_price=int(unit_price),
                    old_unit_price=old_unit_price,
                    counterparty_entity_id=_entity(counterparty),
                    notify_entity_id=_entity(notify),
                )
            ]
        )

    def _publish_expiry(self, order: MarketOrder, *, kind: str) -> None:
        """流れた注文を持ち主へ知らせる。

        板から離れた場所に居ると、自分の出品が流れたことを知る手段が無い。
        次に板へ寄るまで、預けた品は板の上にあり所持品からは消えたままになる。
        商人の注文は知らせる相手が居ない。
        """
        # trace は商人の注文も残す。板が痩せていく理由を読むのに、誰の注文
        # だったかは関係ない。
        self._record(
            kind="expired", item_spec_id=order.item_spec_id, side=order.side.value,
            quantity=order.quantity, unit_price=order.unit_price_gold,
            actor_name=self._name_of(order.owner),
            order_id=order.order_id.value,
            collected=(kind == "expired_returned"),
        )
        if order.owner.is_merchant:
            return
        self._publish(
            order.owner.player_id, kind=kind, side=order.side,
            item_spec_id=order.item_spec_id,
            quantity=order.quantity, unit_price=order.unit_price_gold,
            notify=order.owner,
        )

    def _place_merchant_order(
        self,
        *,
        side: MarketOrderSide,
        merchant_id: int,
        item_spec_id: int,
        quantity: int,
        unit_price: int,
        current_tick: int,
        expires_in_ticks: Optional[int] = None,
    ) -> MarketOrder:
        order = self._new_order(
            side=side,
            owner=MarketParticipant.merchant(merchant_id),
            item_spec_id=item_spec_id,
            quantity=quantity,
            unit_price=unit_price,
            current_tick=current_tick,
            expires_in_ticks=expires_in_ticks,
        )
        self._store.save(self._store.board().with_order(order))
        return order

    def _new_order(
        self,
        *,
        side: MarketOrderSide,
        owner: MarketParticipant,
        item_spec_id: int,
        quantity: int,
        unit_price: int,
        current_tick: int,
        expires_in_ticks: Optional[int] = None,
    ) -> MarketOrder:
        """注文を 1 件作る。

        寿命は**注文ごとの宣言 → 板ぜんたいの既定**の順に決まる。既定を
        書き換えて長くすると、人が出す注文の寿命まで動いてしまい、run を
        跨いだ比較が切れる。
        """
        return MarketOrder.create(
            order_id=self._store.next_order_id(),
            side=side,
            owner=owner,
            item_spec_id=int(item_spec_id),
            quantity=int(quantity),
            unit_price_gold=int(unit_price),
            listed_at_tick=int(current_tick),
            expires_in_ticks=(
                self._expires_in_ticks
                if expires_in_ticks is None
                else int(expires_in_ticks)
            ),
        )

    def _require_can_take(
        self, taker: PlayerId, order: MarketOrder, quantity: int,
    ) -> None:
        """受ける側が本当に受けられるかを、何かを動かす前に確かめる。"""
        if order.side is MarketOrderSide.SELL:
            # 売り注文を受ける = 買う。代金を払い、品を受け取る。
            self._require_gold(taker, order.unit_price_gold * int(quantity))
            self._require_room(taker, int(quantity))
        else:
            # 買い注文を受ける = 売る。品を渡し、板の gold を受け取る。
            self._require_holds(taker, order.item_spec_id, int(quantity))

    def _settle(
        self, order: MarketOrder, trade: MarketTrade, *, taker: PlayerId,
    ) -> None:
        """約定した内容どおりに、品と gold を動かす。

        板に預けてあるぶんは**もう誰の持ち物でもない**ので、板側から動かす。
        預けた人からもう一度引くと二重に取ることになる。
        """
        spec_ids = tuple(
            ItemSpecId.create(trade.item_spec_id) for _ in range(trade.quantity)
        )
        if order.side is MarketOrderSide.SELL:
            # 品は板から買い手へ。gold は買い手から売り手へ。
            self._give_items_to(taker, spec_ids)
            self._take_gold_from(taker, trade.total_gold)
            self._pay(trade.seller, trade.total_gold)
        else:
            # 品は売り手から買い手へ。gold は板から売り手へ。
            self._take_items_from(taker, trade.item_spec_id, trade.quantity)
            self._deliver_items(trade.buyer, spec_ids)
            self._pay(trade.seller, trade.total_gold)

    def _return_deposit(self, order: MarketOrder) -> bool:
        """板が預かっているものを持ち主へ返す。返せたら True。

        商人の注文は預かっていないので、返すものが無い (True)。
        """
        if order.owner.is_merchant or order.quantity <= 0:
            return True
        player_id = order.owner.player_id
        if order.side is MarketOrderSide.BUY:
            self._pay(order.owner, order.total_gold)
            return True
        if self._free_slots(player_id) < order.quantity:
            return False
        self._give_items_to(
            player_id,
            tuple(
                ItemSpecId.create(order.item_spec_id) for _ in range(order.quantity)
            ),
        )
        return True

    def _deliver_items(
        self, participant: MarketParticipant, spec_ids: Tuple[ItemSpecId, ...],
    ) -> None:
        """買い手へ品を渡す。商人が買い手なら、品は世界から消える。"""
        if participant.is_merchant:
            # 商人は世界の外との出入り口なので、受け取った品はどこにも入らない。
            # 在庫へ入れると「商人を経由した転売」が最短の稼ぎ方になる。
            return
        # **買い手はその場に居るとは限らない。** 受け取れなければ板の足元へ
        # 置き、本人に知らせる (事前拒否は使えない — 売る側から相手の所持品は
        # 見えないので、打つ前に避けようがない)。
        grant_item_specs_to_inventory(
            participant.player_id, spec_ids, self._items, self._item_specs,
            self._inventories,
            overflow_sink=self._delivery_overflow_sink or self._overflow_sink,
        )

    def _pay(self, participant: MarketParticipant, gold: int) -> None:
        """売り手へ代金を渡す。商人が売り手なら、gold は世界から消える。"""
        if participant.is_merchant or gold <= 0:
            return
        status = self._statuses.find_by_id(participant.player_id)
        status.earn_gold(gold)
        self._statuses.save(status)

    def _give_items_to(
        self, player_id: PlayerId, spec_ids: Tuple[ItemSpecId, ...],
    ) -> None:
        grant_item_specs_to_inventory(
            player_id, spec_ids, self._items, self._item_specs, self._inventories,
            overflow_sink=self._overflow_sink,
        )

    def _take_items_from(
        self, player_id: PlayerId, item_spec_id: int, quantity: int,
    ) -> None:
        inventory = self._inventories.find_by_id(player_id)
        spec_ids = tuple(
            ItemSpecId.create(item_spec_id) for _ in range(int(quantity))
        )
        remove_items_of_specs_from_inventory(inventory, spec_ids, self._items)
        self._inventories.save(inventory)

    def _take_gold_from(self, player_id: PlayerId, gold: int) -> None:
        if gold <= 0:
            return
        status = self._statuses.find_by_id(player_id)
        status.pay_gold(gold)
        self._statuses.save(status)

    def _my_order(
        self,
        player_id: PlayerId,
        item_spec_id: int,
        side: MarketOrderSide,
        *,
        action: str,
    ) -> MarketOrder:
        """その人の、その品目・その向きの注文を 1 件返す。

        引き取り待ちは板の商品ではないので対象にしない (値を変えても意味が
        無く、取り下げは `market_cancel` の別経路で引き取る)。
        """
        owner = MarketParticipant.player(player_id)
        for order in self._store.board().orders:
            if (
                order.owner == owner
                and order.item_spec_id == int(item_spec_id)
                and order.side is side
                and not order.is_awaiting_collection
            ):
                return order
        raise MarketNoSuchOrderError(
            item_name=self._item_display_name(item_spec_id), action=action,
        )

    def _require_at_board(self, player_id: PlayerId) -> None:
        """板と同席していることを確かめる。

        露出判断では見ない。ツールを出したり消したりすると、エージェントから
        見て世界の可能性が揺れる。商人の `MERCHANT_NOT_AT_SPOT` と同じく、
        実行時の失敗として返す。
        """
        if self._reach.is_global:
            # 届く世界では板の前に立つ必要が無い。**板の在り処は残っている** —
            # 受け取れなかった品はそこへ置かれる。
            return
        board_spot = getattr(self._store, "board_spot_id", None)
        if board_spot is None or self._graph is None:
            return
        from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

        graph = self._graph.find_graph()
        try:
            here = graph.get_entity_spot(EntityId.create(int(player_id)))
        except Exception as exc:  # noqa: BLE001
            raise MarketBoardNotHereError() from exc
        if here != board_spot:
            raise MarketBoardNotHereError()

    def _require_no_order_yet(
        self, player_id: PlayerId, item_spec_id: int, side: MarketOrderSide,
    ) -> None:
        """同じ品目・同じ向きの自分の注文が、まだ板に無いことを確かめる。

        **不変条件であって、ツールの都合ではない。** 2 件あると取り下げ・値の
        付け直しが「品目 + 向き」でどちらを指すのか決まらず、板の状態そのものが
        壊れる。番号で指す形は「表示に出ている名前をそのまま渡す」規約から
        外れるので採らない。

        引き取り待ちも 1 件に数える。数えないと、引き取り待ちの注文が残った
        まま同じ品目を出し直せてしまい、同じ曖昧さが生まれる。断り文は分ける
        — 「取り下げる / 値を変える」と「先に引き取る」では次の一手が違う。
        """
        owner = MarketParticipant.player(player_id)
        for order in self._store.board().orders:
            if order.owner != owner or order.item_spec_id != int(item_spec_id):
                continue
            if order.side is not side:
                continue
            if order.is_awaiting_collection:
                raise MarketOrderAwaitingCollectionError(
                    item_name=self._item_display_name(item_spec_id),
                )
            raise MarketDuplicateOrderError(
                item_name=self._item_display_name(item_spec_id),
                action="売り注文" if side is MarketOrderSide.SELL else "買い注文",
            )

    def _require_holds(
        self, player_id: PlayerId, item_spec_id: int, quantity: int,
    ) -> None:
        owned = self._owned_counts(player_id).get(int(item_spec_id), 0)
        if owned < int(quantity):
            raise MarketItemNotOwnedError(
                item_name=self._item_display_name(item_spec_id),
                quantity=int(quantity),
                owned=owned,
            )

    def _require_gold(self, player_id: PlayerId, gold: int) -> None:
        available = self._gold_of(player_id)
        if available < gold:
            raise MarketGoldNotEnoughError(needed=gold, available=available)

    def _require_room(self, player_id: PlayerId, quantity: int) -> None:
        free = self._free_slots(player_id)
        if free < quantity:
            raise MarketInventoryFullError(needed=quantity, free=free)

    def _free_slots(self, player_id: PlayerId) -> int:
        inventory = self._inventories.find_by_id(player_id)
        if inventory is None:
            return 0
        summary = inventory.get_inventory_summary()
        return int(summary["empty_inventory_slots"])

    def _gold_of(self, player_id: PlayerId) -> int:
        status = self._statuses.find_by_id(player_id)
        return int(status.gold.value) if status is not None else 0

    def _owned_counts(self, player_id: PlayerId) -> Dict[int, int]:
        inventory = self._inventories.find_by_id(player_id)
        if inventory is None:
            return {}
        counts = count_owned_item_instances_by_spec(inventory, self._items)
        return {spec.value: count for spec, count in counts.items()}

    def _item_spec_id_by_label(self, label: str) -> int:
        spec = self._item_specs.find_by_name(str(label))
        if spec is None:
            raise MarketUnknownItemError(item_label=str(label))
        return spec.item_spec_id.value

    def _item_display_name(self, item_spec_id: int) -> str:
        if self._item_name is None:
            return "その品"
        try:
            return self._item_name(item_spec_id) or "その品"
        except Exception:  # noqa: BLE001
            return "その品"

    def _name_of(self, participant: MarketParticipant) -> str:
        if participant.is_merchant:
            return "商人"
        if self._entity_name is None:
            return "誰か"
        try:
            return self._entity_name(participant.entity_id) or "誰か"
        except Exception:  # noqa: BLE001
            return "誰か"


__all__ = [
    "MARKET_GOLD_SOURCE",
    "DEFAULT_ORDER_EXPIRES_IN_TICKS",
    "MarketDuplicateOrderError",
    "MarketBoardNotHereError",
    "MarketException",
    "MarketGoldNotEnoughError",
    "MarketInventoryFullError",
    "MarketItemNotOwnedError",
    "MarketNoSuchOrderError",
    "MarketNothingToBuyError",
    "MarketNothingToSellError",
    "MarketOnlyYourOwnBidError",
    "MarketOnlyYourOwnListingError",
    "MarketOrderAwaitingCollectionError",
    "MarketOrderExpiryResult",
    "MarketPurchase",
    "MarketSale",
    "MarketService",
    "MarketSettlement",
    "MarketUnknownItemError",
]
