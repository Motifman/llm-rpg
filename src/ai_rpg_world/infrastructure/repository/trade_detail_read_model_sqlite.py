"""TradeDetailReadModel 用 SQLite スキーマ"""

from __future__ import annotations

import sqlite3

from ai_rpg_world.infrastructure.repository.sqlite_migration import (
    SqliteMigration,
    apply_migrations,
)


_TRADE_DETAIL_NAMESPACE = "trade_detail_read_model"


def _migration_v1(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_detail_read_models (
            trade_id INTEGER PRIMARY KEY NOT NULL,
            item_spec_id INTEGER NOT NULL,
            item_instance_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            item_quantity INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            item_rarity TEXT NOT NULL,
            item_description TEXT NOT NULL,
            item_equipment_type TEXT,
            durability_current INTEGER,
            durability_max INTEGER,
            requested_gold INTEGER NOT NULL,
            seller_name TEXT NOT NULL,
            buyer_name TEXT,
            status TEXT NOT NULL
        )
        """
    )


_TRADE_DETAIL_MIGRATIONS = (
    SqliteMigration(version=1, apply=_migration_v1),
)


def init_trade_detail_read_model_schema(conn: sqlite3.Connection) -> None:
    """trade_detail_read_models テーブルを作成する（commit しない）。"""
    apply_migrations(
        conn,
        namespace=_TRADE_DETAIL_NAMESPACE,
        migrations=_TRADE_DETAIL_MIGRATIONS,
    )
