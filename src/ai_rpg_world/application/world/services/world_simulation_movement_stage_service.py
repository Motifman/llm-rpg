from typing import Callable, Optional, TYPE_CHECKING

from ai_rpg_world.domain.common.value_object import WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.application.harvest.services.harvest_command_service import (
        HarvestCommandService,
    )
    from ai_rpg_world.application.world.services.movement_service import (
        MovementApplicationService,
    )
    from ai_rpg_world.application.world.services.pursuit_continuation_service import (
        PursuitContinuationService,
    )
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class WorldSimulationMovementStageService:
    """継続追跡を含む pending movement stage。"""

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        physical_map_repository: PhysicalMapRepository,
        movement_service_getter: Callable[[], Optional["MovementApplicationService"]],
        pursuit_continuation_service_getter: Callable[[], Optional["PursuitContinuationService"]],
    ) -> None:
        self._player_status_repository = player_status_repository
        self._physical_map_repository = physical_map_repository
        self._movement_service_getter = movement_service_getter
        self._pursuit_continuation_service_getter = (
            pursuit_continuation_service_getter
        )

    def run(self, current_tick: WorldTick) -> None:
        tick_movement = getattr(
            self._movement_service_getter(),
            "tick_movement_in_current_unit_of_work",
            None,
        )
        if not callable(tick_movement):
            return

        continuation_service = self._pursuit_continuation_service_getter()
        for status in self._player_status_repository.find_all():
            has_active_pursuit = (
                status.has_active_pursuit and status.pursuit_state is not None
            )
            if status.current_spot_id is None:
                continue
            if not has_active_pursuit and status.goal_spot_id is None:
                continue

            physical_map = self._physical_map_repository.find_by_spot_id(
                status.current_spot_id
            )
            if physical_map is None:
                continue

            try:
                actor = physical_map.get_actor(
                    WorldObjectId.create(int(status.player_id))
                )
            except ObjectNotFoundException:
                continue

            if actor.is_busy(current_tick):
                continue

            if has_active_pursuit and continuation_service is not None:
                continuation = continuation_service.evaluate_tick(status)
                if not continuation.should_advance_movement:
                    continue
            elif status.goal_spot_id is None:
                continue

            tick_movement(int(status.player_id))
