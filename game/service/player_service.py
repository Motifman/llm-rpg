from typing import Optional
from game.core.unit_of_work import UnitOfWork
from game.repository.player_repository import PlayerRepository


class PlayerService:
    """単一プレイヤー内のユースケースをTxで実行（雛形）。"""

    def __init__(self, uow: UnitOfWork, players: PlayerRepository):
        self._uow = uow
        self._players = players

    def equip_item_atomic(self, player_id: str, slot: str, *, item_id: Optional[str] = None, unique_item_id: Optional[str] = None) -> None:
        with self._uow.transaction("IMMEDIATE"):
            current = self._players.get_equipment(player_id).get(slot)
            if current:
                self._players.clear_equipment(player_id, slot)
                # スタック装備を想定（ユニークはスロット解除だけ）
                if getattr(current, "item_id", None):
                    self._players.add_stack(player_id, current.item_id, +1)
            if unique_item_id:
                self._players.upsert_equipment(player_id, slot, unique_item_id=unique_item_id)
            else:
                assert item_id is not None
                self._players.add_stack(player_id, item_id, -1)
                self._players.upsert_equipment(player_id, slot, item_id=item_id)

    def add_gold_atomic(self, player_id: str, delta: int) -> None:
        with self._uow.transaction("IMMEDIATE"):
            self._players.increment_gold(player_id, delta)
