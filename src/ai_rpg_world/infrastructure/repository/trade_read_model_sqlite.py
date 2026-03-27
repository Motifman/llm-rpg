"""Trade ReadModel 用 SQLite スキーマ初期化（LLM memory DB とは分離）"""

import sqlite3


def init_trade_read_model_schema(conn: sqlite3.Connection) -> None:
    """trade_read_models テーブルと seller+ACTIVE 向け複合 index を作成する。

    明示的な `commit()` は行わない。`SqliteUnitOfWork` 等の外側トランザクションに含められるよう、
    DDL のみを発行する。単体接続（既定の自動コミットモード）では各文が自動確定される。
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_read_models (
            trade_id INTEGER PRIMARY KEY NOT NULL,
            seller_id INTEGER NOT NULL,
            seller_name TEXT NOT NULL,
            buyer_id INTEGER,
            buyer_name TEXT,
            requested_gold INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            item_instance_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            item_quantity INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            item_rarity TEXT NOT NULL,
            item_description TEXT NOT NULL,
            item_equipment_type TEXT,
            durability_current INTEGER,
            durability_max INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_trade_read_seller_status_created_trade
            ON trade_read_models(seller_id, status, created_at, trade_id)
        """
    )
