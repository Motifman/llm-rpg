from dataclasses import dataclass
from src.domain.item.durability import Durability
from src.domain.item.unique_item import UniqueItem
from src.domain.player.base_status import BaseStatus


@dataclass(frozen=True)
class EquipmentItem(UniqueItem):
    """装備品。UniqueItemの具体的な一種。"""
    base_status: BaseStatus
    durability: Durability

    def __post_init__(self):
        super().__post_init__()
        if self.durability.is_broken():
            raise ValueError(f"Durability is broken. durability: {self.durability}")
    
    def durability_damage(self, amount: int) -> int:
        return self.durability.damage(amount)
    
    def durability_repair(self, amount: int) -> int:
        return self.durability.repair(amount)
    
    def is_broken(self) -> bool:
        return self.durability.is_broken()