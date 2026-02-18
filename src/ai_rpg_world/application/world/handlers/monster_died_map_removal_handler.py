"""
MonsterDiedEvent を受けて、死亡したモンスターの WorldObject をマップから削除するハンドラ（Phase 6）
"""

import logging

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.monster.event.monster_events import MonsterDiedEvent
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository


class MonsterDiedMapRemovalHandler(EventHandler[MonsterDiedEvent]):
    """モンスター死亡イベントで、該当する WorldObject を物理マップから削除するハンドラ"""

    def __init__(
        self,
        physical_map_repository: PhysicalMapRepository,
        monster_repository: MonsterRepository,
        unit_of_work: UnitOfWork,
    ):
        self._physical_map_repository = physical_map_repository
        self._monster_repository = monster_repository
        self._unit_of_work = unit_of_work
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: MonsterDiedEvent) -> None:
        try:
            self._handle_impl(event)
        except (ApplicationException, DomainException):
            raise
        except Exception as e:
            self._logger.exception("Unexpected error in MonsterDiedMapRemovalHandler: %s", e)
            raise SystemErrorException(
                f"Monster died map removal failed: {e}",
                original_exception=e,
            ) from e

    def _handle_impl(self, event: MonsterDiedEvent) -> None:
        if event.spot_id is None:
            return

        physical_map = self._physical_map_repository.find_by_spot_id(event.spot_id)
        if not physical_map:
            self._logger.debug(
                "Map not found for spot %s (expected if stale), skipping map removal",
                event.spot_id,
            )
            return

        monster = self._monster_repository.find_by_id(event.aggregate_id)
        if not monster:
            self._logger.debug(
                "Dead monster %s not found, skipping map removal",
                event.aggregate_id,
            )
            return

        world_object_id = monster.world_object_id
        try:
            physical_map.remove_object(world_object_id)
        except ObjectNotFoundException:
            self._logger.debug(
                "Object %s already removed from map (expected if duplicate event), skipping",
                world_object_id,
            )
            return

        self._physical_map_repository.save(physical_map)
        self._logger.debug(
            "Removed dead monster world object %s from map spot %s",
            world_object_id,
            event.spot_id,
        )
