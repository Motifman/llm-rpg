from typing import Dict, List, Optional, Set
from game.world.poi import POI, POIUnlockCondition
from game.world.poi_progress import POIProgressManager, POIExplorationResult
from game.enums import PlayerState
from game.battle.battle_manager import BattleManager
from game.core.game_context import GameContext
from game.player.player import Player


class POIManager:
    """POIシステム全体を管理"""
    def __init__(self):
        self._spot_pois: Dict[str, Dict[str, POI]] = {}  # spot_id -> (poi_id -> POI)
        self._progress_manager = POIProgressManager()
        
    def register_poi(self, spot_id: str, poi: POI):
        """SpotにPOIを登録"""
        if spot_id not in self._spot_pois:
            self._spot_pois[spot_id] = {}
        self._spot_pois[spot_id][poi.poi_id] = poi
        
    def get_available_pois(
        self,
        spot_id: str,
        player: Player
    ) -> List[POI]:
        """プレイヤーが調査可能なPOIのリストを取得"""
        if spot_id not in self._spot_pois:
            return []
            
        progress = self._progress_manager.get_player_progress(player.player_id)
        discovered_pois = progress.get_discovered_pois(spot_id)
        
        return [
            poi for poi in self._spot_pois[spot_id].values()
            if poi.is_accessible(player, discovered_pois)
        ]
        
    def get_discovered_pois(
        self,
        spot_id: str,
        player: Player
    ) -> List[POI]:
        """プレイヤーが既に発見したPOIのリストを取得"""
        if spot_id not in self._spot_pois:
            return []
            
        progress = self._progress_manager.get_player_progress(player.player_id)
        discovered_poi_ids = progress.get_discovered_pois(spot_id)
        
        return [
            self._spot_pois[spot_id][poi_id]
            for poi_id in discovered_poi_ids
            if poi_id in self._spot_pois[spot_id]
        ]
        
    def explore_poi(
        self,
        spot_id: str,
        poi_id: str,
        player: Player,
        game_context: GameContext
    ) -> POIExplorationResult:
        """POIを探索"""
        if spot_id not in self._spot_pois or poi_id not in self._spot_pois[spot_id]:
            raise ValueError(f"POI not found: {spot_id}/{poi_id}")
            
        poi = self._spot_pois[spot_id][poi_id]
        progress = self._progress_manager.get_player_progress(player.player_id)
        
        # 既に探索済みの場合は過去の結果を返す
        if progress.has_discovered_poi(spot_id, poi_id):
            return progress.get_exploration_result(spot_id, poi_id)
            
        # POIの探索結果を取得
        discovery = poi.get_discovery_result()
        
        # アイテムの取得処理
        found_items = []
        for item in discovery['items']:
            player.add_item(item)
            found_items.append(item.item_id)
            
        # モンスターとの戦闘処理
        encountered_monsters = []
        if discovery['monsters']:
            battle_manager = game_context.get_battle_manager()
            battle_manager.start_battle(spot_id, discovery['monsters'], player)
            player.set_player_state(PlayerState.BATTLE)
            for monster in discovery['monsters']:
                encountered_monsters.append(monster.monster_id)
                
        # 探索結果を作成
        result = POIExplorationResult(
            description=discovery['description'],
            found_items=found_items,
            encountered_monsters=encountered_monsters,
            unlocked_pois=discovery['unlocks_pois']
        )
        
        # 結果を記録
        self._progress_manager.record_poi_discovery(
            player.player_id,
            spot_id,
            poi_id,
            result
        )
        
        return result
        
    def get_exploration_history(
        self,
        spot_id: str,
        poi_id: str,
        player: Player
    ) -> Optional[POIExplorationResult]:
        """過去の探索結果を取得"""
        progress = self._progress_manager.get_player_progress(player.player_id)
        return progress.get_exploration_result(spot_id, poi_id)