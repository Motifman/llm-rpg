"""
取引ページング用の汎用カーソル
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Cursor(ABC):
    """ページング用の抽象カーソル

    ドメイン層でのカーソル表現。アプリケーション層でのエンコード/デコードは
    別途CursorCodecで行う。
    """
    created_at: datetime

    @property
    @abstractmethod
    def entity_id(self) -> int:
        """エンティティの一意なID"""
        pass


@dataclass(frozen=True)
class TradeCursor(Cursor):
    """取引ページング用のカーソル"""
    created_at: datetime
    trade_id: int

    @property
    def entity_id(self) -> int:
        return self.trade_id


@dataclass(frozen=True)
class ListingCursor(Cursor):
    """出品ページング用のカーソル"""
    created_at: datetime
    listing_id: int  # trade_idと同じ

    @property
    def entity_id(self) -> int:
        return self.listing_id
