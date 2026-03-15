"""プレイヤー位置取得クエリサービス"""

from typing import Optional

from ai_rpg_world.application.world.contracts.queries import GetPlayerLocationQuery
from ai_rpg_world.application.world.contracts.dtos import PlayerLocationDto
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    PlayerNotFoundException,
    MapNotFoundException,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.repository.player_profile_repository import (
    PlayerProfileRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)
from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository


class PlayerLocationQueryService:
    """
    プレイヤーの現在位置を取得するクエリサービス。

    WorldQueryService の _get_player_location_impl から切り出した責務を担当する。
    プレイヤー未配置時は None、プロフィール／スポット不在時は例外を送出する。
    """

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

    def get_player_location(
        self, query: GetPlayerLocationQuery
    ) -> Optional[PlayerLocationDto]:
        """
        プレイヤーの現在位置を取得する。

        未配置時は None、プロフィール不在時は PlayerNotFoundException、
        スポット不在時は MapNotFoundException を送出する。
        """
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

        areas = []
        physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
        if physical_map:
            areas = physical_map.get_location_areas_at(coord)
        area_ids = [int(la.location_id) for la in areas]
        area_names = [la.name for la in areas]
        area_id = area_ids[0] if area_ids else None
        area_name = area_names[0] if area_names else None

        return PlayerLocationDto(
            player_id=query.player_id,
            player_name=player_name,
            current_spot_id=int(spot_id),
            current_spot_name=spot_name,
            current_spot_description=spot_desc,
            x=coord.x,
            y=coord.y,
            z=coord.z,
            area_ids=area_ids,
            area_names=area_names,
            area_id=area_id,
            area_name=area_name,
        )
