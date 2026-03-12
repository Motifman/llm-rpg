"""LLM 向けの意図的ドロップ facade。"""

from ai_rpg_world.application.world.contracts.commands import DropItemCommand
from ai_rpg_world.application.world.exceptions.command.drop_command_exception import (
    DropPlayerOrInventoryNotFoundException,
)
from ai_rpg_world.application.world.services.drop_item_service import DropItemApplicationService
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class PlayerDropItemApplicationService:
    """LLM から使いやすい意図的ドロップ API。"""

    def __init__(
        self,
        drop_item_service: DropItemApplicationService,
        player_status_repository: PlayerStatusRepository,
    ) -> None:
        self._drop_item_service = drop_item_service
        self._player_status_repository = player_status_repository

    def drop_from_slot(self, *, player_id: int, inventory_slot_id: int) -> None:
        status = self._player_status_repository.find_by_id(PlayerId.create(player_id))
        if status is None or status.current_spot_id is None:
            raise DropPlayerOrInventoryNotFoundException(player_id)
        self._drop_item_service.drop_item(
            DropItemCommand(
                player_id=player_id,
                inventory_slot_id=inventory_slot_id,
            )
        )
