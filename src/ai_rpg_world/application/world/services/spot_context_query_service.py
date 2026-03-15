"""スポット文脈取得クエリサービス"""

from typing import Optional

from ai_rpg_world.application.world.contracts.queries import GetSpotContextForPlayerQuery
from ai_rpg_world.application.world.contracts.dtos import SpotInfoDto
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    PlayerNotFoundException,
    MapNotFoundException,
)
from ai_rpg_world.application.common.interfaces import IPlayerAudienceQueryPort
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
from ai_rpg_world.domain.world.repository.connected_spots_provider import (
    IConnectedSpotsProvider,
)


class SpotContextQueryService:
    """
    プレイヤーの現在スポット情報＋接続先一覧を取得するクエリサービス。

    WorldQueryService の _get_spot_context_for_player_impl から切り出した責務を担当する。
    未配置時は None、プロフィール／スポット不在時は例外を送出する。
    """

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        player_profile_repository: PlayerProfileRepository,
        physical_map_repository: PhysicalMapRepository,
        spot_repository: SpotRepository,
        connected_spots_provider: IConnectedSpotsProvider,
        player_audience_query: IPlayerAudienceQueryPort,
    ):
        self._player_status_repository = player_status_repository
        self._player_profile_repository = player_profile_repository
        self._physical_map_repository = physical_map_repository
        self._spot_repository = spot_repository
        self._connected_spots_provider = connected_spots_provider
        self._player_audience_query = player_audience_query

    def get_spot_context(
        self, query: GetSpotContextForPlayerQuery
    ) -> Optional[SpotInfoDto]:
        """
        プレイヤーの現在スポット情報＋接続先一覧を取得する。

        未配置時は None、プロフィール不在時は PlayerNotFoundException、
        スポット不在時は MapNotFoundException を送出する。
        """
        player_id = PlayerId(query.player_id)
        player_status = self._player_status_repository.find_by_id(player_id)
        if (
            not player_status
            or not player_status.current_spot_id
            or not player_status.current_coordinate
        ):
            return None

        spot_id = player_status.current_spot_id
        coord = player_status.current_coordinate

        profile = self._player_profile_repository.find_by_id(player_id)
        if not profile:
            raise PlayerNotFoundException(query.player_id)

        spot = self._spot_repository.find_by_id(spot_id)
        if not spot:
            raise MapNotFoundException(int(spot_id))

        areas = []
        physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
        if physical_map:
            areas = physical_map.get_location_areas_at(coord)
        area_ids = [int(la.location_id) for la in areas]
        area_names = [la.name for la in areas]
        area_id = area_ids[0] if area_ids else None
        area_name = area_names[0] if area_names else None

        player_ids_at_spot = self._player_audience_query.players_at_spot(spot_id)
        current_player_ids = {int(p.value) for p in player_ids_at_spot}
        current_player_count = len(current_player_ids)

        connected_spot_ids: set = set()
        connected_spot_names: set = set()
        for conn_id in self._connected_spots_provider.get_connected_spots(spot_id):
            connected_spot_ids.add(int(conn_id))
            conn_spot = self._spot_repository.find_by_id(conn_id)
            if conn_spot:
                connected_spot_names.add(conn_spot.name)

        return SpotInfoDto(
            spot_id=int(spot_id),
            name=spot.name,
            description=spot.description,
            area_id=area_id,
            area_name=area_name,
            current_player_count=current_player_count,
            current_player_ids=current_player_ids,
            connected_spot_ids=connected_spot_ids,
            connected_spot_names=connected_spot_names,
            area_ids=area_ids,
            area_names=area_names,
        )
