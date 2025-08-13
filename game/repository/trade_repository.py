from typing import Optional
from game.core.database import Database


class TradeRepository:
    """取引テーブル群のアクセス（雛形）。"""

    def __init__(self, db: Database):
        self._db = db
        self._conn = db.conn
        self._cursor = self._conn.cursor()

    def get_for_update(self, trade_id: str) -> object:
        """取引をロックしつつ取得（雛形：実装時に楽観ロック/状態確認）。"""
        rows = self._db.query(
            """
            SELECT * FROM trade WHERE trade_id = ?
            """,
            (trade_id,),
        )
        if not rows:
            raise ValueError(f"trade not found: {trade_id}")
        row = dict(rows[0])
        return row

    def mark_completed(self, trade_id: str, buyer_id: str) -> None:
        """取引をCOMPLETEDへ更新（雛形）。"""
        pass