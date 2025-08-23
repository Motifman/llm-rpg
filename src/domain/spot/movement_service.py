from datetime import datetime
from src.domain.spot.spot import Spot
from src.domain.spot.road import Road
from src.domain.player.player import Player
from src.domain.spot.movement_result import MovementResult
from src.domain.spot.spot_exception import (
    PlayerNotMeetConditionException,
    PlayerAlreadyInToSpotException,
    PlayerNotInFromSpotException,
    SpotNotConnectedException,
    RoadNotConnectedToFromSpotException,
    RoadNotConnectedToToSpotException,
)


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
            
        Raises:
            PlayerNotInFromSpotException: プレイヤーが移動元スポットにいない場合
            PlayerAlreadyInToSpotException: プレイヤーが既に移動先スポットにいる場合
            SpotNotConnectedException: スポット間が接続されていない場合
            RoadNotConnectedToFromSpotException: 道路が移動元スポットに接続されていない場合
            RoadNotConnectedToToSpotException: 道路が移動先スポットに接続されていない場合
            PlayerNotMeetConditionException: プレイヤーが道路の条件を満たしていない場合
        """
        # バリデーション
        if player.current_spot_id != from_spot.spot_id:
            raise PlayerNotInFromSpotException(f"Player {player.player_id} is not in the from spot {from_spot.spot_id}")
        if player.current_spot_id == to_spot.spot_id:
            raise PlayerAlreadyInToSpotException(f"Player {player.player_id} is already in the spot {to_spot.spot_id}")
        if not from_spot.is_connected_to(to_spot):
            raise SpotNotConnectedException(f"from_spot {from_spot.spot_id} is not connected to to_spot {to_spot.spot_id}")
        if road.from_spot_id != from_spot.spot_id:
            raise RoadNotConnectedToFromSpotException(f"road.from_spot_id {road.from_spot_id} is not equal to from_spot.spot_id {from_spot.spot_id}")
        if road.to_spot_id != to_spot.spot_id:
            raise RoadNotConnectedToToSpotException(f"road.to_spot_id {road.to_spot_id} is not equal to to_spot.spot_id {to_spot.spot_id}")
        if not road.is_available(player):
            availability_message = road.get_availability_message(player)
            raise PlayerNotMeetConditionException(f"road {road.road_id} is not available for the player {player.player_id}: {availability_message}")
        
        # 移動実行
        player.set_current_spot_id(to_spot.spot_id)
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