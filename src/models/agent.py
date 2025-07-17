from typing import List
from .item import Item


class Agent:
    def __init__(self, agent_id: str, name: str):
        self.agent_id = agent_id
        self.name = name
        self.items: List[Item] = []
        self.current_spot_id: str = ""

    def add_item(self, item: Item):
        self.items.append(item)

    def remove_item(self, item: Item):
        self.items.remove(item)
    
    def has_item(self, item_id: str) -> bool:
        return any(item.item_id == item_id for item in self.items)
    
    def get_items(self) -> List[Item]:
        return self.items
    
    def get_item_by_id(self, item_id: str) -> Item:
        for item in self.items:
            if item.item_id == item_id:
                return item
        return None
    
    def get_current_spot_id(self) -> str:
        return self.current_spot_id
    
    def set_current_spot_id(self, spot_id: str):
        self.current_spot_id = spot_id
    
    def __str__(self):
        return f"Agent(agent_id={self.agent_id}, name={self.name}, items={self.items})"
    
    def __repr__(self):
        return f"Agent(agent_id={self.agent_id}, name={self.name}, items={self.items})"