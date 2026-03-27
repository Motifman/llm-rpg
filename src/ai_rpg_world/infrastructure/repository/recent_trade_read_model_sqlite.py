"""RecentTradeReadModel 用 SQLite スキーマ。"""

from __future__ import annotations

import sqlite3

from ai_rpg_world.infrastructure.repository.sqlite_migration import (
    SqliteMigration,
    apply_migrations,
)


_RECENT_TRADE_NAMESPACE = "recent_trade_read_model"


def _migration_v1(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recent_trade_read_models (
            item_spec_id INTEGER PRIMARY KEY NOT NULL,
            item_name TEXT NOT NULL,
            last_updated TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_recent_trade_read_models_item_name
            ON recent_trade_read_models(item_name)
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recent_trade_read_model_entries (
            item_spec_id INTEGER NOT NULL,
            trade_index INTEGER NOT NULL,
            trade_id INTEGER NOT NULL,
            price INTEGER NOT NULL,
            traded_at TEXT NOT NULL,
            PRIMARY KEY (item_spec_id, trade_index)
        )
        """
    )


_RECENT_TRADE_MIGRATIONS = (
    SqliteMigration(version=1, apply=_migration_v1),
)


def init_recent_trade_read_model_schema(conn: sqlite3.Connection) -> None:
    apply_migrations(
        conn,
        namespace=_RECENT_TRADE_NAMESPACE,
        migrations=_RECENT_TRADE_MIGRATIONS,
    )
