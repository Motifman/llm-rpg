from dataclasses import dataclass
from datetime import datetime


@dataclass
class MovementResult:
    """プレイヤー移動結果を表すクラス"""
    
    player_id: int
    player_name: str
    from_spot_id: int
    from_spot_name: str
    to_spot_id: int
    to_spot_name: str
    road_id: int
    road_description: str
    moved_at: datetime
    distance: float = 1.0  # デフォルト距離
    
    def get_move_summary(self) -> str:
        """移動概要を取得"""
        return f"{self.player_name}が{self.from_spot_name}から{self.to_spot_name}に{self.road_description}を通って移動しました（距離: {self.distance}）"
