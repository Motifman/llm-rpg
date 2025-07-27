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
    
    def __post_init__(self):
        # 親クラスのItemコンストラクタを正しく呼び出す
        super().__init__(self.item_id, self.name, self.description)
    
    def can_consume(self, player: "Player") -> bool:
        return player.has_item(self.item_id)
    
    def __str__(self):
        return f"{self.name} ({self.item_id}) - {self.description} ({self.effect})"
    
    def __repr__(self):
        return f"ConsumableItem(item_id={self.item_id}, name={self.name}, description={self.description}, effect={self.effect}, max_stack={self.max_stack})"