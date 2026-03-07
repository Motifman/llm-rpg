"""プレイヤー視点の採集開始 API。"""

import logging
from typing import Callable, Any

from ai_rpg_world.application.common.services.game_time_provider import GameTimeProvider
from ai_rpg_world.application.harvest.contracts.commands import StartHarvestCommand
from ai_rpg_world.application.harvest.contracts.dtos import HarvestCommandResultDto
from ai_rpg_world.application.harvest.exceptions.base_exception import (
    HarvestApplicationException,
    HarvestSystemErrorException,
)
from ai_rpg_world.application.harvest.exceptions.command.harvest_command_exception import (
    HarvestActorNotFoundException,
    HarvestCommandException,
    HarvestResourceNotFoundException,
)
from ai_rpg_world.application.harvest.services.harvest_command_service import HarvestCommandService
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class PlayerHarvestApplicationService:
    """LLM などが使いやすい形で採集開始を提供する薄いアプリケーションサービス。"""

    def __init__(
        self,
        harvest_command_service: HarvestCommandService,
        physical_map_repository: PhysicalMapRepository,
        player_status_repository: PlayerStatusRepository,
        time_provider: GameTimeProvider,
    ):
        self._harvest_command_service = harvest_command_service
        self._physical_map_repository = physical_map_repository
        self._player_status_repository = player_status_repository
        self._time_provider = time_provider
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(
        self,
        operation: Callable[[], HarvestCommandResultDto],
        context: dict,
    ) -> HarvestCommandResultDto:
        try:
            return operation()
        except HarvestApplicationException:
            raise
        except DomainException as e:
            raise HarvestCommandException(str(e), **context)
        except Exception as e:
            self._logger.error(
                "Unexpected error in %s: %s",
                context.get("action", "unknown"),
                e,
                extra=context,
            )
            raise HarvestSystemErrorException(
                f"{context.get('action', 'unknown')} failed: {str(e)}",
                original_exception=e,
            )

    def start_harvest_by_target(
        self,
        *,
        player_id: int,
        target_world_object_id: int,
    ) -> HarvestCommandResultDto:
        """対象資源を指定して採集を開始する。隣接対象には自動で向き直る。"""
        return self._execute_with_error_handling(
            operation=lambda: self._start_harvest_by_target_impl(
                player_id=player_id,
                target_world_object_id=target_world_object_id,
            ),
            context={
                "action": "start_harvest_by_target",
                "player_id": player_id,
                "target_world_object_id": target_world_object_id,
            },
        )

    def _start_harvest_by_target_impl(
        self,
        *,
        player_id: int,
        target_world_object_id: int,
    ) -> HarvestCommandResultDto:
        player_id_vo = PlayerId.create(player_id)
        status = self._player_status_repository.find_by_id(player_id_vo)
        if not status or not status.current_spot_id:
            raise HarvestActorNotFoundException(player_id)

        physical_map = self._physical_map_repository.find_by_spot_id(status.current_spot_id)
        if physical_map is None:
            raise HarvestCommandException(f"Spot not found: {int(status.current_spot_id)}")

        actor_id = WorldObjectId.create(player_id)
        target_id = WorldObjectId.create(target_world_object_id)
        try:
            actor = physical_map.get_actor(actor_id)
        except ObjectNotFoundException:
            raise HarvestActorNotFoundException(player_id)
        try:
            target = physical_map.get_object(target_id)
        except ObjectNotFoundException:
            raise HarvestResourceNotFoundException(target_world_object_id, int(status.current_spot_id))

        if actor.coordinate.is_adjacent_8way(target.coordinate):
            actor.turn(actor.coordinate.direction_to(target.coordinate))
            self._physical_map_repository.save(physical_map)

        return self._harvest_command_service.start_harvest(
            StartHarvestCommand(
                actor_id=str(player_id),
                target_id=str(target_world_object_id),
                spot_id=str(int(status.current_spot_id)),
                current_tick=self._time_provider.get_current_tick().value,
            )
        )
