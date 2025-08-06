from typing import Dict, Set, List, Optional
from dataclasses import dataclass, field


@dataclass
class POIExplorationResult:
    """POIの探索結果を表現するデータクラス"""
    description: str
    found_items: List[str] = field(default_factory=list)  # 発見したアイテムのID
    encountered_monsters: List[str] = field(default_factory=list)  # 遭遇したモンスターのID
    unlocked_pois: List[str] = field(default_factory=list)  # 解放されたPOIのID


class PlayerPOIProgress:
    """特定のプレイヤーのPOI探索進捗を管理"""
    def __init__(self, player_id: str):
        self.player_id = player_id
        self._discovered_pois: Dict[str, Set[str]] = {}  # spot_id -> set of discovered poi_ids
        self._exploration_history: Dict[str, Dict[str, POIExplorationResult]] = {}  # spot_id -> (poi_id -> result)
        
    def add_spot(self, spot_id: str):
        """新しいSpotの進捗管理を開始"""
        if spot_id not in self._discovered_pois:
            self._discovered_pois[spot_id] = set()
            self._exploration_history[spot_id] = {}
            
    def has_discovered_poi(self, spot_id: str, poi_id: str) -> bool:
        """指定したPOIが発見済みかチェック"""
        return poi_id in self._discovered_pois.get(spot_id, set())
        
    def get_discovered_pois(self, spot_id: str) -> Set[str]:
        """指定したSpotで発見済みのPOIのIDを取得"""
        return self._discovered_pois.get(spot_id, set()).copy()
        
    def record_poi_discovery(
        self,
        spot_id: str,
        poi_id: str,
        exploration_result: POIExplorationResult
    ):
        """POIの探索結果を記録"""
        if spot_id not in self._discovered_pois:
            self.add_spot(spot_id)
            
        self._discovered_pois[spot_id].add(poi_id)
        self._exploration_history[spot_id][poi_id] = exploration_result
        
    def get_exploration_result(
        self,
        spot_id: str,
        poi_id: str
    ) -> Optional[POIExplorationResult]:
        """過去の探索結果を取得"""
        return self._exploration_history.get(spot_id, {}).get(poi_id)


class POIProgressManager:
    """全プレイヤーのPOI探索進捗を管理"""
    def __init__(self):
        self._player_progress: Dict[str, PlayerPOIProgress] = {}
        
    def get_player_progress(self, player_id: str) -> PlayerPOIProgress:
        """プレイヤーの進捗を取得（存在しない場合は新規作成）"""
        if player_id not in self._player_progress:
            self._player_progress[player_id] = PlayerPOIProgress(player_id)
        return self._player_progress[player_id]
        
    def record_poi_discovery(
        self,
        player_id: str,
        spot_id: str,
        poi_id: str,
        exploration_result: POIExplorationResult
    ):
        """POIの探索結果を記録"""
        progress = self.get_player_progress(player_id)
        progress.record_poi_discovery(spot_id, poi_id, exploration_result)