"""SQLite 実装の ISpotGraphRepository（単一行スナップショット）。"""

from __future__ import annotations

import sqlite3
from json import JSONDecodeError

from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import ISpotGraphRepository
from ai_rpg_world.infrastructure.repository.spot_graph_sqlite_schema import init_spot_graph_schema
from ai_rpg_world.infrastructure.repository.spot_graph_persistence_exceptions import (
    SpotGraphSnapshotNotInitializedError,
    SpotGraphStateDecodeError,
)
from ai_rpg_world.infrastructure.repository.sqlite_world_graph_state_codec import (
    dumps_spot_graph_aggregate,
    loads_spot_graph_aggregate,
)


class SqliteSpotGraphRepository(ISpotGraphRepository):
    """スポットグラフ集約を JSON 1 行で保持する。"""

    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_spot_graph_schema(connection)

    @classmethod
    def for_standalone_connection(cls, connection: sqlite3.Connection) -> SqliteSpotGraphRepository:
        """書き込み後に connection.commit() する（単独接続向け）。"""
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(cls, connection: sqlite3.Connection) -> SqliteSpotGraphRepository:
        """Unit of Work スコープ内で共有する（コミットは UoW 側）。"""
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

    def find_graph(self) -> SpotGraphAggregate:
        row = self._conn.execute(
            "SELECT payload_json FROM spot_graph_snapshot WHERE id = 1"
        ).fetchone()
        if row is None:
            raise SpotGraphSnapshotNotInitializedError(
                "spot_graph_snapshot が未初期化です（シードまたは save を先に実行）"
            )
        payload = str(row["payload_json"])
        try:
            return loads_spot_graph_aggregate(payload)
        except (JSONDecodeError, KeyError, TypeError) as exc:
            raise SpotGraphStateDecodeError(
                "spot_graph_snapshot の payload_json を復元できません"
            ) from exc

    def save(self, graph: SpotGraphAggregate) -> None:
        self._assert_shared_transaction_active()
        payload = dumps_spot_graph_aggregate(graph)
        self._conn.execute(
            "INSERT OR REPLACE INTO spot_graph_snapshot (id, payload_json) VALUES (1, ?)",
            (payload,),
        )
        self._finalize_write()


__all__ = ["SqliteSpotGraphRepository"]
