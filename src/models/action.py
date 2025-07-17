from dataclasses import dataclass
from typing import Optional
from abc import ABC


@dataclass(frozen=True)
class Action(ABC):
    """行動の基底クラス"""
    description: str


@dataclass(frozen=True)
class Movement(Action):
    """移動行動"""
    direction: str
    target_spot_id: str


@dataclass(frozen=True)
class Exploration(Action):
    """探索行動"""
    item_id: Optional[str] = None
    discovered_info: Optional[str] = None
    experience_points: Optional[int] = None
    money: Optional[int] = None