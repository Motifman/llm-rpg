"""ItemTradeStatisticsReadModel 用 SQLite スキーマ。"""

from __future__ import annotations

import sqlite3

from ai_rpg_world.infrastructure.repository.sqlite_migration import (
    SqliteMigration,
    apply_migrations,
)


_ITEM_TRADE_STATS_NAMESPACE = "item_trade_statistics_read_model"


def _migration_v1(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS item_trade_statistics_read_models (
            item_spec_id INTEGER PRIMARY KEY NOT NULL,
            min_price INTEGER,
            max_price INTEGER,
            avg_price REAL,
            median_price INTEGER,
            total_trades INTEGER NOT NULL,
            success_rate REAL NOT NULL,
            last_updated TEXT NOT NULL
        )
        """
    )


_ITEM_TRADE_STATS_MIGRATIONS = (
    SqliteMigration(version=1, apply=_migration_v1),
)


def init_item_trade_statistics_read_model_schema(conn: sqlite3.Connection) -> None:
    apply_migrations(
        conn,
        namespace=_ITEM_TRADE_STATS_NAMESPACE,
        migrations=_ITEM_TRADE_STATS_MIGRATIONS,
    )
