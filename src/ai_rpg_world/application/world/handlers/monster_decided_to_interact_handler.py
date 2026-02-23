"""MonsterDecidedToInteractEvent を購読し、マップ上でインタラクション（採食等）を実行するハンドラ。"""

import logging

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.monster.event.monster_events import MonsterDecidedToInteractEvent
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository


class MonsterDecidedToInteractHandler(EventHandler[MonsterDecidedToInteractEvent]):
    """MonsterDecidedToInteractEvent を受けて physical_map.interact_with を実行する。"""

    def __init__(self, physical_map_repository: PhysicalMapRepository):
        self._physical_map_repository = physical_map_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: MonsterDecidedToInteractEvent) -> None:
        try:
            self._handle_impl(event)
        except (ApplicationException, DomainException):
            raise
        except Exception as e:
            self._logger.exception(
                "Unexpected error in MonsterDecidedToInteractHandler: %s", e
            )
            raise SystemErrorException(
                f"Monster decided to interact handler failed: {e}",
                original_exception=e,
            ) from e

    def _handle_impl(self, event: MonsterDecidedToInteractEvent) -> None:
        physical_map = self._physical_map_repository.find_by_spot_id(event.spot_id)
        if physical_map is None:
            self._logger.warning(
                "Physical map not found for spot_id=%s, skipping interact",
                event.spot_id,
            )
            return
        try:
            physical_map.interact_with(
                event.actor_id,
                event.target_id,
                event.current_tick,
            )
        except DomainException as e:
            self._logger.warning(
                "Interact skipped for actor %s target %s: %s",
                event.actor_id,
                event.target_id,
                str(e),
            )
            return
        self._physical_map_repository.save(physical_map)
