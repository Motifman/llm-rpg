from typing import Dict, Set, List
from ai_rpg_world.domain.poi.poi_exploration import POIExplorationResult


class PlayerPOIState:
    """プレイヤーPOI状態集約ルート"""
    def __init__(self, player_id: str):
        self._player_id = player_id
        self._discovered_pois: Dict[int, Set[int]] = {}  # spot_id -> poi_ids
        self._exploration_history: List[POIExplorationResult] = []
    
    def record_exploration(self, spot_id: int, result: POIExplorationResult):
        """探索結果記録（ドメインロジック）"""
        if result.success:
            if spot_id not in self._discovered_pois:
                self._discovered_pois[spot_id] = set()
            self._discovered_pois[spot_id].add(result.poi_id)
        
        self._exploration_history.append(result)
