"""追加引数不要のワールドオブジェクト相互作用サービス。"""

import logging
from typing import Callable, Any

from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
from ai_rpg_world.application.world.contracts.commands import InteractWorldObjectCommand
from ai_rpg_world.application.world.exceptions.base_exception import (
    WorldApplicationException,
    WorldSystemErrorException,
)
from ai_rpg_world.application.world.exceptions.command.interaction_command_exception import (
    InteractionCommandException,
    InteractionInvalidException,
    InteractionPlayerNotFoundException,
    InteractionTargetNotFoundException,
)
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class InteractionCommandService:
    """LLM などから使いやすいワールドオブジェクト相互作用の入口。"""

    def __init__(
        self,
        physical_map_repository: PhysicalMapRepository,
        player_status_repository: PlayerStatusRepository,
        time_provider: GameTimeProvider,
        unit_of_work: UnitOfWork,
    ):
        self._physical_map_repository = physical_map_repository
        self._player_status_repository = player_status_repository
        self._time_provider = time_provider
        self._unit_of_work = unit_of_work
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(
        self,
        operation: Callable[[], Any],
        context: dict,
    ) -> Any:
        try:
            return operation()
        except WorldApplicationException:
            raise
        except DomainException as e:
            raise InteractionCommandException(str(e), **context)
        except Exception as e:
            self._logger.error(
                "Unexpected error in %s: %s",
                context.get("action", "unknown"),
                e,
                extra=context,
            )
            raise WorldSystemErrorException(
                f"{context.get('action', 'unknown')} failed: {str(e)}",
                original_exception=e,
            )

    def interact_world_object(self, command: InteractWorldObjectCommand) -> None:
        """対象オブジェクトに相互作用する。隣接対象には自動で向き直る。"""
        self._execute_with_error_handling(
            operation=lambda: self._interact_world_object_impl(command),
            context={
                "action": "interact_world_object",
                "player_id": command.player_id,
                "target_world_object_id": command.target_world_object_id,
            },
        )

    def _interact_world_object_impl(self, command: InteractWorldObjectCommand) -> None:
        with self._unit_of_work:
            player_id = PlayerId.create(command.player_id)
            status = self._player_status_repository.find_by_id(player_id)
            if not status or not status.current_spot_id or status.current_coordinate is None:
                raise InteractionPlayerNotFoundException(command.player_id)

            physical_map = self._physical_map_repository.find_by_spot_id(status.current_spot_id)
            if physical_map is None:
                raise InteractionInvalidException(
                    "現在地のマップが見つかりません。",
                    command.player_id,
                )

            actor_id = WorldObjectId.create(command.player_id)
            target_id = WorldObjectId.create(command.target_world_object_id)
            try:
                actor = physical_map.get_actor(actor_id)
            except ObjectNotFoundException:
                raise InteractionPlayerNotFoundException(command.player_id)
            try:
                target = physical_map.get_object(target_id)
            except ObjectNotFoundException:
                raise InteractionTargetNotFoundException(command.target_world_object_id)

            if actor.coordinate.distance_to(target.coordinate) == 1:
                actor.turn(actor.coordinate.direction_to(target.coordinate))

            physical_map.interact_with(
                actor_id=actor_id,
                target_id=target_id,
                current_tick=self._time_provider.get_current_tick(),
            )
            self._physical_map_repository.save(physical_map)
