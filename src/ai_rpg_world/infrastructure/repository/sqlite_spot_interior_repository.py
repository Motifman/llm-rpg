"""SQLite 実装の ISpotInteriorRepository。"""

from __future__ import annotations

import sqlite3
from typing import Optional

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import ISpotInteriorRepository
from ai_rpg_world.infrastructure.repository.spot_graph_sqlite_schema import init_spot_graph_schema
from ai_rpg_world.infrastructure.repository.sqlite_world_graph_state_codec import (
    dumps_spot_interior,
    loads_spot_interior,
)


class SqliteSpotInteriorRepository(ISpotInteriorRepository):
    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_spot_graph_schema(connection)

    @classmethod
    def for_standalone_connection(cls, connection: sqlite3.Connection) -> SqliteSpotInteriorRepository:
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(cls, connection: sqlite3.Connection) -> SqliteSpotInteriorRepository:
        return cls(connection, _commits_after_write=False)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()

    def _assert_shared_transaction_active(self) -> None:
        if self._commits_after_write:
            return
        if not self._conn.in_transaction:
            raise RuntimeError(
                "for_shared_unit_of_work で生成したリポジトリの書き込みは、"
                "アクティブなトランザクション内（with uow）で実行してください"
            )

    def find_by_spot_id(self, spot_id: SpotId) -> Optional[SpotInterior]:
        row = self._conn.execute(
            "SELECT payload_json FROM spot_graph_interior WHERE spot_id = ?",
            (int(spot_id.value),),
        ).fetchone()
        if row is None:
            return None
        return loads_spot_interior(str(row["payload_json"]))

    def save(self, spot_id: SpotId, interior: SpotInterior) -> None:
        self._assert_shared_transaction_active()
        payload = dumps_spot_interior(interior)
        self._conn.execute(
            "INSERT OR REPLACE INTO spot_graph_interior (spot_id, payload_json) VALUES (?, ?)",
            (int(spot_id.value), payload),
        )
        self._finalize_write()


__all__ = ["SqliteSpotInteriorRepository"]
