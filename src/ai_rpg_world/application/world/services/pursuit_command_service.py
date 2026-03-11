import logging
from typing import Any, Callable, Optional

from ai_rpg_world.application.world.contracts.commands import (
    CancelPursuitCommand,
    StartPursuitCommand,
)
from ai_rpg_world.application.world.contracts.dtos import PursuitCommandResultDto
from ai_rpg_world.application.world.contracts.queries import GetPlayerCurrentStateQuery
from ai_rpg_world.application.world.exceptions.base_exception import (
    WorldApplicationException,
    WorldSystemErrorException,
)
from ai_rpg_world.application.world.exceptions.command.pursuit_command_exception import (
    PursuitActorBusyException,
    PursuitActorNotPlacedException,
    PursuitActorObjectNotFoundException,
    PursuitCommandException,
    PursuitInvalidTargetKindException,
    PursuitPlayerNotFoundException,
    PursuitSelfTargetException,
    PursuitTargetNotFoundException,
    PursuitTargetNotVisibleException,
)
from ai_rpg_world.application.world.services.world_query_service import WorldQueryService
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import (
    PursuitTargetSnapshot,
)
from ai_rpg_world.domain.world.exception.map_exception import (
    NotAnActorException,
    ObjectNotFoundException,
    WorldObjectIdValidationException,
)
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class PursuitCommandService:
    """プレイヤーの追跡開始/中断を扱うアプリケーションサービス。"""

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        player_profile_repository: PlayerProfileRepository,
        physical_map_repository: PhysicalMapRepository,
        world_query_service: WorldQueryService,
        unit_of_work: UnitOfWork,
    ) -> None:
        self._player_status_repository = player_status_repository
        self._player_profile_repository = player_profile_repository
        self._physical_map_repository = physical_map_repository
        self._world_query_service = world_query_service
        self._unit_of_work = unit_of_work
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(
        self,
        operation: Callable[[], PursuitCommandResultDto],
        context: dict[str, Any],
    ) -> PursuitCommandResultDto:
        try:
            return operation()
        except WorldApplicationException:
            raise
        except DomainException as e:
            raise PursuitCommandException(str(e), player_id=context.get("player_id"))
        except Exception as e:
            self._logger.error(
                "Unexpected error in %s: %s",
                context.get("action", "unknown"),
                str(e),
                extra=context,
            )
            raise WorldSystemErrorException(
                f"{context.get('action', 'unknown')} failed: {str(e)}",
                original_exception=e,
            )

    def start_pursuit(self, command: StartPursuitCommand) -> PursuitCommandResultDto:
        return self._execute_with_error_handling(
            operation=lambda: self._start_pursuit_impl(command),
            context={
                "action": "start_pursuit",
                "player_id": command.player_id,
                "target_world_object_id": command.target_world_object_id,
            },
        )

    def cancel_pursuit(self, command: CancelPursuitCommand) -> PursuitCommandResultDto:
        return self._execute_with_error_handling(
            operation=lambda: self._cancel_pursuit_impl(command),
            context={"action": "cancel_pursuit", "player_id": command.player_id},
        )

    def _start_pursuit_impl(self, command: StartPursuitCommand) -> PursuitCommandResultDto:
        player_id = PlayerId(command.player_id)
        target_world_object_id = command.target_world_object_id
        target_id = WorldObjectId.create(target_world_object_id)

        with self._unit_of_work:
            player_status = self._player_status_repository.find_by_id(player_id)
            if player_status is None:
                raise PursuitPlayerNotFoundException(command.player_id)
            if (
                player_status.current_spot_id is None
                or player_status.current_coordinate is None
            ):
                raise PursuitActorNotPlacedException(command.player_id)

            physical_map = self._physical_map_repository.find_by_spot_id(
                player_status.current_spot_id
            )
            if physical_map is None:
                raise PursuitActorNotPlacedException(command.player_id)

            try:
                physical_map.get_actor(WorldObjectId.create(command.player_id))
            except (
                ObjectNotFoundException,
                NotAnActorException,
                WorldObjectIdValidationException,
            ):
                raise PursuitActorObjectNotFoundException(command.player_id)

            current_state = self._world_query_service.get_player_current_state(
                GetPlayerCurrentStateQuery(player_id=command.player_id)
            )
            if current_state is None:
                raise PursuitActorNotPlacedException(command.player_id)
            if current_state.is_busy:
                raise PursuitActorBusyException(
                    command.player_id,
                    current_state.busy_until_tick or 0,
                )

            try:
                physical_map.get_object(target_id)
            except ObjectNotFoundException:
                raise PursuitTargetNotFoundException(
                    command.player_id,
                    target_world_object_id,
                )

            visible_target = next(
                (
                    obj
                    for obj in current_state.visible_objects
                    if obj.object_id == target_world_object_id
                ),
                None,
            )
            if visible_target is None:
                raise PursuitTargetNotVisibleException(
                    command.player_id,
                    target_world_object_id,
                )
            if visible_target.is_self:
                raise PursuitSelfTargetException(command.player_id)
            if visible_target.object_kind not in {"player", "monster"}:
                raise PursuitInvalidTargetKindException(
                    command.player_id,
                    target_world_object_id,
                    visible_target.object_kind or "unknown",
                )

            snapshot = PursuitTargetSnapshot(
                target_id=target_id,
                spot_id=player_status.current_spot_id,
                coordinate=self._visible_target_coordinate(visible_target),
            )
            player_status.clear_path()

            target_name = visible_target.display_name or f"対象{target_world_object_id}"
            if player_status.has_active_pursuit and player_status.pursuit_state is not None:
                current_target_id = player_status.pursuit_state.target_id
                if current_target_id == target_id:
                    changed = player_status.update_pursuit(target_snapshot=snapshot)
                    self._player_status_repository.save(player_status)
                    return PursuitCommandResultDto(
                        success=True,
                        message=(
                            f"{target_name}の追跡情報を更新しました。"
                            if changed
                            else f"既に{target_name}を追跡中です。"
                        ),
                        target_world_object_id=target_world_object_id,
                        target_display_name=target_name,
                        no_op=not changed,
                    )

                player_status.cancel_pursuit()
                player_status.start_pursuit(snapshot)
                self._player_status_repository.save(player_status)
                return PursuitCommandResultDto(
                    success=True,
                    message=f"追跡対象を{target_name}に切り替えました。",
                    target_world_object_id=target_world_object_id,
                    target_display_name=target_name,
                )

            player_status.start_pursuit(snapshot)
            self._player_status_repository.save(player_status)
            return PursuitCommandResultDto(
                success=True,
                message=f"{target_name}の追跡を開始しました。",
                target_world_object_id=target_world_object_id,
                target_display_name=target_name,
            )

    def _cancel_pursuit_impl(self, command: CancelPursuitCommand) -> PursuitCommandResultDto:
        player_id = PlayerId(command.player_id)

        with self._unit_of_work:
            player_status = self._player_status_repository.find_by_id(player_id)
            if player_status is None:
                raise PursuitPlayerNotFoundException(command.player_id)

            if not player_status.has_active_pursuit or player_status.pursuit_state is None:
                return PursuitCommandResultDto(
                    success=True,
                    message="追跡中の対象はいません。",
                    no_op=True,
                )

            current_target = player_status.pursuit_state.target_snapshot
            target_name = (
                current_target.target_id.value if current_target is not None else None
            )
            player_status.cancel_pursuit()
            player_status.clear_path()
            self._player_status_repository.save(player_status)
            return PursuitCommandResultDto(
                success=True,
                message="追跡を中断しました。",
                target_world_object_id=(
                    int(current_target.target_id) if current_target is not None else None
                ),
                target_display_name=str(target_name) if target_name is not None else None,
            )

    def _visible_target_coordinate(self, visible_target: Any):
        from ai_rpg_world.domain.world.value_object.coordinate import Coordinate

        return Coordinate(
            int(visible_target.x),
            int(visible_target.y),
            int(visible_target.z),
        )
