from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    """アイテム"""
    item_id: str
    description: str

    def __str__(self):
        return f"{self.item_id} - {self.description}"
    
    def __repr__(self):
        return f"Item(item_id={self.item_id}, description={self.description})"