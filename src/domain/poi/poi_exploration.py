from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Set

from src.domain.poi.poi import POI, POIReward

if TYPE_CHECKING:
    from src.domain.player.player import Player


@dataclass
class POIExplorationResult:
    """探索結果（値オブジェクト）"""
    poi_id: int
    success: bool
    reward: POIReward
    timestamp: datetime


class POIExploration:
    """POI探索ドメインサービス"""
    def explore_poi(self, poi: POI, player: 'Player', discovered_pois: Set[int]) -> POIExplorationResult:
        """POI探索のドメインロジック"""
        if not poi.can_explore(player, discovered_pois):
            return POIExplorationResult(poi.poi_id, False, POIReward(), datetime.now())
        
        reward = poi.explore()
        return POIExplorationResult(poi.poi_id, True, reward, datetime.now())