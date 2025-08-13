from game.core.unit_of_work import UnitOfWork
from game.repository.player_repository import PlayerRepository
from game.repository.trade_repository import TradeRepository


class TradeService:
    """取引成立など、複数アグリゲート横断のユースケースを1Txで実行（雛形）。"""

    def __init__(self, uow: UnitOfWork, players: PlayerRepository, trades: TradeRepository):
        self._uow = uow
        self._players = players
        self._trades = trades

    def accept_trade_atomic(self, trade_id: str, buyer_id: str) -> None:
        with self._uow.transaction("IMMEDIATE"):
            t = self._trades.get_for_update(trade_id)
            seller_id = t.seller_id
            price = t.requested_money
            item_id = t.offered_item_id
            count = t.offered_item_count

            # 在庫移転と金銭授受（エラーハンドリングは実装時に）
            self._players.add_stack(seller_id, item_id, -count)
            self._players.add_stack(buyer_id, item_id, +count)
            self._players.increment_gold(buyer_id, -price)
            self._players.increment_gold(seller_id, +price)

            self._trades.mark_completed(trade_id, buyer_id)
