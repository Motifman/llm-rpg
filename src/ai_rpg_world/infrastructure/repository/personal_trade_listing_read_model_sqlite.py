"""PersonalTradeListingReadModel 用 SQLite スキーマ"""

import sqlite3


def init_personal_trade_listing_read_model_schema(conn: sqlite3.Connection) -> None:
    """personal_trade_listing_read_models テーブルを作成する（commit しない）。"""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS personal_trade_listing_read_models (
            trade_id INTEGER PRIMARY KEY NOT NULL,
            item_spec_id INTEGER NOT NULL,
            item_instance_id INTEGER NOT NULL,
            recipient_player_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            item_quantity INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            item_rarity TEXT NOT NULL,
            item_equipment_type TEXT,
            durability_current INTEGER,
            durability_max INTEGER,
            requested_gold INTEGER NOT NULL,
            seller_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ptl_recipient_created_trade
            ON personal_trade_listing_read_models(
                recipient_player_id, created_at, trade_id
            )
        """
    )
