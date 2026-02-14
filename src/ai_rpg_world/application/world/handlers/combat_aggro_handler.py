import logging
from typing import Optional

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.world.aggro_store import AggroStore
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.combat.event.combat_events import HitBoxHitRecordedEvent
from ai_rpg_world.domain.combat.repository.hit_box_repository import HitBoxRepository
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository


class CombatAggroHandler(EventHandler[HitBoxHitRecordedEvent]):
    """HitBoxヒットイベントを受けて被弾したアクターのヘイト（ターゲット）を更新するハンドラ"""

    def __init__(
        self,
        hit_box_repository: HitBoxRepository,
        physical_map_repository: PhysicalMapRepository,
        unit_of_work: UnitOfWork,
        aggro_store: Optional[AggroStore] = None,
    ):
        self._hit_box_repository = hit_box_repository
        self._physical_map_repository = physical_map_repository
        self._unit_of_work = unit_of_work
        self._aggro_store = aggro_store
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: HitBoxHitRecordedEvent) -> None:
        try:
            self._handle_impl(event)
        except (ApplicationException, DomainException):
            raise
        except Exception as e:
            self._logger.exception("Unexpected error in CombatAggroHandler: %s", e)
            raise SystemErrorException(
                f"Combat aggro handling failed: {e}",
                original_exception=e,
            ) from e

    def _handle_impl(self, event: HitBoxHitRecordedEvent) -> None:
        hit_box = self._hit_box_repository.find_by_id(event.aggregate_id)
        if not hit_box:
            self._logger.debug("HitBox not found for aggro event (expected if stale): %s", event.aggregate_id)
            return

        physical_map = self._physical_map_repository.find_by_spot_id(hit_box.spot_id)
        if not physical_map:
            self._logger.debug("Map not found for HitBox aggro (expected if stale): %s", hit_box.spot_id)
            return

        try:
            owner_obj = physical_map.get_object(event.owner_id)
            target_obj = physical_map.get_object(event.target_id)
        except ObjectNotFoundException:
            self._logger.debug("Combatant disappeared before aggro update: owner=%s, target=%s", event.owner_id, event.target_id)
            return

        if not owner_obj.is_actor:
            return
        if not target_obj.is_actor:
            return

        component = target_obj.component
        if not isinstance(component, AutonomousBehaviorComponent):
            return

        component.spot_target(owner_obj.object_id, owner_obj.coordinate)
        if self._aggro_store is not None:
            self._aggro_store.add_aggro(
                spot_id=hit_box.spot_id,
                victim_id=event.target_id,
                attacker_id=event.owner_id,
                amount=1,
            )
        self._physical_map_repository.save(physical_map)
