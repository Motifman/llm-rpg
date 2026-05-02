"""スポットグラフ用 SQLite テーブル（既存 game_write テーブルとは別 namespace のマイグレーション）。"""

from __future__ import annotations

import sqlite3

from ai_rpg_world.infrastructure.repository.sqlite_migration import SqliteMigration, apply_migrations

_SPOT_GRAPH_NAMESPACE = "spot_graph"


def _migration_v1(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS spot_graph_snapshot (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            payload_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS spot_graph_interior (
            spot_id INTEGER PRIMARY KEY NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )


SPOT_GRAPH_MIGRATIONS: tuple[SqliteMigration, ...] = (
    SqliteMigration(version=1, apply=_migration_v1),
)


def init_spot_graph_schema(connection: sqlite3.Connection) -> int:
    """マイグレーションを適用し、最新バージョン番号を返す。"""
    return apply_migrations(
        connection,
        namespace=_SPOT_GRAPH_NAMESPACE,
        migrations=SPOT_GRAPH_MIGRATIONS,
    )


__all__ = ["SPOT_GRAPH_MIGRATIONS", "init_spot_graph_schema"]
