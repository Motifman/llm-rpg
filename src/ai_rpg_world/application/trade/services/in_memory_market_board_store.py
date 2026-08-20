"""市場の掲示板を保持する store (経済統合 Phase 3)。

板は**世界の状態**で、誰かの記憶ではない。per-Being の記憶ではなく world
snapshot に載せるのはそのため。ここが保存・復元されないと、中断・再開で板が
消えて、預けた品と gold がまるごと消滅する。

板そのものは不変オブジェクトなので、store は「いまの板」と「次に払い出す
注文 ID」だけを持つ。
"""

from __future__ import annotations

import threading
from typing import Iterable, Optional

from ai_rpg_world.domain.trade.aggregate.market_board import MarketBoard, MarketTrade
from ai_rpg_world.domain.trade.aggregate.market_order import MarketOrder
from ai_rpg_world.domain.trade.value_object.market_order_id import MarketOrderId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class InMemoryMarketBoardStore:
    """掲示板 1 つと、その置き場所を保持する。"""

    def __init__(self, *, board_spot_id: Optional[SpotId] = None) -> None:
        self._board = MarketBoard.empty()
        self._board_spot_id = board_spot_id
        self._next_id = 1
        self._lock = threading.RLock()

    @property
    def board_spot_id(self) -> Optional[SpotId]:
        """板の置いてある場所。宣言の無い世界では None (板が無い)。"""
        return self._board_spot_id

    def next_order_id(self) -> MarketOrderId:
        with self._lock:
            order_id = MarketOrderId(self._next_id)
            self._next_id += 1
            return order_id

    def board(self) -> MarketBoard:
        with self._lock:
            return self._board

    def save(self, board: MarketBoard) -> None:
        """板を丸ごと置き換える。板は不変なので差分は持たない。"""
        if not isinstance(board, MarketBoard):
            raise TypeError("board must be MarketBoard")
        with self._lock:
            self._board = board
            for order in board.orders:
                self._next_id = max(self._next_id, order.order_id.value + 1)

    def replace_all(
        self,
        orders: Iterable[MarketOrder],
        last_trades: Iterable[MarketTrade] = (),
    ) -> None:
        """snapshot 復元用。板の注文と直近の約定を丸ごと置き換える。

        ID の払い出しも戻す。戻さないと、再開後に出した注文が復元済みの注文と
        同じ ID になり、板が「同じ ID を二度置けません」で落ちる。
        """
        with self._lock:
            self._board = MarketBoard.empty()
            self._next_id = 1
            self.save(MarketBoard(
                orders=tuple(orders), last_trades=tuple(last_trades),
            ))


__all__ = ["InMemoryMarketBoardStore"]
