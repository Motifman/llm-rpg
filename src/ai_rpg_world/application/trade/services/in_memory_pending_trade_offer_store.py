"""返事待ちの取引提案を保持する store (Phase 2)。

提案は**二人の間にある状態**なので、per-Being の記憶ではなく world 状態と
して持つ。world snapshot に載せるのはそのため。

二重提案を弾くのはこの層の仕事にする。集約は 1 件の提案の中だけを見るので、
「同じ相手へ既に持ちかけている」「同じ品を別の提案にも出している」は集約
からは見えない。
"""

from __future__ import annotations

import threading
from typing import Dict, Iterable, Optional, Tuple

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.aggregate.pending_trade_offer import (
    PendingTradeOffer,
    TradeOfferState,
)
from ai_rpg_world.domain.trade.value_object.trade_offer_id import TradeOfferId


class InMemoryPendingTradeOfferStore:
    """返事待ちの提案を保持する。返事のついた提案は保持しない。"""

    def __init__(self) -> None:
        self._offers: Dict[int, PendingTradeOffer] = {}
        self._next_id = 1
        self._lock = threading.RLock()

    def next_offer_id(self) -> TradeOfferId:
        """次に使う提案 ID を払い出す。"""
        with self._lock:
            offer_id = TradeOfferId(self._next_id)
            self._next_id += 1
            return offer_id

    def put(self, offer: PendingTradeOffer) -> None:
        """提案を保持する。返事待ちでないものは持たない。"""
        if not isinstance(offer, PendingTradeOffer):
            raise TypeError("offer must be PendingTradeOffer")
        with self._lock:
            if offer.is_pending:
                self._offers[offer.offer_id.value] = offer
                self._next_id = max(self._next_id, offer.offer_id.value + 1)
            else:
                self._offers.pop(offer.offer_id.value, None)

    def find(self, offer_id: TradeOfferId) -> Optional[PendingTradeOffer]:
        with self._lock:
            return self._offers.get(offer_id.value)

    def list_all(self) -> Tuple[PendingTradeOffer, ...]:
        """保持している提案を、提案 ID の順で返す。"""
        with self._lock:
            return tuple(self._offers[k] for k in sorted(self._offers))

    def list_for_target(self, player_id: PlayerId) -> Tuple[PendingTradeOffer, ...]:
        """その人に宛てられた提案を、古い順で返す。"""
        return tuple(
            offer for offer in self.list_all() if offer.target_player_id == player_id
        )

    def list_from_offerer(self, player_id: PlayerId) -> Tuple[PendingTradeOffer, ...]:
        """その人が出している提案を、古い順で返す。"""
        return tuple(
            offer for offer in self.list_all() if offer.offerer_player_id == player_id
        )

    def has_offer_between(self, offerer: PlayerId, target: PlayerId) -> bool:
        """その向きの提案が既に生きているか (同一ペアの二重提案を弾くのに使う)。"""
        return any(
            offer.offerer_player_id == offerer and offer.target_player_id == target
            for offer in self.list_all()
        )

    def committed_item_quantities(self, offerer: PlayerId) -> Dict[int, int]:
        """その人が提案に出している品の合計数を item_spec_id ごとに返す。

        凍結 (次の PR) が「同じ品を 2 件の提案に出す」を弾くのに使う。
        """
        totals: Dict[int, int] = {}
        for offer in self.list_from_offerer(offerer):
            for spec_id, quantity in offer.gives.items:
                totals[spec_id] = totals.get(spec_id, 0) + quantity
        return totals

    def committed_gold(self, offerer: PlayerId) -> int:
        """その人が提案に出している gold の合計。"""
        return sum(offer.gives.gold for offer in self.list_from_offerer(offerer))

    def expired_offers(self, current_tick: int) -> Tuple[PendingTradeOffer, ...]:
        """その tick で期限を過ぎている提案を返す (状態は変えない)。

        状態遷移と観測の発火は呼び出し側 (tick stage) の仕事にする。store が
        観測を持つと、保存・復元のたびに「流れた」が二重に届きうる。
        """
        return tuple(
            offer for offer in self.list_all() if offer.is_expired_at(current_tick)
        )

    def remove(self, offer_id: TradeOfferId) -> None:
        with self._lock:
            self._offers.pop(offer_id.value, None)

    def replace_all(self, offers: Iterable[PendingTradeOffer]) -> None:
        """snapshot 復元用。保持している提案を丸ごと置き換える。"""
        with self._lock:
            self._offers = {}
            self._next_id = 1
            for offer in offers:
                self.put(offer)


__all__ = ["InMemoryPendingTradeOfferStore", "TradeOfferState"]
