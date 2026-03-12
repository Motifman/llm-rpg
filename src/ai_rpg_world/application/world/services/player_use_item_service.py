"""LLM 向けの消費可能アイテム使用 facade。"""

from ai_rpg_world.application.world.contracts.commands import UseItemCommand
from ai_rpg_world.application.world.exceptions.command.use_command_exception import (
    UseItemPlayerNotFoundException,
)
from ai_rpg_world.application.world.services.use_item_service import UseItemApplicationService
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class PlayerUseItemApplicationService:
    """LLM から使いやすい消費可能アイテム使用 API。"""

    def __init__(
        self,
        use_item_service: UseItemApplicationService,
        player_status_repository: PlayerStatusRepository,
    ) -> None:
        self._use_item_service = use_item_service
        self._player_status_repository = player_status_repository

    def use_item(self, *, player_id: int, inventory_slot_id: int) -> None:
        """指定スロットの消費可能アイテムを使用する"""
        status = self._player_status_repository.find_by_id(PlayerId(player_id))
        if status is None:
            raise UseItemPlayerNotFoundException(player_id)
        self._use_item_service.use_item(
            UseItemCommand(
                player_id=player_id,
                inventory_slot_id=inventory_slot_id,
            )
        )
