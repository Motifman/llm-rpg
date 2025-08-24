from datetime import datetime
from src.domain.spot.spot import Spot
from src.domain.spot.road import Road
from src.domain.player.player import Player
from src.domain.spot.movement_result import MovementResult


class MovementService:
    def __init__(self):
        pass
    
    def move_player_to_spot(self, player: Player, from_spot: Spot, to_spot: Spot, road: Road) -> MovementResult:
        """プレイヤーをスポット間で移動させる
        
        Args:
            player: 移動するプレイヤー
            from_spot: 移動元スポット
            to_spot: 移動先スポット
            road: 使用する道路
            
        Returns:
            MoveResult: 移動結果
        """
        # バリデーション
        road.check_player_conditions(player)
        
        # 移動実行
        player.move_to_spot(to_spot.spot_id)
        from_spot.remove_player(player.player_id)
        to_spot.add_player(player.player_id)
        
        # 移動結果を返却
        return MovementResult(
            player_id=player.player_id,
            player_name=player.name,
            from_spot_id=from_spot.spot_id,
            from_spot_name=from_spot.name,
            to_spot_id=to_spot.spot_id,
            to_spot_name=to_spot.name,
            road_id=road.road_id,
            road_description=road.description,
            moved_at=datetime.now()
        )