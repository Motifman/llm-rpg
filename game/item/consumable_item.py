from dataclasses import dataclass, field
from typing import List, TYPE_CHECKING, Optional

from game.item.item import Item
from game.item.item_effect import ItemEffect

if TYPE_CHECKING:
    from game.player.player import Player


@dataclass(frozen=True)
class ConsumableItem(Item):
    effect: ItemEffect
    max_stack: int = 1 
    
    def can_consume(self, agent: "Player") -> bool:
        return agent.get_inventory().has_item(self.item_id)
    
    def __str__(self):
        return f"{self.item_id} - {self.description} ({self.effect})"
    
    def __repr__(self):
        return f"ConsumableItem(item_id={self.item_id}, description={self.description}, effect={self.effect}, max_stack={self.max_stack})"