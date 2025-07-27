from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    item_id: str
    name: str
    description: str

    def __str__(self):
        return f"{self.name} ({self.item_id}) - {self.description}"
    
    def __repr__(self):
        return f"Item(item_id={self.item_id}, name={self.name}, description={self.description})"