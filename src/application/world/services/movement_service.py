from typing import Optional, List
from datetime import datetime
from src.application.world.contracts.commands import (
    MovePlayerCommand,
    GetPlayerLocationCommand,
    GetSpotInfoCommand
)
from src.application.world.contracts.dtos import (
    MoveResultDto,
    PlayerLocationDto,
    SpotInfoDto,
    AvailableMoveDto,
    PlayerMovementOptionsDto
)
from src.domain.spot.movement_service import MovementService
from src.domain.player.player_repository import PlayerRepository
from src.domain.spot.spot_repository import SpotRepository
from src.domain.spot.road_repository import RoadRepository
from src.domain.spot.spot_exception import (
    PlayerNotMeetConditionException,
    PlayerAlreadyInSpotException,
    PlayerNotInSpotException,
    SpotNotConnectedException,
    RoadNotConnectedToFromSpotException,
    RoadNotConnectedToToSpotException,
)


class MovementApplicationService:
    """移動アプリケーションサービス"""
    
    def __init__(
        self,
        move_service: MovementService,
        player_repository: PlayerRepository,
        spot_repository: SpotRepository,
        road_repository: RoadRepository
    ):
        self._move_service = move_service
        self._player_repository = player_repository
        self._spot_repository = spot_repository
        self._road_repository = road_repository
    
    def move_player(self, command: MovePlayerCommand) -> MoveResultDto:
        """プレイヤーを移動させる
        
        Args:
            command: 移動コマンド
            
        Returns:
            MoveResultDto: 移動結果
            
        Raises:
            ValueError: プレイヤーまたはスポットが見つからない場合
        """
        # 1. エンティティを取得
        player = self._player_repository.find_by_id(command.player_id)
        if not player:
            raise ValueError(f"Player not found: {command.player_id}")
        
        to_spot = self._spot_repository.find_by_id(command.to_spot_id)
        if not to_spot:
            raise ValueError(f"Destination spot not found: {command.to_spot_id}")
        
        from_spot = self._spot_repository.find_by_id(player.current_spot_id)
        if not from_spot:
            raise ValueError(f"Current spot not found: {player.current_spot_id}")
        
        road = self._road_repository.find_between_spots(from_spot.spot_id, to_spot.spot_id)
        if not road:
            raise ValueError(f"Road not found between spots {from_spot.spot_id} and {to_spot.spot_id}")
        
        try:
            # 3. ドメインサービスで移動実行
            move_result = self._move_service.move_player_to_spot(player, from_spot, to_spot, road)
            
            # 4. エンティティを保存
            self._player_repository.save(player)
            self._spot_repository.save(from_spot)
            self._spot_repository.save(to_spot)
            self._road_repository.save(road)
            
            # 5. DTOに変換して返却
            return MoveResultDto(
                success=True,
                player_id=move_result.player_id,
                player_name=move_result.player_name,
                from_spot_id=move_result.from_spot_id,
                from_spot_name=move_result.from_spot_name,
                to_spot_id=move_result.to_spot_id,
                to_spot_name=move_result.to_spot_name,
                road_id=move_result.road_id,
                road_description=move_result.road_description,
                moved_at=move_result.moved_at,
                distance=move_result.distance,
                message=move_result.get_move_summary()
            )
            
        except (PlayerNotMeetConditionException, PlayerAlreadyInSpotException,
                PlayerNotInSpotException, SpotNotConnectedException,
                RoadNotConnectedToFromSpotException, RoadNotConnectedToToSpotException) as e:
            return MoveResultDto(
                success=False,
                player_id=player.player_id,
                player_name=player.name,
                from_spot_id=from_spot.spot_id,
                from_spot_name=from_spot.name,
                to_spot_id=to_spot.spot_id,
                to_spot_name=to_spot.name,
                road_id=road.road_id if road else 0,
                road_description=road.description if road else "",
                moved_at=datetime.now(),
                distance=0,
                message="移動に失敗しました",
                error_message=str(e)
            )
    
    def get_player_location(self, command: GetPlayerLocationCommand) -> Optional[PlayerLocationDto]:
        """プレイヤーの現在位置を取得"""
        player = self._player_repository.find_by_id(command.player_id)
        if not player:
            return None
        
        current_spot = self._spot_repository.find_by_id(player.current_spot_id)
        if not current_spot:
            return None
        
        # エリア情報は将来的に実装
        area_name = None
        
        return PlayerLocationDto(
            player_id=player.player_id,
            player_name=player.name,
            current_spot_id=current_spot.spot_id,
            current_spot_name=current_spot.name,
            current_spot_description=current_spot.description,
            area_id=getattr(current_spot, '_area_id', None),
            area_name=area_name
        )
    
    def get_spot_info(self, command: GetSpotInfoCommand) -> Optional[SpotInfoDto]:
        """スポット情報を取得"""
        spot = self._spot_repository.find_by_id(command.spot_id)
        if not spot:
            return None
        
        # エリア情報は将来的に実装
        area_name = None
        
        # 接続情報をリポジトリから取得
        connected_spots = self._spot_repository.find_connected_spots(spot.spot_id)
        connected_spot_ids = [spot.spot_id for spot in connected_spots]
        connected_spot_names = [spot.name for spot in connected_spots]
        
        return SpotInfoDto(
            spot_id=spot.spot_id,
            name=spot.name,
            description=spot.description,
            area_id=getattr(spot, '_area_id', None),
            area_name=area_name,
            current_player_count=spot.get_current_player_count(),
            current_player_ids=spot.get_current_player_ids(),
            connected_spot_ids=connected_spot_ids,
            connected_spot_names=connected_spot_names
        )
    
    def get_player_movement_options(self, player_id: int) -> Optional[PlayerMovementOptionsDto]:
        """プレイヤーの移動オプションを取得"""
        player = self._player_repository.find_by_id(player_id)
        if not player:
            return None
        
        current_spot = self._spot_repository.find_by_id(player.current_spot_id)
        if not current_spot:
            return None
        
        available_moves = []
        
        # 接続されているスポットをリポジトリから取得
        connected_spot_ids = self._road_repository.find_connected_spot_ids(current_spot.spot_id)
        
        for to_spot_id in connected_spot_ids:
            to_spot = self._spot_repository.find_by_id(to_spot_id)
            if not to_spot:
                continue
            
            # 道路情報をリポジトリから取得
            road = self._road_repository.find_between_spots(current_spot.spot_id, to_spot_id)
            if not road:
                continue
            
            available_moves.append(AvailableMoveDto(
                spot_id=to_spot.spot_id,
                spot_name=to_spot.name,
                road_id=road.road_id,
                road_description=road.description,
                conditions_met=True,  # 条件チェックは移動時に実行されるため、ここでは常にTrue
                failed_conditions=[]  # 条件チェックは移動時に実行されるため、ここでは空リスト
            ))
        
        return PlayerMovementOptionsDto(
            player_id=player.player_id,
            player_name=player.name,
            current_spot_id=current_spot.spot_id,
            current_spot_name=current_spot.name,
            available_moves=available_moves,
            total_available_moves=len(available_moves)  # すべての接続先を利用可能として扱う
        )