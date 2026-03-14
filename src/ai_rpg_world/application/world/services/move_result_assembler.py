"""MoveResultAssembler: 移動結果 DTO の組み立てを担当するアプリケーションサービス。"""

from datetime import datetime
from typing import Optional

from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.application.world.contracts.dtos import MoveResultDto
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    PlayerNotFoundException,
    MapNotFoundException,
)


class MoveResultAssembler:
    """MoveResultDto の組み立てを担当するアプリケーションサービス。"""

    def __init__(
        self,
        player_profile_repository: PlayerProfileRepository,
        spot_repository: SpotRepository,
    ):
        self._player_profile_repository = player_profile_repository
        self._spot_repository = spot_repository

    def create_success(
        self,
        player_status: PlayerStatusAggregate,
        from_spot_id: SpotId,
        from_coord: Coordinate,
        to_coord: Coordinate,
        arrival_tick: int,
        message: str,
    ) -> MoveResultDto:
        """
        移動成功時の DTO を組み立てる。

        Raises:
            PlayerNotFoundException: プロフィールが存在しない場合
            MapNotFoundException: スポットが存在しない場合
        """
        profile = self._player_profile_repository.find_by_id(player_status.player_id)
        if not profile:
            raise PlayerNotFoundException(int(player_status.player_id))
        player_name = profile.name.value

        from_spot = self._spot_repository.find_by_id(from_spot_id)
        if not from_spot:
            raise MapNotFoundException(int(from_spot_id))
        from_spot_name = from_spot.name

        to_spot = self._spot_repository.find_by_id(player_status.current_spot_id)
        if not to_spot:
            raise MapNotFoundException(int(player_status.current_spot_id))
        to_spot_name = to_spot.name

        return MoveResultDto(
            success=True,
            player_id=int(player_status.player_id),
            player_name=player_name,
            from_spot_id=int(from_spot_id),
            from_spot_name=from_spot_name,
            to_spot_id=int(player_status.current_spot_id),
            to_spot_name=to_spot_name,
            from_coordinate={"x": from_coord.x, "y": from_coord.y, "z": from_coord.z},
            to_coordinate={"x": to_coord.x, "y": to_coord.y, "z": to_coord.z},
            moved_at=datetime.now(),
            busy_until_tick=arrival_tick,
            message=message,
        )

    def create_failure(
        self,
        player_id_int: int,
        message: str,
        player_status: Optional[PlayerStatusAggregate] = None,
    ) -> MoveResultDto:
        """移動失敗時の DTO を組み立てる。player_status が None の場合は最小限の情報で構築。"""
        player_id = PlayerId(player_id_int)
        player_name = ""
        from_spot_id = 0
        from_spot_name = ""
        to_spot_id = 0
        to_spot_name = ""
        from_coord_dict = {"x": 0, "y": 0, "z": 0}
        to_coord_dict = {"x": 0, "y": 0, "z": 0}

        if player_status:
            profile = self._player_profile_repository.find_by_id(player_id)
            if profile:
                player_name = profile.name.value

            if player_status.current_spot_id:
                from_spot_id = int(player_status.current_spot_id)
                to_spot_id = from_spot_id
                spot = self._spot_repository.find_by_id(player_status.current_spot_id)
                if spot:
                    from_spot_name = spot.name
                    to_spot_name = spot.name

            if player_status.current_coordinate:
                c = player_status.current_coordinate
                from_coord_dict = {"x": c.x, "y": c.y, "z": c.z}
                to_coord_dict = from_coord_dict

        return MoveResultDto(
            success=False,
            player_id=player_id_int,
            player_name=player_name,
            from_spot_id=from_spot_id,
            from_spot_name=from_spot_name,
            to_spot_id=to_spot_id,
            to_spot_name=to_spot_name,
            from_coordinate=from_coord_dict,
            to_coordinate=to_coord_dict,
            moved_at=datetime.now(),
            busy_until_tick=0,
            message="移動失敗",
            error_message=message,
        )
