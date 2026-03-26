"""GlobalMarketListingReadModel 用 SQLite スキーマ"""

import sqlite3


def init_global_market_listing_read_model_schema(conn: sqlite3.Connection) -> None:
    """global_market_listing_read_models テーブルを作成する（commit しない）。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS global_market_listing_read_models (
            trade_id INTEGER PRIMARY KEY NOT NULL,
            item_spec_id INTEGER NOT NULL,
            item_instance_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            item_quantity INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            item_rarity TEXT NOT NULL,
            item_equipment_type TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            durability_current INTEGER,
            durability_max INTEGER,
            requested_gold INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_gml_created_trade
            ON global_market_listing_read_models(created_at, trade_id)
        """
    )
