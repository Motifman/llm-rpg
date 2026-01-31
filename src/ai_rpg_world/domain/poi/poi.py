from dataclasses import dataclass, field
from typing import Set, List, TYPE_CHECKING

from ai_rpg_world.domain.poi.poi_enum import POIType

if TYPE_CHECKING:
    from ai_rpg_world.domain.player.player import Player


@dataclass
class POIUnlockCondition:
    """POIアンロック条件（値オブジェクト）"""
    required_items: Set[int] = field(default_factory=set)
    required_poi_discoveries: Set[int] = field(default_factory=set)
    
    def is_satisfied(self, player: 'Player', discovered_pois: Set[int]) -> bool:
        """条件が満たされているかチェック"""
        if self.required_items and not all(player.has_item(item_id) for item_id in self.required_items):
            return False
        
        if self.required_poi_discoveries and not all(poi_id in discovered_pois for poi_id in self.required_poi_discoveries):
            return False
            
        return True


@dataclass 
class POIReward:
    """POI報酬（値オブジェクト）"""
    information: str = ""
    gold: int = 0
    exp: int = 0
    items: List[int] = field(default_factory=list)
    
    def __post_init__(self):
        if self.items is None:
            self.items = []
        if self.gold < 0:
            raise ValueError("Gold must be greater than 0")
        if self.exp < 0:
            raise ValueError("Exp must be greater than 0")
        if self.information == "":
            self.information = ""


class POI:
    """調査可能な地点を表すクラス"""
    def __init__(self, poi_id: int, name: str, description: str, poi_type: POIType, 
                 unlock_condition: POIUnlockCondition, reward: POIReward):
        self._poi_id = poi_id
        self._name = name
        self._description = description
        self._poi_type = poi_type
        self._unlock_condition = unlock_condition
        self._reward = reward
    
    @property
    def poi_id(self) -> int:
        """POI ID取得"""
        return self._poi_id
    
    def can_explore(self, player: 'Player', discovered_pois: Set[int]) -> bool:
        """探索可能性判定（ドメインロジック）"""
        return self._unlock_condition.is_satisfied(player, discovered_pois)
    
    def explore(self) -> POIReward:
        """探索実行（ドメインロジック）"""
        return self._reward