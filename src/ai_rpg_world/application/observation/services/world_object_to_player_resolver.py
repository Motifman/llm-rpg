"""WorldObjectId → PlayerId 解決の実装（PhysicalMapRepository 利用）"""

from typing import Optional

from ai_rpg_world.application.observation.contracts.interfaces import (
    IWorldObjectToPlayerResolver,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class WorldObjectToPlayerResolver(IWorldObjectToPlayerResolver):
    """
    PhysicalMapRepository を用いて WorldObjectId に紐づくプレイヤーIDを解決する。
    観測配信先解決（マップ系イベント）で共通利用する。
    """

    def __init__(self, physical_map_repository: PhysicalMapRepository) -> None:
        self._physical_map_repository = physical_map_repository

    def resolve_player_id(self, object_id: WorldObjectId) -> Optional[PlayerId]:
        """WorldObjectId に紐づくプレイヤーIDを返す。プレイヤーでなければ None。"""
        spot_id = self._physical_map_repository.find_spot_id_by_object_id(object_id)
        if spot_id is None:
            return None
        physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
        if physical_map is None:
            return None
        try:
            obj = physical_map.get_object(object_id)
        except ObjectNotFoundException:
            return None
        return obj.player_id
