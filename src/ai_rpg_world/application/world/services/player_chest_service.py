"""LLM 向けのチェスト操作 facade。"""

from ai_rpg_world.application.world.contracts.commands import (
    StoreItemInChestCommand,
    TakeItemFromChestCommand,
)
from ai_rpg_world.application.world.exceptions.command.chest_command_exception import (
    ChestNotFoundException,
)
from ai_rpg_world.application.world.services.chest_command_service import ChestCommandService
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class PlayerChestApplicationService:
    """LLM から使いやすいチェスト収納・取得 API。"""

    def __init__(
        self,
        chest_command_service: ChestCommandService,
        player_status_repository: PlayerStatusRepository,
    ) -> None:
        self._chest_command_service = chest_command_service
        self._player_status_repository = player_status_repository

    def store_item_by_target(
        self,
        *,
        player_id: int,
        chest_world_object_id: int,
        item_instance_id: int,
    ) -> None:
        status = self._player_status_repository.find_by_id(PlayerId.create(player_id))
        if status is None or status.current_spot_id is None:
            raise ChestNotFoundException(0, chest_world_object_id)
        self._chest_command_service.store_item_in_chest(
            StoreItemInChestCommand(
                player_id=player_id,
                spot_id=int(status.current_spot_id),
                actor_world_object_id=player_id,
                chest_world_object_id=chest_world_object_id,
                item_instance_id=item_instance_id,
            )
        )

    def take_item_by_target(
        self,
        *,
        player_id: int,
        chest_world_object_id: int,
        item_instance_id: int,
    ) -> None:
        status = self._player_status_repository.find_by_id(PlayerId.create(player_id))
        if status is None or status.current_spot_id is None:
            raise ChestNotFoundException(0, chest_world_object_id)
        self._chest_command_service.take_item_from_chest(
            TakeItemFromChestCommand(
                player_id=player_id,
                spot_id=int(status.current_spot_id),
                actor_world_object_id=player_id,
                chest_world_object_id=chest_world_object_id,
                item_instance_id=item_instance_id,
            )
        )
