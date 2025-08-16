from src.domain.spot.spot import Spot
from src.domain.spot.road import Road
from src.domain.player.player import Player
from src.domain.spot.spot_exception import (
    PlayerNotMeetConditionException,
    PlayerAlreadyInToSpotException,
    PlayerNotInFromSpotException,
    SpotNotConnectedException,
    RoadNotConnectedToFromSpotException,
    RoadNotConnectedToToSpotException,
)


class MoveService:
    def __init__(self):
        pass
    
    def move_player_to_spot(self, player: Player, from_spot: Spot, to_spot: Spot, road: Road):
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
        player.set_current_spot_id(to_spot.spot_id)
        from_spot.remove_player(player.player_id)
        to_spot.add_player(player.player_id)