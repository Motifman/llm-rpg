"""
取引ページング用の汎用カーソルコーデック
"""
import base64
import json
from datetime import datetime
from typing import Optional

from ai_rpg_world.domain.trade.repository.cursor import Cursor, TradeCursor, ListingCursor


class CursorCodec:
    """ページング用の汎用カーソルエンコード/デコードユーティリティ"""

    @staticmethod
    def encode(cursor: Cursor) -> str:
        """Cursorをbase64エンコードされた文字列に変換"""
        data = {
            "created_at": cursor.created_at.isoformat(),
            "entity_id": cursor.entity_id
        }
        json_str = json.dumps(data, separators=(',', ':'))
        return base64.b64encode(json_str.encode('utf-8')).decode('utf-8')

    @staticmethod
    def decode_trade_cursor(encoded_cursor: str) -> TradeCursor:
        """エンコードされたカーソル文字列からTradeCursorを復元"""
        try:
            json_str = base64.b64decode(encoded_cursor.encode('utf-8')).decode('utf-8')
            data = json.loads(json_str)

            created_at = datetime.fromisoformat(data["created_at"])
            trade_id = int(data["entity_id"])

            return TradeCursor(created_at=created_at, trade_id=trade_id)
        except (ValueError, KeyError, TypeError):
            raise ValueError(f"Invalid cursor format: {encoded_cursor}")

    @staticmethod
    def decode_listing_cursor(encoded_cursor: str) -> ListingCursor:
        """エンコードされたカーソル文字列からListingCursorを復元"""
        try:
            json_str = base64.b64decode(encoded_cursor.encode('utf-8')).decode('utf-8')
            data = json.loads(json_str)

            created_at = datetime.fromisoformat(data["created_at"])
            listing_id = int(data["entity_id"])

            return ListingCursor(created_at=created_at, listing_id=listing_id)
        except (ValueError, KeyError, TypeError):
            raise ValueError(f"Invalid cursor format: {encoded_cursor}")
