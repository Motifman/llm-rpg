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
        return type("TradeRow", (), {"trade_id": trade_id, "seller_id": "", "requested_money": 0, "offered_item_id": "", "offered_item_count": 0})()

    def mark_completed(self, trade_id: str, buyer_id: str) -> None:
        """取引をCOMPLETEDへ更新（雛形）。"""
        pass
