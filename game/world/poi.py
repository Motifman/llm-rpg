from typing import Dict, List, Optional, Set, TYPE_CHECKING
from dataclasses import dataclass
from game.item.item import Item
from game.monster.monster import Monster

if TYPE_CHECKING:
    from game.player.player import Player
    from game.core.game_context import GameContext


@dataclass
class POIUnlockCondition:
    """POIのアンロック条件を表現するデータクラス"""
    required_items: Set[str] = None  # 必要なアイテムのID
    required_player_states: Set[str] = None  # 必要なプレイヤーの状態
    required_poi_discoveries: Set[str] = None  # 必要な他のPOIの発見状態

    def is_satisfied(self, player: 'Player', discovered_pois: Set[str]) -> bool:
        """条件が満たされているかチェック"""
        if self.required_items and not all(player.has_item(item_id) for item_id in self.required_items):
            return False
        
        if self.required_player_states and not all(player.is_in_state(state) for state in self.required_player_states):
            return False
            
        if self.required_poi_discoveries and not all(poi_id in discovered_pois for poi_id in self.required_poi_discoveries):
            return False
            
        return True


class POI:
    """Point of Interest - Spot内の調査可能な地点を表現"""
    def __init__(
        self,
        poi_id: str,
        name: str,
        description: str,
        detailed_description: str,
        unlock_condition: Optional[POIUnlockCondition] = None
    ):
        self.poi_id = poi_id
        self.name = name
        self.description = description  # 基本的な説明（未調査時に見える）
        self.detailed_description = detailed_description  # 詳細な説明（調査後に見える）
        self.unlock_condition = unlock_condition or POIUnlockCondition()
        
        self.items: List[Item] = []  # このPOIから入手可能なアイテム
        self.hidden_monsters: List[Monster] = []  # このPOIから出現する可能性のあるモンスター
        self.unlocks_pois: List[str] = []  # このPOIの調査により解放される他のPOIのID
        
    def add_item(self, item: Item):
        """POIにアイテムを追加"""
        self.items.append(item)
        
    def add_hidden_monster(self, monster: Monster):
        """POIに隠れているモンスターを追加"""
        self.hidden_monsters.append(monster)
        
    def add_unlockable_poi(self, poi_id: str):
        """このPOIの調査により解放されるPOIを追加"""
        self.unlocks_pois.append(poi_id)
        
    def is_accessible(self, player: 'Player', discovered_pois: Set[str]) -> bool:
        """プレイヤーがこのPOIにアクセス可能か判定"""
        return self.unlock_condition.is_satisfied(player, discovered_pois)
        
    def get_discovery_result(self) -> Dict:
        """POIの調査結果を返す"""
        return {
            'description': self.detailed_description,
            'items': self.items.copy(),
            'monsters': self.hidden_monsters.copy(),
            'unlocks_pois': self.unlocks_pois.copy()
        }