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


@dataclass(frozen=True)
class MarketSettlement:
    """成立した約定 1 件。trace と観測はここから作る。"""

    trade: MarketTrade
    seller_name: str
    buyer_name: str
    item_name: str


class MarketService:
    """板の注文の受付・約定・取り下げ・期限切れを実行する。"""

    def __init__(
        self,
        *,
        market_board_store: Any,
        player_inventory_repository: Any,
        player_status_repository: Any,
        item_repository: Any,
        item_spec_repository: Any,
        item_spec_name_resolver: Optional[Any] = None,
        entity_name_resolver: Optional[Any] = None,
        expires_in_ticks: int = DEFAULT_ORDER_EXPIRES_IN_TICKS,
    ) -> None:
        self._store = market_board_store
        self._inventories = player_inventory_repository
        self._statuses = player_status_repository
        self._items = item_repository
        self._item_specs = item_spec_repository
        self._item_name = item_spec_name_resolver
        self._entity_name = entity_name_resolver
        self._expires_in_ticks = expires_in_ticks

    # ── 参照 ────────────────────────────────────────────────────────────

    def board(self) -> MarketBoard:
        return self._store.board()

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
        return order

    def place_merchant_sell_order(
        self,
        *,
        merchant_id: int,
        item_spec_id: int,
        quantity: int,
        unit_price: int,
        current_tick: int,
    ) -> MarketOrder:
        """商人の売り注文を板へ置く (預けるものは無い — 世界の外から来る)。"""
        return self._place_merchant_order(
            side=MarketOrderSide.SELL,
            merchant_id=merchant_id,
            item_spec_id=item_spec_id,
            quantity=quantity,
            unit_price=unit_price,
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
    ) -> MarketOrder:
        """商人の買い注文を板へ置く (gold は無限なので預けない)。"""
        return self._place_merchant_order(
            side=MarketOrderSide.BUY,
            merchant_id=merchant_id,
            item_spec_id=item_spec_id,
            quantity=quantity,
            unit_price=unit_price,
            current_tick=current_tick,
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
        return MarketSettlement(
            trade=trade,
            seller_name=self._name_of(trade.seller),
            buyer_name=self._name_of(trade.buyer),
            item_name=self._item_display_name(trade.item_spec_id),
        )

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
        if not returned:
            # 引き取り待ちにするのは期限切れの話で、取り下げは本人の意思。
            # 受け取れないなら取り下げ自体を断る (板の状態を変えない)。
            raise MarketInventoryFullError(
                needed=order.quantity, free=self._free_slots(player_id),
            )
        self._store.save(after)
        return order

    def expire_orders(self, *, current_tick: int) -> Tuple[MarketOrder, ...]:
        """期限を過ぎた注文を板から下げ、預けたものを持ち主へ返す。"""
        board = self._store.board()
        expired = board.expired_orders(current_tick)
        for order in expired:
            if self._return_deposit(order):
                board = board.cancelled(order.order_id, by=order.owner)
            else:
                # 返せないぶんは消さない。消すと預けた品が黙って世界から
                # 消える。板に残して、空きを作ってから引き取れるようにする。
                board = board.awaiting_collection(order.order_id)
        self._store.save(board)
        return expired

    # ── 内部 ────────────────────────────────────────────────────────────

    def _place_merchant_order(
        self,
        *,
        side: MarketOrderSide,
        merchant_id: int,
        item_spec_id: int,
        quantity: int,
        unit_price: int,
        current_tick: int,
    ) -> MarketOrder:
        order = self._new_order(
            side=side,
            owner=MarketParticipant.merchant(merchant_id),
            item_spec_id=item_spec_id,
            quantity=quantity,
            unit_price=unit_price,
            current_tick=current_tick,
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
    ) -> MarketOrder:
        return MarketOrder.create(
            order_id=self._store.next_order_id(),
            side=side,
            owner=owner,
            item_spec_id=int(item_spec_id),
            quantity=int(quantity),
            unit_price_gold=int(unit_price),
            listed_at_tick=int(current_tick),
            expires_in_ticks=self._expires_in_ticks,
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
        self._give_items_to(participant.player_id, spec_ids)

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
    "MarketException",
    "MarketGoldNotEnoughError",
    "MarketInventoryFullError",
    "MarketItemNotOwnedError",
    "MarketOrderAwaitingCollectionError",
    "MarketService",
    "MarketSettlement",
    "MarketUnknownItemError",
]
