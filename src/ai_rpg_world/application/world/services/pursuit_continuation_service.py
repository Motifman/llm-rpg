from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ai_rpg_world.application.world.contracts.dtos import (
    PlayerCurrentStateDto,
    VisibleObjectDto,
)
from ai_rpg_world.application.world.contracts.queries import GetPlayerCurrentStateQuery
from ai_rpg_world.application.world.services.world_query_service import WorldQueryService
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)


class PursuitContinuationAction(str, Enum):
    """Phase 3 tick-time pursuit routing outcomes."""

    PLAIN_MOVEMENT = "plain_movement"
    CONTINUE_PURSUIT = "continue_pursuit"
    WAITING_FOR_PATH = "waiting_for_path"
    ACTOR_UNAVAILABLE = "actor_unavailable"


@dataclass(frozen=True)
class PursuitContinuationDecision:
    """
    Narrow continuation result for world-tick orchestration.

    The shape intentionally leaves room for later plans to attach concrete
    replanning and failure branches without forcing the world tick to own them.
    """

    action: PursuitContinuationAction
    continuation_checked: bool
    should_advance_movement: bool
    replan_required: bool
    has_visible_target: bool
    has_active_path: bool
    target_world_object_id: Optional[int] = None
    visible_target: Optional[VisibleObjectDto] = None
    current_state: Optional[PlayerCurrentStateDto] = None
    failure_reason: Optional[str] = None


class PursuitContinuationService:
    """Builds pursuit continuation decisions for the world tick."""

    def __init__(self, world_query_service: WorldQueryService) -> None:
        self._world_query_service = world_query_service

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
                has_visible_target=False,
                has_active_path=False,
                target_world_object_id=target_world_object_id,
            )

        visible_target = self._find_visible_target(current_state, target_world_object_id)
        has_active_path = current_state.has_active_path
        return PursuitContinuationDecision(
            action=(
                PursuitContinuationAction.CONTINUE_PURSUIT
                if has_active_path
                else PursuitContinuationAction.WAITING_FOR_PATH
            ),
            continuation_checked=True,
            should_advance_movement=has_active_path,
            replan_required=not has_active_path,
            has_visible_target=visible_target is not None,
            has_active_path=has_active_path,
            target_world_object_id=target_world_object_id,
            visible_target=visible_target,
            current_state=current_state,
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
