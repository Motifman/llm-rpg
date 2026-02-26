"""ワールドクエリサービス（読み取り専用の位置情報等）"""

import logging
from typing import Optional, Callable, Any

from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
from ai_rpg_world.application.world.contracts.queries import GetPlayerLocationQuery
from ai_rpg_world.application.world.contracts.dtos import PlayerLocationDto
from ai_rpg_world.application.world.exceptions.base_exception import WorldApplicationException, WorldSystemErrorException
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    MovementCommandException,
    PlayerNotFoundException,
    MapNotFoundException,
)


class WorldQueryService:
    """ワールドに関する読み取り専用クエリを提供するサービス"""

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        player_profile_repository: PlayerProfileRepository,
        physical_map_repository: PhysicalMapRepository,
        spot_repository: SpotRepository,
    ):
        self._player_status_repository = player_status_repository
        self._player_profile_repository = player_profile_repository
        self._physical_map_repository = physical_map_repository
        self._spot_repository = spot_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(self, operation: Callable[[], Any], context: dict) -> Any:
        """共通の例外処理を実行"""
        try:
            return operation()
        except WorldApplicationException:
            raise
        except DomainException as e:
            raise MovementCommandException(str(e), player_id=context.get("player_id"))
        except Exception as e:
            self._logger.error(
                "Unexpected error in %s: %s",
                context.get("action", "unknown"),
                str(e),
                extra=context,
            )
            raise WorldSystemErrorException(
                f"{context.get('action', 'unknown')} failed: {str(e)}",
                original_exception=e,
            )

    def get_player_location(self, query: GetPlayerLocationQuery) -> Optional[PlayerLocationDto]:
        """プレイヤーの現在位置を取得。未配置の場合は None、プレイヤー／スポット不在時は例外。"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_player_location_impl(query),
            context={"action": "get_player_location", "player_id": query.player_id},
        )

    def _get_player_location_impl(self, query: GetPlayerLocationQuery) -> Optional[PlayerLocationDto]:
        """プレイヤーの現在位置を取得する実装。未配置時は None を返す。"""
        player_id = PlayerId(query.player_id)
        player_status = self._player_status_repository.find_by_id(player_id)
        if not player_status or not player_status.current_spot_id or not player_status.current_coordinate:
            return None

        spot_id = player_status.current_spot_id
        coord = player_status.current_coordinate

        profile = self._player_profile_repository.find_by_id(player_id)
        if not profile:
            raise PlayerNotFoundException(query.player_id)
        player_name = profile.name.value

        spot = self._spot_repository.find_by_id(spot_id)
        if not spot:
            raise MapNotFoundException(int(spot_id))
        spot_name = spot.name
        spot_desc = spot.description

        area_id = None
        area_name = None
        physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
        if physical_map:
            areas = physical_map.get_location_areas_at(coord)
            if areas:
                area_id = int(areas[0].location_id)
                area_name = areas[0].name

        return PlayerLocationDto(
            player_id=query.player_id,
            player_name=player_name,
            current_spot_id=int(spot_id),
            current_spot_name=spot_name,
            current_spot_description=spot_desc,
            x=coord.x,
            y=coord.y,
            z=coord.z,
            area_id=area_id,
            area_name=area_name,
        )
