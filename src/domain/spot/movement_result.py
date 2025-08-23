from dataclasses import dataclass
from datetime import datetime
from src.domain.spot.spot import Spot
from src.domain.spot.road import Road


@dataclass
class MovementResult:
    """移動結果"""
    player_id: int
    player_name: str
    from_spot_id: int
    from_spot_name: str
    to_spot_id: int
    to_spot_name: str
    road_id: int
    road_description: str
    moved_at: datetime
    distance: int = 1  # 現在は隣接スポットのみなので1固定
    
    def get_move_summary(self) -> str:
        """移動の概要を取得"""
        return f"{self.player_name}が{self.from_spot_name}から{self.to_spot_name}に移動しました"
    
    def get_detailed_move_info(self) -> str:
        """詳細な移動情報を取得"""
        return (
            f"プレイヤー: {self.player_name} (ID: {self.player_id})\n"
            f"移動経路: {self.from_spot_name} (ID: {self.from_spot_id}) → {self.to_spot_name} (ID: {self.to_spot_id})\n"
            f"使用道路: {self.road_description} (ID: {self.road_id})\n"
            f"移動距離: {self.distance}\n"
            f"移動時刻: {self.moved_at.strftime('%Y-%m-%d %H:%M:%S')}"
        )
