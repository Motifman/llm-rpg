"""MonsterDecidedToMoveEvent を購読し、マップ上でオブジェクトを移動させるハンドラ。"""

import logging

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.monster.event.monster_events import MonsterDecidedToMoveEvent
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


def _coordinate_from_event_dict(d: dict) -> Coordinate:
    return Coordinate(
        d["x"],
        d["y"],
        d.get("z", 0),
    )


class MonsterDecidedToMoveHandler(EventHandler[MonsterDecidedToMoveEvent]):
    """MonsterDecidedToMoveEvent を受けて physical_map.move_object を実行する。"""

    def __init__(
        self,
        physical_map_repository: PhysicalMapRepository,
        monster_repository: MonsterRepository,
    ):
        self._physical_map_repository = physical_map_repository
        self._monster_repository = monster_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: MonsterDecidedToMoveEvent) -> None:
        try:
            self._handle_impl(event)
        except (ApplicationException, DomainException):
            raise
        except Exception as e:
            self._logger.exception(
                "Unexpected error in MonsterDecidedToMoveHandler: %s", e
            )
            raise SystemErrorException(
                f"Monster decided to move handler failed: {e}",
                original_exception=e,
            ) from e

    def _handle_impl(self, event: MonsterDecidedToMoveEvent) -> None:
        physical_map = self._physical_map_repository.find_by_spot_id(event.spot_id)
        if physical_map is None:
            self._logger.warning(
                "Physical map not found for spot_id=%s, skipping move",
                event.spot_id,
            )
            return

        coordinate = _coordinate_from_event_dict(event.coordinate)
        try:
            physical_map.move_object(
                event.actor_id,
                coordinate,
                event.current_tick,
            )
        except DomainException as e:
            self._logger.warning(
                "Move skipped for actor %s: %s",
                event.actor_id,
                str(e),
            )
            return

        self._physical_map_repository.save(physical_map)

        # パトロール点到達時はモンスターの patrol_index を進める
        monster = self._monster_repository.find_by_world_object_id(event.actor_id)
        if monster is None:
            return
        actor = physical_map.get_actor(event.actor_id)
        if actor is None:
            return
        if not isinstance(actor.component, AutonomousBehaviorComponent):
            return
        pts = actor.component.patrol_points
        if not pts:
            return
        if coordinate != pts[monster.behavior_patrol_index]:
            return
        monster.advance_patrol_index(len(pts))
        self._monster_repository.save(monster)
