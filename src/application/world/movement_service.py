from typing import Optional, List
from datetime import datetime
from src.application.world.commands import (
    MovePlayerCommand,
    GetPlayerLocationCommand,
    GetSpotInfoCommand
)
from src.application.world.dtos import (
    MoveResultDto,
    PlayerLocationDto,
    SpotInfoDto,
    AvailableMoveDto,
    PlayerMovementOptionsDto
)
from src.domain.spot.movement_service import MovementService
from src.domain.player.player_repository import PlayerRepository
from src.domain.spot.spot_repository import SpotRepository
from src.domain.spot.spot_exception import (
    PlayerNotMeetConditionException,
    PlayerAlreadyInToSpotException,
    PlayerNotInFromSpotException,
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
        spot_repository: SpotRepository
    ):
        self._move_service = move_service
        self._player_repository = player_repository
        self._spot_repository = spot_repository
    
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
        
        # 2. 道路を取得
        road = self._find_road_between_spots(from_spot, to_spot)
        if not road:
            return MoveResultDto(
                success=False,
                player_id=player.player_id,
                player_name=player.name,
                from_spot_id=from_spot.spot_id,
                from_spot_name=from_spot.name,
                to_spot_id=to_spot.spot_id,
                to_spot_name=to_spot.name,
                road_id=0,
                road_description="",
                moved_at=datetime.now(),
                distance=0,
                message="移動に失敗しました",
                error_message=f"スポット {from_spot.spot_id} と {to_spot.spot_id} の間に道路がありません"
            )
        
        try:
            # 3. ドメインサービスで移動実行
            move_result = self._move_service.move_player_to_spot(player, from_spot, to_spot, road)
            
            # 4. エンティティを保存
            self._player_repository.save(player)
            self._spot_repository.save(from_spot)
            self._spot_repository.save(to_spot)
            
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
            
        except (PlayerNotMeetConditionException, PlayerAlreadyInToSpotException,
                PlayerNotInFromSpotException, SpotNotConnectedException,
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
        
        return SpotInfoDto(
            spot_id=spot.spot_id,
            name=spot.name,
            description=spot.description,
            area_id=getattr(spot, '_area_id', None),
            area_name=area_name,
            current_player_count=spot.get_current_player_count(),
            current_player_ids=spot.get_current_player_ids(),
            connected_spot_ids=spot.get_connected_spot_ids(),
            connected_spot_names=spot.get_connected_spot_names()
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
        
        # 接続されているスポットをチェック
        for road in current_spot.get_all_roads():
            to_spot = self._spot_repository.find_by_id(road.to_spot_id)
            if not to_spot:
                continue
            
            # 道路の条件をチェック
            conditions_met = road.is_available(player)
            failed_conditions = []
            
            if not conditions_met:
                # 失敗した条件の詳細を取得
                availability_details = road._check_availability_details(player)
                failed_conditions = [
                    f"{result.condition.condition_type.value}: {result.message}"
                    for result in availability_details["failed_conditions"]
                ]
            
            available_moves.append(AvailableMoveDto(
                spot_id=to_spot.spot_id,
                spot_name=to_spot.name,
                road_id=road.road_id,
                road_description=road.description,
                conditions_met=conditions_met,
                failed_conditions=failed_conditions
            ))
        
        return PlayerMovementOptionsDto(
            player_id=player.player_id,
            player_name=player.name,
            current_spot_id=current_spot.spot_id,
            current_spot_name=current_spot.name,
            available_moves=available_moves,
            total_available_moves=len([m for m in available_moves if m.conditions_met])
        )
    
    def _find_road_between_spots(self, from_spot, to_spot):
        """2つのスポット間の道路を検索"""
        for road in from_spot.get_all_roads():
            if road.to_spot_id == to_spot.spot_id:
                return road
        return None
