"""視界・可視オブジェクト取得クエリサービス"""

from typing import Optional, TYPE_CHECKING

from ai_rpg_world.application.world.contracts.queries import GetVisibleContextQuery
from ai_rpg_world.application.world.contracts.dtos import VisibleContextDto
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
from ai_rpg_world.application.world.services.visible_object_read_model_builder import (
    VisibleObjectReadModelBuilder,
)

if TYPE_CHECKING:
    from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository


class VisibleContextQueryService:
    """
    視界・可視オブジェクト取得クエリサービス。

    WorldQueryService の _get_visible_context_impl から切り出した責務を担当する。
    未配置時は None、プロフィール／スポット／マップ不在時は例外を送出する。
    """

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        player_profile_repository: PlayerProfileRepository,
        physical_map_repository: PhysicalMapRepository,
        spot_repository: SpotRepository,
        monster_repository: Optional["MonsterRepository"] = None,
    ):
        self._player_status_repository = player_status_repository
        self._player_profile_repository = player_profile_repository
        self._physical_map_repository = physical_map_repository
        self._spot_repository = spot_repository
        self._visible_object_builder = VisibleObjectReadModelBuilder(
            player_profile_repository=player_profile_repository,
            monster_repository=monster_repository,
        )

    def get_visible_context(
        self, query: GetVisibleContextQuery
    ) -> Optional[VisibleContextDto]:
        """
        プレイヤー視点の視界内オブジェクトを取得する。

        未配置時は None、プロフィール不在時は PlayerNotFoundException、
        スポット／マップ不在時は MapNotFoundException を送出する。
        """
        player_id = PlayerId(query.player_id)
        player_status = self._player_status_repository.find_by_id(player_id)
        if (
            not player_status
            or not player_status.current_spot_id
            or not player_status.current_coordinate
        ):
            return None

        profile = self._player_profile_repository.find_by_id(player_id)
        if not profile:
            raise PlayerNotFoundException(query.player_id)

        spot_id = player_status.current_spot_id
        coord = player_status.current_coordinate
        physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
        if not physical_map:
            raise MapNotFoundException(int(spot_id))

        spot = self._spot_repository.find_by_id(spot_id)
        if not spot:
            raise MapNotFoundException(int(spot_id))

        distance = max(0, query.distance)
        return self._visible_object_builder.build_visible_context(
            player_id=query.player_id,
            player_name=profile.name.value,
            spot=spot,
            physical_map=physical_map,
            origin=coord,
            view_distance=distance,
        )
