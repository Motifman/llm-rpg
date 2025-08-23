from dataclasses import dataclass
from src.domain.item.item import Item
from src.domain.item.unique_item import UniqueItem


@dataclass(frozen=True)
class ItemQuantity:
    """アイテムの数量を表すバリューオブジェクト"""
    item: Item
    quantity: int
    
    def __post_init__(self):
        if self.quantity < 0:
            raise ValueError(f"Quantity must be >= 0: {self.quantity}")
        if isinstance(self.item, UniqueItem):
            raise ValueError(f"Unique item cannot have quantity: {self.item}")
    
    def split(self, amount: int) -> tuple['ItemQuantity', 'ItemQuantity']:
        """指定した数量で分割する"""
        if amount <= 0 or amount >= self.quantity:
            raise ValueError(f"Invalid split amount: {amount}")
        
        return (
            ItemQuantity(self.item, amount),
            ItemQuantity(self.item, self.quantity - amount)
        )
    
    def merge(self, other: 'ItemQuantity') -> 'ItemQuantity':
        """同じアイテムの数量をマージする"""
        if self.item.item_id != other.item.item_id:
            raise ValueError("Cannot merge different items")
        
        return ItemQuantity(self.item, self.quantity + other.quantity)