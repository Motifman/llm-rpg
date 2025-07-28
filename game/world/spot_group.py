from typing import List, Dict, Set, Optional
from dataclasses import dataclass
from game.world.spot import Spot
from game.world.movement_graph import MovementGraph


@dataclass
class SpotGroupConfig:
    """SpotGroupの設定を定義するデータクラス"""
    group_id: str
    name: str
    description: str
    spot_ids: List[str]
    entrance_spot_ids: List[str] = None
    exit_spot_ids: List[str] = None
    tags: List[str] = None


class SpotGroup:
    """特定の役割を持つSpotの集合を管理するクラス"""
    
    def __init__(self, config: SpotGroupConfig):
        self.config = config
        self.group_id = config.group_id  # group_id属性を追加
        self.spots: Dict[str, Spot] = {}
        self.entrance_spots: Dict[str, Spot] = {}
        self.exit_spots: Dict[str, Spot] = {}
        self.tags: Set[str] = set(config.tags or [])
    
    def add_spot(self, spot: Spot):
        """Spotをグループに追加"""
        if spot.spot_id in self.config.spot_ids:
            self.spots[spot.spot_id] = spot
            
            # 入り口スポットかチェック
            if self.config.entrance_spot_ids and spot.spot_id in self.config.entrance_spot_ids:
                self.entrance_spots[spot.spot_id] = spot
            
            # 出口スポットかチェック
            if self.config.exit_spot_ids and spot.spot_id in self.config.exit_spot_ids:
                self.exit_spots[spot.spot_id] = spot
    
    def get_spot(self, spot_id: str) -> Optional[Spot]:
        """指定されたIDのSpotを取得"""
        return self.spots.get(spot_id)
    
    def get_all_spots(self) -> List[Spot]:
        """グループ内の全てのSpotを取得"""
        return list(self.spots.values())
    
    def get_entrance_spots(self) -> List[Spot]:
        """入り口スポットを取得"""
        return list(self.entrance_spots.values())
    
    def get_exit_spots(self) -> List[Spot]:
        """出口スポットを取得"""
        return list(self.exit_spots.values())
    
    def get_entrance_spot_ids(self) -> List[str]:
        """入り口スポットのIDリストを取得"""
        return list(self.entrance_spots.keys())
    
    def get_exit_spot_ids(self) -> List[str]:
        """出口スポットのIDリストを取得"""
        return list(self.exit_spots.keys())
    
    def has_spot(self, spot_id: str) -> bool:
        """指定されたSpotがグループに含まれているかチェック"""
        return spot_id in self.spots
    
    def is_entrance_spot(self, spot_id: str) -> bool:
        """指定されたSpotが入り口かチェック"""
        return spot_id in self.entrance_spots
    
    def is_exit_spot(self, spot_id: str) -> bool:
        """指定されたSpotが出口かチェック"""
        return spot_id in self.exit_spots
    
    def has_tag(self, tag: str) -> bool:
        """指定されたタグを持つかチェック"""
        return tag in self.tags
    
    def get_tags(self) -> List[str]:
        """グループのタグリストを取得"""
        return list(self.tags)
    
    def get_description(self) -> str:
        """グループの説明を取得"""
        return f"{self.config.name}: {self.config.description}"
    
    def get_summary(self) -> str:
        """グループの概要を取得"""
        summary = f"=== {self.config.name} ===\n"
        summary += f"{self.config.description}\n"
        summary += f"スポット数: {len(self.spots)}\n"
        if self.entrance_spots:
            summary += f"入り口: {', '.join(self.entrance_spots.keys())}\n"
        if self.exit_spots:
            summary += f"出口: {', '.join(self.exit_spots.keys())}\n"
        if self.tags:
            summary += f"タグ: {', '.join(self.tags)}\n"
        return summary 