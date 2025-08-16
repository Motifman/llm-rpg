from dataclasses import dataclass, field
from typing import List, Optional
from src.domain.item.item import Item


@dataclass(frozen=True)
class DropReward:
    gold: int = 0
    exp: int = 0
    items: Optional[List[Item]] = field(default_factory=list)
    information: Optional[List[str]] = field(default_factory=list)
    
    @classmethod
    def create(cls, gold: int, exp: int, items: Optional[List[Item]], information: Optional[List[str]]) -> "MonsterDropReward":
        if gold < 0:
            gold = 0
        if exp < 0:
            exp = 0
        return cls(gold, exp, items, information)