"""
取引ページング用のカーソルコーデック
"""

import base64
import json
from datetime import datetime
from typing import Optional


class TradeCursorCodec:
    """取引ページング用のカーソルエンコード/デコードユーティリティ"""

    @staticmethod
    def encode(cursor) -> str:
        """TradeCursorをbase64エンコードされた文字列に変換"""
        data = {
            "created_at": cursor.created_at.isoformat(),
            "trade_id": str(cursor.trade_id)  # intをstrに変換
        }
        json_str = json.dumps(data, separators=(',', ':'))
        return base64.b64encode(json_str.encode('utf-8')).decode('utf-8')

    @staticmethod
    def decode(encoded_cursor: str):
        """エンコードされたカーソル文字列からTradeCursorを復元"""
        from src.domain.trade.repository.trade_read_model_repository import TradeCursor

        try:
            json_str = base64.b64decode(encoded_cursor.encode('utf-8')).decode('utf-8')
            data = json.loads(json_str)

            created_at = datetime.fromisoformat(data["created_at"])
            trade_id = int(data["trade_id"])  # strをintに変換

            return TradeCursor(created_at=created_at, trade_id=trade_id)
        except (ValueError, KeyError, TypeError):
            raise ValueError(f"Invalid cursor format: {encoded_cursor}")

