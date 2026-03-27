"""取引集約の SQLite 実装（`GAME_DB_PATH` / UoW 共有接続）。"""
from __future__ import annotations

import copy
import sqlite3
from typing import Any, List, Optional

from ai_rpg_world.domain.trade.aggregate.trade_aggregate import TradeAggregate
from ai_rpg_world.domain.trade.repository.trade_repository import TradeRepository
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    allocate_sequence_value,
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_command_codec import (
    row_to_trade_aggregate,
    trade_aggregate_to_row,
)


class SqliteTradeAggregateRepository(TradeRepository):
    """`TradeRepository` の SQLite 実装。`save` 時に `event_sink` があれば集約イベントを UoW に渡す。"""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        _commits_after_write: bool,
        event_sink: Any = None,
    ) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        self._event_sink = event_sink
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(
        cls,
        connection: sqlite3.Connection,
        *,
        event_sink: Any = None,
    ) -> SqliteTradeAggregateRepository:
        return cls(connection, _commits_after_write=True, event_sink=event_sink)

    @classmethod
    def for_shared_unit_of_work(
        cls,
        connection: sqlite3.Connection,
        *,
        event_sink: Any = None,
    ) -> SqliteTradeAggregateRepository:
        return cls(connection, _commits_after_write=False, event_sink=event_sink)

    def _finalize_write(self) -> None:
        """単体接続は常に commit。UoW 共有かつ scope 内は UoW に任せる。それ以外は暗黙 tx を閉じるため commit。"""
        if self._commits_after_write:
            self._conn.commit()
            return
        if self._event_sink is not None and hasattr(self._event_sink, "is_in_transaction"):
            if self._event_sink.is_in_transaction():
                return
        self._conn.commit()

    def _maybe_emit_events(self, aggregate: Any) -> None:
        sink = self._event_sink
        if sink is None or not hasattr(sink, "add_events_from_aggregate"):
            return
        if hasattr(sink, "is_in_transaction") and not sink.is_in_transaction():
            return
        sink.add_events_from_aggregate(aggregate)

    def generate_trade_id(self) -> TradeId:
        tid = TradeId(allocate_sequence_value(self._conn, "trade_id"))
        self._finalize_write()
        return tid

    def find_by_id(self, trade_id: TradeId) -> Optional[TradeAggregate]:
        cur = self._conn.execute(
            "SELECT * FROM trade_aggregates WHERE trade_id = ?",
            (int(trade_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(row_to_trade_aggregate(row))

    def find_by_ids(self, trade_ids: List[TradeId]) -> List[TradeAggregate]:
        return [t for tid in trade_ids for t in [self.find_by_id(tid)] if t is not None]

    def save(self, trade: TradeAggregate) -> TradeAggregate:
        self._maybe_emit_events(trade)
        row = trade_aggregate_to_row(trade)
        self._conn.execute(
            """
            INSERT INTO trade_aggregates (
                trade_id, seller_id, offered_item_id, requested_gold, created_at,
                trade_type, target_player_id, status, version, buyer_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_id) DO UPDATE SET
                seller_id = excluded.seller_id,
                offered_item_id = excluded.offered_item_id,
                requested_gold = excluded.requested_gold,
                created_at = excluded.created_at,
                trade_type = excluded.trade_type,
                target_player_id = excluded.target_player_id,
                status = excluded.status,
                version = excluded.version,
                buyer_id = excluded.buyer_id
            """,
            row,
        )
        self._finalize_write()
        return copy.deepcopy(trade)

    def delete(self, trade_id: TradeId) -> bool:
        cur = self._conn.execute(
            "DELETE FROM trade_aggregates WHERE trade_id = ?",
            (int(trade_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0

    def find_all(self) -> List[TradeAggregate]:
        cur = self._conn.execute("SELECT * FROM trade_aggregates")
        return [copy.deepcopy(row_to_trade_aggregate(r)) for r in cur.fetchall()]


__all__ = ["SqliteTradeAggregateRepository"]
