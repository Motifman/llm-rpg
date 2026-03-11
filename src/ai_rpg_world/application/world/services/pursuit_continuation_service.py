from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Protocol

from ai_rpg_world.application.world.contracts.dtos import (
    PlayerCurrentStateDto,
    VisibleObjectDto,
)
from ai_rpg_world.application.world.contracts.queries import GetPlayerCurrentStateQuery
from ai_rpg_world.application.world.services.world_query_service import WorldQueryService
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import (
    PursuitFailureReason,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_last_known_state import (
    PursuitLastKnownState,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import (
    PursuitTargetSnapshot,
)
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class PursuitPathReplanner(Protocol):
    def replan_path_to_coordinate_in_current_unit_of_work(
        self,
        player_id: int,
        target_spot_id: int,
        target_coordinate: Coordinate,
    ) -> Any: ...


class PursuitContinuationAction(str, Enum):
    """Phase 3 tick-time pursuit continuation outcomes."""

    PLAIN_MOVEMENT = "plain_movement"
    CONTINUE_PURSUIT = "continue_pursuit"
    PURSUIT_FAILED = "pursuit_failed"
    ACTOR_UNAVAILABLE = "actor_unavailable"


@dataclass(frozen=True)
class PursuitContinuationDecision:
    """Result returned to world-tick orchestration for one pursuit actor."""

    action: PursuitContinuationAction
    continuation_checked: bool
    should_advance_movement: bool
    replan_required: bool
    replan_attempted: bool
    has_visible_target: bool
    has_active_path: bool
    target_world_object_id: Optional[int] = None
    visible_target: Optional[VisibleObjectDto] = None
    current_state: Optional[PlayerCurrentStateDto] = None
    failure_reason: Optional[PursuitFailureReason] = None
    pursuit_updated: bool = False


class PursuitContinuationService:
    """Runs the Phase 3 continuation state machine before tick movement."""

    def __init__(
        self,
        world_query_service: WorldQueryService,
        movement_service: Optional[PursuitPathReplanner] = None,
        player_status_repository: Optional[PlayerStatusRepository] = None,
        physical_map_repository: Optional[PhysicalMapRepository] = None,
    ) -> None:
        self._world_query_service = world_query_service
        self._movement_service = movement_service
        self._player_status_repository = player_status_repository
        self._physical_map_repository = physical_map_repository

    def evaluate_tick(
        self,
        player_status: PlayerStatusAggregate,
    ) -> PursuitContinuationDecision:
        if not player_status.has_active_pursuit or player_status.pursuit_state is None:
            has_path = player_status.goal_spot_id is not None and bool(player_status.planned_path)
            return PursuitContinuationDecision(
                action=PursuitContinuationAction.PLAIN_MOVEMENT,
                continuation_checked=False,
                should_advance_movement=has_path,
                replan_required=False,
                replan_attempted=False,
                has_visible_target=False,
                has_active_path=has_path,
            )

        current_state = self._world_query_service.get_player_current_state(
            GetPlayerCurrentStateQuery(
                player_id=int(player_status.player_id),
                include_available_moves=False,
                include_tile_map=False,
            )
        )
        target_world_object_id = int(player_status.pursuit_state.target_id)

        if current_state is None:
            return PursuitContinuationDecision(
                action=PursuitContinuationAction.ACTOR_UNAVAILABLE,
                continuation_checked=True,
                should_advance_movement=False,
                replan_required=False,
                replan_attempted=False,
                has_visible_target=False,
                has_active_path=False,
                target_world_object_id=target_world_object_id,
            )

        visible_target = self._find_visible_target(current_state, target_world_object_id)
        if visible_target is not None:
            return self._handle_visible_target(player_status, current_state, visible_target)

        return self._handle_frozen_last_known(player_status, current_state)

    def _handle_visible_target(
        self,
        player_status: PlayerStatusAggregate,
        current_state: PlayerCurrentStateDto,
        visible_target: VisibleObjectDto,
    ) -> PursuitContinuationDecision:
        pursuit_state = player_status.pursuit_state
        assert pursuit_state is not None

        snapshot = self._build_snapshot(
            target_world_object_id=int(pursuit_state.target_id),
            spot_id=SpotId(current_state.current_spot_id),
            visible_target=visible_target,
        )
        last_known = self._build_last_known(snapshot)
        pursuit_updated = player_status.update_pursuit(
            target_snapshot=snapshot,
            last_known=last_known,
        )
        if pursuit_updated:
            self._save_player_status(player_status)

        has_active_path = self._has_active_path(player_status, current_state)
        replan_required = pursuit_updated or not has_active_path
        replan_attempted = False

        if replan_required:
            replan_attempted = True
            replan_succeeded = self._replan_to_coordinate(
                player_status=player_status,
                target_spot_id=snapshot.spot_id,
                target_coordinate=snapshot.coordinate,
            )
            if not replan_succeeded:
                player_status.fail_pursuit(
                    PursuitFailureReason.PATH_UNREACHABLE,
                    last_known=last_known,
                    target_snapshot=snapshot,
                )
                self._save_player_status(player_status)
                return PursuitContinuationDecision(
                    action=PursuitContinuationAction.PURSUIT_FAILED,
                    continuation_checked=True,
                    should_advance_movement=False,
                    replan_required=True,
                    replan_attempted=True,
                    has_visible_target=True,
                    has_active_path=False,
                    target_world_object_id=int(snapshot.target_id),
                    visible_target=visible_target,
                    current_state=current_state,
                    failure_reason=PursuitFailureReason.PATH_UNREACHABLE,
                    pursuit_updated=pursuit_updated,
                )
            has_active_path = self._has_active_path(player_status, current_state)

        return PursuitContinuationDecision(
            action=PursuitContinuationAction.CONTINUE_PURSUIT,
            continuation_checked=True,
            should_advance_movement=has_active_path,
            replan_required=replan_required,
            replan_attempted=replan_attempted,
            has_visible_target=True,
            has_active_path=has_active_path,
            target_world_object_id=int(snapshot.target_id),
            visible_target=visible_target,
            current_state=current_state,
            pursuit_updated=pursuit_updated,
        )

    def _handle_frozen_last_known(
        self,
        player_status: PlayerStatusAggregate,
        current_state: PlayerCurrentStateDto,
    ) -> PursuitContinuationDecision:
        pursuit_state = player_status.pursuit_state
        assert pursuit_state is not None

        last_known = pursuit_state.last_known
        snapshot = pursuit_state.target_snapshot
        has_active_path = self._has_active_path(player_status, current_state)
        target_world_object_id = int(pursuit_state.target_id)

        if self._physical_map_repository is not None:
            target_spot_id = self._physical_map_repository.find_spot_id_by_object_id(
                pursuit_state.target_id
            )
            if target_spot_id is None:
                player_status.fail_pursuit(
                    PursuitFailureReason.TARGET_MISSING,
                    last_known=last_known,
                    target_snapshot=snapshot,
                )
                self._save_player_status(player_status)
                return PursuitContinuationDecision(
                    action=PursuitContinuationAction.PURSUIT_FAILED,
                    continuation_checked=True,
                    should_advance_movement=False,
                    replan_required=False,
                    replan_attempted=False,
                    has_visible_target=False,
                    has_active_path=False,
                    target_world_object_id=target_world_object_id,
                    current_state=current_state,
                    failure_reason=PursuitFailureReason.TARGET_MISSING,
                )

        if self._is_at_last_known(player_status, last_known):
            player_status.fail_pursuit(
                PursuitFailureReason.VISION_LOST_AT_LAST_KNOWN,
                last_known=last_known,
                target_snapshot=snapshot,
            )
            self._save_player_status(player_status)
            return PursuitContinuationDecision(
                action=PursuitContinuationAction.PURSUIT_FAILED,
                continuation_checked=True,
                should_advance_movement=False,
                replan_required=False,
                replan_attempted=False,
                has_visible_target=False,
                has_active_path=False,
                target_world_object_id=target_world_object_id,
                current_state=current_state,
                failure_reason=PursuitFailureReason.VISION_LOST_AT_LAST_KNOWN,
            )

        replan_required = not has_active_path
        replan_attempted = False
        if replan_required:
            replan_attempted = True
            replan_succeeded = self._replan_to_coordinate(
                player_status=player_status,
                target_spot_id=last_known.spot_id,
                target_coordinate=last_known.coordinate,
            )
            if not replan_succeeded:
                player_status.fail_pursuit(
                    PursuitFailureReason.PATH_UNREACHABLE,
                    last_known=last_known,
                    target_snapshot=snapshot,
                )
                self._save_player_status(player_status)
                return PursuitContinuationDecision(
                    action=PursuitContinuationAction.PURSUIT_FAILED,
                    continuation_checked=True,
                    should_advance_movement=False,
                    replan_required=True,
                    replan_attempted=True,
                    has_visible_target=False,
                    has_active_path=False,
                    target_world_object_id=target_world_object_id,
                    current_state=current_state,
                    failure_reason=PursuitFailureReason.PATH_UNREACHABLE,
                )
            has_active_path = self._has_active_path(player_status, current_state)

        return PursuitContinuationDecision(
            action=PursuitContinuationAction.CONTINUE_PURSUIT,
            continuation_checked=True,
            should_advance_movement=has_active_path,
            replan_required=replan_required,
            replan_attempted=replan_attempted,
            has_visible_target=False,
            has_active_path=has_active_path,
            target_world_object_id=target_world_object_id,
            current_state=current_state,
        )

    def _replan_to_coordinate(
        self,
        player_status: PlayerStatusAggregate,
        target_spot_id: SpotId,
        target_coordinate: Coordinate,
    ) -> bool:
        if self._movement_service is None:
            return False

        result = self._movement_service.replan_path_to_coordinate_in_current_unit_of_work(
            player_id=int(player_status.player_id),
            target_spot_id=int(target_spot_id),
            target_coordinate=target_coordinate,
        )
        return bool(getattr(result, "success", False))

    @staticmethod
    def _build_snapshot(
        target_world_object_id: int,
        spot_id: SpotId,
        visible_target: VisibleObjectDto,
    ) -> PursuitTargetSnapshot:
        return PursuitTargetSnapshot(
            target_id=player_status_target_id(target_world_object_id),
            spot_id=spot_id,
            coordinate=Coordinate(
                int(visible_target.x),
                int(visible_target.y),
                int(visible_target.z),
            ),
        )

    @staticmethod
    def _build_last_known(snapshot: PursuitTargetSnapshot) -> PursuitLastKnownState:
        return PursuitLastKnownState(
            target_id=snapshot.target_id,
            spot_id=snapshot.spot_id,
            coordinate=snapshot.coordinate,
        )

    @staticmethod
    def _has_active_path(
        player_status: PlayerStatusAggregate,
        current_state: PlayerCurrentStateDto,
    ) -> bool:
        return bool(player_status.planned_path) or bool(current_state.has_active_path)

    @staticmethod
    def _is_at_last_known(
        player_status: PlayerStatusAggregate,
        last_known: PursuitLastKnownState,
    ) -> bool:
        return (
            player_status.current_spot_id == last_known.spot_id
            and player_status.current_coordinate == last_known.coordinate
        )

    @staticmethod
    def _find_visible_target(
        current_state: PlayerCurrentStateDto,
        target_world_object_id: int,
    ) -> Optional[VisibleObjectDto]:
        return next(
            (
                visible_object
                for visible_object in current_state.visible_objects
                if visible_object.object_id == target_world_object_id
            ),
            None,
        )

    def _save_player_status(self, player_status: PlayerStatusAggregate) -> None:
        if self._player_status_repository is not None:
            self._player_status_repository.save(player_status)


def player_status_target_id(target_world_object_id: int):
    from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId

    return WorldObjectId.create(target_world_object_id)
