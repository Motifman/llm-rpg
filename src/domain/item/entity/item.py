from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.domain.item.item_enum import ItemType, Rarity
from src.domain.item.item_effect import ItemEffect


@dataclass(frozen=True)
class Item:
    """全てのアイテムの基底となる抽象クラス"""
    item_id: int
    name: str
    description: str
    item_type: ItemType
    rarity: Rarity
    is_tradeable: bool = True
    
    def __post_init__(self):
        if self.item_id < 0:
            raise ValueError(f"item_id must be >= 0. item_id: {self.item_id}")
        if self.name == "":
            raise ValueError(f"name must not be empty. name: {self.name}")
        if self.description == "":
            raise ValueError(f"description must not be empty. description: {self.description}")
    





