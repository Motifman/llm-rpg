from dataclasses import dataclass
from typing import Optional
from src.domain.trade.exception.trade_exception import InvalidTradeStatusException


@dataclass
class TradeItem:
    item_id: int
    count: Optional[int] = None
    unique_id: Optional[int] = None

    def __post_init__(self):
        """インスタンス生成後のバリデーション"""
        is_stackable = self.count is not None
        is_unique = self.unique_id is not None
        if not (is_stackable or is_unique):
            raise InvalidTradeStatusException(f"TradeItem must have either count or unique_id: {self.item_id}, {self.count}, {self.unique_id}")
        if is_stackable and is_unique:
            raise InvalidTradeStatusException(f"TradeItem cannot have both count and unique_id: {self.item_id}, {self.count}, {self.unique_id}")
        if is_stackable and self.count <= 0:
            raise InvalidTradeStatusException(f"Count must be greater than 0: {self.item_id}, {self.count}, {self.unique_id}")

    @classmethod
    def stackable(cls, item_id: int, count: int) -> "TradeItem":
        """スタック可能アイテム用のファクトリメソッド"""
        return cls(item_id=item_id, count=count, unique_id=None)

    @classmethod
    def unique(cls, item_id: int, unique_id: int) -> "TradeItem":
        """固有アイテム用のファクトリメソッド"""
        return cls(item_id=item_id, count=None, unique_id=unique_id)

    def is_stackable(self) -> bool:
        """スタック可能アイテムかどうか"""
        return self.count is not None
