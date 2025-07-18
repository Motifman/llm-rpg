from dataclasses import dataclass, field
from typing import Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .agent import Agent


@dataclass(frozen=True)
class Item:
    """アイテム"""
    item_id: str
    description: str

    def __str__(self):
        return f"{self.item_id} - {self.description}"
    
    def __repr__(self):
        return f"Item(item_id={self.item_id}, description={self.description})"


@dataclass(frozen=True)
class ItemEffect:
    """アイテム消費時の効果"""
    hp_change: int = 0
    mp_change: int = 0
    attack_change: int = 0
    defense_change: int = 0
    money_change: int = 0
    experience_change: int = 0
    temporary_effects: Dict[str, Any] = field(default_factory=dict)
    
    def __str__(self):
        effects = []
        if self.hp_change != 0:
            effects.append(f"HP{self.hp_change:+d}")
        if self.mp_change != 0:
            effects.append(f"MP{self.mp_change:+d}")
        if self.attack_change != 0:
            effects.append(f"攻撃力{self.attack_change:+d}")
        if self.defense_change != 0:
            effects.append(f"防御力{self.defense_change:+d}")
        if self.money_change != 0:
            effects.append(f"所持金{self.money_change:+d}")
        if self.experience_change != 0:
            effects.append(f"経験値{self.experience_change:+d}")
        if self.temporary_effects:
            for key, value in self.temporary_effects.items():
                effects.append(f"{key}: {value}")
        
        return "効果: " + ", ".join(effects) if effects else "効果なし"


@dataclass(frozen=True)
class ConsumableItem(Item):
    """消費可能アイテム"""
    effect: ItemEffect
    max_stack: int = 1  # スタック数（重複所持数）
    
    def can_consume(self, agent: "Agent") -> bool:
        """消費可能かチェック"""
        return agent.has_item(self.item_id)
    
    def __str__(self):
        return f"{self.item_id} - {self.description} ({self.effect})"
    
    def __repr__(self):
        return f"ConsumableItem(item_id={self.item_id}, description={self.description}, effect={self.effect}, max_stack={self.max_stack})"