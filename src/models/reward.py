from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class ActionReward:
    items: List[str] = field(default_factory=list)
    money: int = 0
    experience: int = 0  
    information: List[str] = field(default_factory=list)