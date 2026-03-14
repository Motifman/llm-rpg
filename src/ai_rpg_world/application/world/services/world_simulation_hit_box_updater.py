import logging
from typing import Callable

from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.combat.repository.hit_box_repository import HitBoxRepository
from ai_rpg_world.domain.combat.service.hit_box_collision_service import (
    HitBoxCollisionDomainService,
)
from ai_rpg_world.domain.combat.service.hit_box_config_service import HitBoxConfigService
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate


class WorldSimulationHitBoxUpdater:
    """HitBox 更新本体を扱う collaborator。"""

    def __init__(
        self,
        hit_box_repository: HitBoxRepository,
        hit_box_config_service: HitBoxConfigService,
        hit_box_collision_service: HitBoxCollisionDomainService,
        logger: logging.Logger,
        hit_box_config_service_getter: Callable[[], HitBoxConfigService] | None = None,
        hit_box_collision_service_getter: Callable[
            [], HitBoxCollisionDomainService
        ] | None = None,
    ) -> None:
        self._hit_box_repository = hit_box_repository
        self._hit_box_config_service = hit_box_config_service
        self._hit_box_collision_service = hit_box_collision_service
        self._hit_box_config_service_getter = hit_box_config_service_getter
        self._hit_box_collision_service_getter = hit_box_collision_service_getter
        self._logger = logger

    def update_hit_boxes(
        self,
        physical_map: PhysicalMapAggregate,
        current_tick: WorldTick,
    ) -> None:
        try:
            hit_boxes = self._hit_box_repository.find_active_by_spot_id(physical_map.spot_id)
        except Exception as exc:
            self._logger.error(
                "Failed to load hit boxes for map %s: %s",
                physical_map.spot_id,
                str(exc),
                exc_info=True,
            )
            return

        hit_box_config_service = (
            self._hit_box_config_service_getter()
            if self._hit_box_config_service_getter is not None
            else self._hit_box_config_service
        )
        hit_box_collision_service = (
            self._hit_box_collision_service_getter()
            if self._hit_box_collision_service_getter is not None
            else self._hit_box_collision_service
        )

        total_substeps_executed = 0
        total_collision_checks = 0
        guard_trigger_count = 0

        for hit_box in hit_boxes:
            try:
                substeps_per_tick = hit_box_config_service.get_substeps_for_hit_box(hit_box)
                max_collision_checks = hit_box_config_service.get_max_collision_checks_per_tick()
                collision_checks_for_hit_box = 0
                step_ratio = 1.0 / substeps_per_tick
                for _ in range(substeps_per_tick):
                    if not hit_box.is_active:
                        break
                    if not hit_box.is_activated(current_tick):
                        break

                    total_substeps_executed += 1
                    hit_box.on_tick(current_tick, step_ratio=step_ratio)

                    if not hit_box.is_active:
                        continue

                    used_checks, guard_triggered = (
                        hit_box_collision_service.resolve_collisions(
                            physical_map,
                            hit_box,
                            max_collision_checks=(
                                max_collision_checks - collision_checks_for_hit_box
                            ),
                        )
                    )
                    collision_checks_for_hit_box += used_checks
                    if guard_triggered:
                        guard_trigger_count += 1
                        self._logger.warning(
                            "Collision check guard triggered for hit box %s in map %s. limit=%s",
                            hit_box.hit_box_id,
                            physical_map.spot_id,
                            max_collision_checks,
                        )
                        break

                self._hit_box_repository.save(hit_box)
                total_collision_checks += collision_checks_for_hit_box
            except DomainException as exc:
                self._logger.warning(
                    "HitBox update skipped for %s due to domain rule: %s",
                    hit_box.hit_box_id,
                    str(exc),
                )
            except Exception as exc:
                self._logger.error(
                    "Failed to update hit box %s in map %s: %s",
                    hit_box.hit_box_id,
                    physical_map.spot_id,
                    str(exc),
                    exc_info=True,
                )

        self._logger.debug(
            "HitBox update stats map=%s hit_boxes=%s substeps=%s collision_checks=%s guard_triggers=%s",
            physical_map.spot_id,
            len(hit_boxes),
            total_substeps_executed,
            total_collision_checks,
            guard_trigger_count,
        )
