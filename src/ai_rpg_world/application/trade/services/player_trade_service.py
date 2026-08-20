"""同席したエージェント同士の取引を成立させる (経済統合 Phase 2)。

## 誰が何を確かめるか

- **持ちかける側 (offerer)**: 差し出すものを持っているかを提案の時点で確かめ、
  確かめたうえで凍結する。凍結してあるので、承諾の瞬間に「もう無い」は起きない
- **受ける側 (target)**: 求められたものを持っているかは**承諾の瞬間**に確かめる。
  こちらは凍結できない (提案された時点で相手の持ち物を押さえる筋合いが無い)

承諾に失敗しても提案は残す。消すと offerer は理由を知らないまま凍結が解け、
target は集め直しても受けられない。「あと N 個足りない」を返して、集めてから
受け直せるようにする。

## 失敗は原因ごとに分ける

次の一手が違うものを同じコードに畳まない (#105 と同じ判断)。相手が居ない
(移動する) / 持っていない (集める) / 相手の持ち物が足りない (待つか諦める) /
自分宛ての申し出が無い (待つ) は、それぞれ別の失敗にする。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence, Tuple

from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
    remove_items_of_specs_from_inventory,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.aggregate.pending_trade_offer import PendingTradeOffer
from ai_rpg_world.domain.trade.value_object.trade_side import TradeSide
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

#: gold の増減 trace で使う出所。商人との売買 (merchant_buy / merchant_sell) と
#: 並ぶ 3 つ目の源泉。
TRADE_GOLD_SOURCE = "trade_settle"


class PlayerTradeException(Exception):
    """人同士の取引が成立しなかった。"""

    error_code = "PLAYER_TRADE_FAILED"


class TradePartnerNotHereError(PlayerTradeException):
    error_code = "TRADE_PARTNER_NOT_HERE"

    def __init__(self, *, partner_name: str = "その相手") -> None:
        super().__init__(
            f"{partner_name}はこの場所に居ません。"
            "取引は同じ場所に居るときだけ持ちかけられます。"
        )


class TradeItemNotOwnedError(PlayerTradeException):
    error_code = "TRADE_ITEM_NOT_OWNED"

    def __init__(self, *, item_name: str, quantity: int, owned: int) -> None:
        super().__init__(
            f"{item_name}を{quantity}つ差し出そうとしましたが、"
            f"いま出せるのは{owned}つです。"
        )


class TradeGoldNotEnoughError(PlayerTradeException):
    error_code = "TRADE_GOLD_NOT_ENOUGH"

    def __init__(self, *, needed: int, available: int) -> None:
        super().__init__(
            f"{needed}G を差し出そうとしましたが、いま使えるのは{available}G です。"
        )


class TradeUnknownItemError(PlayerTradeException):
    error_code = "TRADE_UNKNOWN_ITEM"

    def __init__(self, *, item_label: str) -> None:
        super().__init__(
            f"この世界に「{item_label}」という品はありません。名前を確かめてください。"
        )


class TradeDuplicateOfferError(PlayerTradeException):
    error_code = "TRADE_DUPLICATE_OFFER"

    def __init__(self, *, partner_name: str) -> None:
        super().__init__(
            f"{partner_name}へは既に取引を持ちかけています。"
            "返事を待つか、流れるのを待ってください。"
        )


class NoOfferForYouError(PlayerTradeException):
    error_code = "TRADE_NO_OFFER_FOR_YOU"

    def __init__(self) -> None:
        super().__init__(
            "あなたに持ちかけられている取引はありません。"
            "誰かが持ちかけるのを待ってください。"
        )


class AmbiguousOfferError(PlayerTradeException):
    error_code = "TRADE_OFFER_AMBIGUOUS"

    def __init__(self, *, offerer_names: Sequence[str]) -> None:
        listed = "、".join(offerer_names)
        super().__init__(
            f"あなたに持ちかけられている取引が複数あります ({listed})。"
            "offerer_player_label で誰の申し出かを指定してください。"
        )


class TradeAskNotMetError(PlayerTradeException):
    error_code = "TRADE_ASK_NOT_MET"

    def __init__(self, *, missing: str) -> None:
        super().__init__(
            f"求められているものが足りません ({missing})。"
            "集めてから受け直せます (申し出は残っています)。"
        )


class TradeSelfInventoryFullError(PlayerTradeException):
    """受ける側の手が塞がっていて、差し出されたものを受け取れない。

    `acquire_item` は満杯だと**黙って品を捨てる**ので、確かめずに渡すと
    「品が消えて gold だけ動く」形になる。受ける側は自分で空けられるので、
    次の一手 (何か置く / 使う) を返して断る。
    """

    error_code = "TRADE_SELF_INVENTORY_FULL"

    def __init__(self, *, needed: int, free: int) -> None:
        super().__init__(
            f"受け取るのに{needed}つぶんの空きが要りますが、空いているのは{free}つです。"
            "drop_item で何かを手放すか、使ってから受け直してください "
            "(申し出は残っています)。"
        )


class TradeReceiverInventoryFullError(PlayerTradeException):
    """持ちかけた側の手が塞がっていて、求めたものを受け取れない。

    受ける側には直せない事情なので、自分の空き不足とは別の失敗にする
    (give_item が「相手の手が塞がっている」を別に返すのと同じ形)。
    """

    error_code = "TRADE_PARTNER_INVENTORY_FULL"

    def __init__(self, *, partner_name: str, needed: int, free: int) -> None:
        super().__init__(
            f"{partner_name}の手が塞がっていて、求められたものを受け取れません "
            f"({needed}つぶんの空きが要りますが、空いているのは{free}つです)。"
            f"{partner_name}が何かを手放すのを待つか、この取引は諦めてください。"
        )


@dataclass(frozen=True)
class TradeSettlement:
    """成立した取引 1 件。trace と観測はここから作る。"""

    offer: PendingTradeOffer
    offerer_name: str
    target_name: str
    #: 受けた側から見た gold の増減。
    target_gold_delta: int


class PlayerTradeService:
    """提案の作成・承諾・辞退を実行する。"""

    def __init__(
        self,
        *,
        pending_trade_offer_store: Any,
        trade_freeze_service: Any,
        spot_graph_repository: Any,
        player_inventory_repository: Any,
        player_status_repository: Any,
        item_repository: Any,
        item_spec_repository: Any,
        item_spec_name_resolver: Optional[Any] = None,
        entity_name_resolver: Optional[Any] = None,
        event_publisher: Optional[Any] = None,
        expires_in_ticks: int = 10,
        overflow_sink: Any = None,
    ) -> None:
        self._offers = pending_trade_offer_store
        self._freeze = trade_freeze_service
        self._graph = spot_graph_repository
        self._inventories = player_inventory_repository
        self._statuses = player_status_repository
        self._items = item_repository
        self._item_specs = item_spec_repository
        self._item_name = item_spec_name_resolver
        self._entity_name = entity_name_resolver
        self._events = event_publisher
        self._expires_in_ticks = expires_in_ticks
        self._overflow_sink = overflow_sink

    def set_event_publisher(self, event_publisher: Any) -> None:
        """観測を出す先を後付けで注入する。

        publisher は runtime を組み終えてからしか作れないので、merchant 側と
        同じく setter で後付けする。注入前は観測が出ない — 交渉が誰にも
        見えない状態なので、配線漏れは第三者観測のテストで落ちる。
        """
        self._events = event_publisher

    # ── 提案 ────────────────────────────────────────────────────────────

    def offer(
        self,
        offerer: PlayerId,
        *,
        target: PlayerId,
        gives_items: Sequence[Dict[str, Any]],
        gives_gold: int,
        asks_item_labels: Sequence[Dict[str, Any]],
        asks_gold: int,
        current_tick: int,
    ) -> PendingTradeOffer:
        """交換を持ちかける。差し出すものはこの時点で凍結する。"""
        self._require_same_spot(offerer, target)
        if self._offers.has_offer_between(offerer, target):
            raise TradeDuplicateOfferError(partner_name=self._name_of(target))

        gives = TradeSide(
            items=tuple(
                (int(entry["item_spec_id"]), int(entry["quantity"]))
                for entry in gives_items
            ),
            gold=int(gives_gold),
        )
        asks = TradeSide(
            items=tuple(
                (self._item_spec_id_by_label(entry["item_label"]), int(entry["quantity"]))
                for entry in asks_item_labels
            ),
            gold=int(asks_gold),
        )
        self._require_can_offer(offerer, gives)

        offer = PendingTradeOffer.create(
            offer_id=self._offers.next_offer_id(),
            offerer_player_id=offerer,
            target_player_id=target,
            gives=gives,
            asks=asks,
            created_tick=int(current_tick),
            expires_in_ticks=self._expires_in_ticks,
        )
        self._offers.put(offer)
        self._freeze.freeze_offer(offer)
        self._publish(offer, kind="offered", actor=offerer)
        return offer

    # ── 返事 ────────────────────────────────────────────────────────────

    def accept(
        self, target: PlayerId, *, offerer: Optional[PlayerId] = None,
    ) -> TradeSettlement:
        """持ちかけられた取引を受け、その場で交換する。"""
        offer = self._offer_for(target, offerer)
        self._require_same_spot(offer.offerer_player_id, offer.target_player_id)
        self._require_can_meet_asks(target, offer.asks)
        self._require_room_on_both_sides(offer)

        # 差し出す側の凍結を解いてから動かす。凍結したままだと、除去の計画が
        # 予約品を避けてしまって「持っているのに渡せない」になる。
        self._freeze.release_offer(offer)
        # **両側の除去を先に済ませてから渡す。** 片側ずつ「抜いて渡す」を
        # 順にやると、渡すぶんで空くはずの枠がまだ空いておらず、釣り合った
        # 交換 (1 つ出して 1 つ受け取る) が満杯で通らなくなる。
        self._take_items(offer.gives, offer.offerer_player_id)
        self._take_items(offer.asks, offer.target_player_id)
        self._move_gold(offer.gives, offer.offerer_player_id, offer.target_player_id)
        self._move_gold(offer.asks, offer.target_player_id, offer.offerer_player_id)
        self._deliver_items(offer.gives, offer.target_player_id)
        self._deliver_items(offer.asks, offer.offerer_player_id)
        self._offers.put(offer.accept())
        self._publish(offer, kind="accepted", actor=target)
        return TradeSettlement(
            offer=offer,
            offerer_name=self._name_of(offer.offerer_player_id),
            target_name=self._name_of(offer.target_player_id),
            target_gold_delta=offer.gives.gold - offer.asks.gold,
        )

    def decline(
        self, target: PlayerId, *, offerer: Optional[PlayerId] = None,
    ) -> PendingTradeOffer:
        """持ちかけられた取引を断る。相手の凍結はここで解ける。"""
        offer = self._offer_for(target, offerer)
        self._freeze.release_offer(offer)
        self._offers.put(offer.decline())
        self._publish(offer, kind="declined", actor=target)
        return offer

    # ── 内部 ────────────────────────────────────────────────────────────

    def _offer_for(
        self, target: PlayerId, offerer: Optional[PlayerId],
    ) -> PendingTradeOffer:
        candidates = self._offers.list_for_target(target)
        if not candidates:
            raise NoOfferForYouError()
        if offerer is not None:
            for offer in candidates:
                if offer.offerer_player_id == offerer:
                    return offer
            raise NoOfferForYouError()
        if len(candidates) > 1:
            raise AmbiguousOfferError(
                offerer_names=[
                    self._name_of(offer.offerer_player_id) for offer in candidates
                ]
            )
        return candidates[0]

    def _publish(
        self, offer: PendingTradeOffer, *, kind: str, actor: PlayerId,
    ) -> None:
        """交渉の 1 手を世界の出来事として出す。

        ``actor`` はその手を打った人 (持ちかけた人 / 返事をした人)。知覚の
        遮断は ``entity_id`` で効くので、ここを取り違えると幽霊の行動が生者へ
        漏れる。配信先 (第三者に見せるか当事者だけか) は kind ごとに
        recipient strategy が決める。
        """
        if self._events is None:
            return
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
            PlayerTradeOfferEvent,
        )

        partner = (
            offer.target_player_id
            if actor == offer.offerer_player_id
            else offer.offerer_player_id
        )
        graph = self._graph.find_graph()
        try:
            spot_id = graph.get_entity_spot(EntityId.create(int(actor)))
        except Exception:  # noqa: BLE001
            return
        self._events.publish_all(
            [
                PlayerTradeOfferEvent.create(
                    aggregate_id=graph.graph_id,
                    aggregate_type="SpotGraphAggregate",
                    entity_id=EntityId.create(int(actor)),
                    partner_entity_id=EntityId.create(int(partner)),
                    offerer_entity_id=EntityId.create(int(offer.offerer_player_id)),
                    spot_id=spot_id,
                    kind=kind,
                    gives_text=self._describe(offer.gives),
                    asks_text=self._describe(offer.asks),
                )
            ]
        )

    def _describe(self, side: TradeSide) -> str:
        """片側の中身を、観測の文面に載る短い日本語にする。"""
        parts = [
            f"{self._item_display_name(spec_id)} {quantity}つ"
            for spec_id, quantity in side.items
        ]
        if side.gold:
            parts.append(f"{side.gold}G")
        return "と".join(parts) if parts else "何も"

    def _require_same_spot(self, a: PlayerId, b: PlayerId) -> None:
        graph = self._graph.find_graph()
        try:
            spot_a = graph.get_entity_spot(EntityId.create(int(a)))
            spot_b = graph.get_entity_spot(EntityId.create(int(b)))
        except Exception as exc:  # noqa: BLE001
            raise TradePartnerNotHereError(partner_name=self._name_of(b)) from exc
        if spot_a != spot_b:
            raise TradePartnerNotHereError(partner_name=self._name_of(b))

    def _require_can_offer(self, offerer: PlayerId, gives: TradeSide) -> None:
        """差し出すものを本当に出せるかを、凍結する前に確かめる。"""
        if gives.gold:
            available = self._freeze.available_gold(offerer)
            if available < gives.gold:
                raise TradeGoldNotEnoughError(
                    needed=gives.gold, available=available,
                )
        # 品は数え上げの時点で凍結ぶんが除かれている
        # (count_owned_item_instances_by_spec が予約済みの instance を飛ばす)。
        # ここで凍結量をもう一度引くと二重に引くことになり、いまは
        # max(0, ...) が負の値を隠すので気付けない。
        counts = self._owned_counts(offerer)
        for spec_id, quantity in gives.items:
            available = counts.get(spec_id, 0)
            if available < quantity:
                raise TradeItemNotOwnedError(
                    item_name=self._item_display_name(spec_id),
                    quantity=quantity,
                    owned=available,
                )

    def _require_can_meet_asks(self, target: PlayerId, asks: TradeSide) -> None:
        """受ける側が求められたものを出せるかを、承諾の瞬間に確かめる。"""
        missing = []
        if asks.gold:
            available = self._freeze.available_gold(target)
            if available < asks.gold:
                missing.append(f"{asks.gold - available}G")
        # 差し出す側と同じ理由で、ここでも凍結量は引かない。
        counts = self._owned_counts(target)
        for spec_id, quantity in asks.items:
            available = counts.get(spec_id, 0)
            if available < quantity:
                name = self._item_display_name(spec_id)
                missing.append(f"{name} あと {quantity - available} つ")
        if missing:
            raise TradeAskNotMetError(missing="、".join(missing))

    def _require_room_on_both_sides(self, offer: PendingTradeOffer) -> None:
        """両側が受け取りきれることを、何かを動かす前に確かめる。

        `acquire_item` は満杯だと**黙って品を捨てる**ので、確かめずに渡すと
        「品が消えて gold だけ動く」形になり、当事者の誰にも見えない。

        空きは「いまの空き + 自分が渡すぶん」で数える。渡した枠は空くので、
        釣り合った交換は満杯でも成立する。ここを「いまの空き」だけで見ると、
        事故を塞いだつもりで**普通の 1 対 1 交換を塞ぐ**。
        """
        target = offer.target_player_id
        offerer = offer.offerer_player_id
        for receiver, incoming, outgoing, is_offerer in (
            (target, offer.gives, offer.asks, False),
            (offerer, offer.asks, offer.gives, True),
        ):
            needed = _item_count(incoming)
            if needed <= 0:
                continue
            room = self._free_slots(receiver) + _item_count(outgoing)
            if room >= needed:
                continue
            if is_offerer:
                raise TradeReceiverInventoryFullError(
                    partner_name=self._name_of(offerer), needed=needed, free=room,
                )
            raise TradeSelfInventoryFullError(needed=needed, free=room)

    def _free_slots(self, player_id: PlayerId) -> int:
        inventory = self._inventories.find_by_id(player_id)
        if inventory is None:
            return 0
        return int(inventory.get_inventory_summary()["empty_inventory_slots"])

    def _move_gold(self, side: TradeSide, giver: PlayerId, receiver: PlayerId) -> None:
        if not side.gold:
            return
        giver_status = self._statuses.find_by_id(giver)
        receiver_status = self._statuses.find_by_id(receiver)
        giver_status.pay_gold(side.gold)
        receiver_status.earn_gold(side.gold)
        self._statuses.save(giver_status)
        self._statuses.save(receiver_status)

    def _take_items(self, side: TradeSide, giver: PlayerId) -> None:
        """片側の品を、渡す人の所持品から抜く。"""
        spec_ids = _spec_ids_of(side)
        if not spec_ids:
            return
        inventory = self._inventories.find_by_id(giver)
        remove_items_of_specs_from_inventory(inventory, spec_ids, self._items)
        self._inventories.save(inventory)

    def _deliver_items(self, side: TradeSide, receiver: PlayerId) -> None:
        """片側の品を、受け取る人の所持品へ入れる。"""
        spec_ids = _spec_ids_of(side)
        if not spec_ids:
            return
        grant_item_specs_to_inventory(
            receiver, spec_ids, self._items, self._item_specs, self._inventories,
            overflow_sink=self._overflow_sink,
        )

    def _owned_counts(self, player_id: PlayerId) -> Dict[int, int]:
        inventory = self._inventories.find_by_id(player_id)
        if inventory is None:
            return {}
        counts = count_owned_item_instances_by_spec(inventory, self._items)
        return {spec.value: count for spec, count in counts.items()}

    def _item_spec_id_by_label(self, label: str) -> int:
        """求める品の名前を、世界の宣言から引く。

        相手の持ち物は見えないので、表示ではなく**世界に在る品の名前**で
        指名する。世界に無い名前はここで落とす。
        """
        spec = self._item_specs.find_by_name(str(label))
        if spec is None:
            raise TradeUnknownItemError(item_label=str(label))
        return spec.item_spec_id.value

    def _item_display_name(self, item_spec_id: int) -> str:
        if self._item_name is None:
            return "その品"
        try:
            return self._item_name(item_spec_id) or "その品"
        except Exception:  # noqa: BLE001
            return "その品"

    def _name_of(self, player_id: PlayerId) -> str:
        if self._entity_name is None:
            return "相手"
        try:
            return self._entity_name(int(player_id)) or "相手"
        except Exception:  # noqa: BLE001
            return "相手"


def _spec_ids_of(side: TradeSide) -> Tuple[ItemSpecId, ...]:
    """片側の品を、1 個 1 要素の並びにする。"""
    return tuple(
        ItemSpecId.create(spec_id)
        for spec_id, quantity in side.items
        for _ in range(quantity)
    )


def _item_count(side: TradeSide) -> int:
    """片側が動かす品の個数 (gold は枠を取らないので数えない)。"""
    return sum(quantity for _spec_id, quantity in side.items)


__all__ = [
    "AmbiguousOfferError",
    "NoOfferForYouError",
    "PlayerTradeException",
    "PlayerTradeService",
    "TradeAskNotMetError",
    "TradeDuplicateOfferError",
    "TradeGoldNotEnoughError",
    "TradeItemNotOwnedError",
    "TradePartnerNotHereError",
    "TradeReceiverInventoryFullError",
    "TradeSelfInventoryFullError",
    "TradeSettlement",
    "TradeUnknownItemError",
    "TRADE_GOLD_SOURCE",
]
