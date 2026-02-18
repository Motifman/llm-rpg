"""
ItemTakenFromChestEvent を受けて、プレイヤーインベントリに該当アイテムを追加するハンドラ
"""

import logging

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.player.repository.player_inventory_repository import PlayerInventoryRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.event.map_events import ItemTakenFromChestEvent


class ItemTakenFromChestHandler(EventHandler[ItemTakenFromChestEvent]):
    """チェスト取得イベントで、プレイヤーインベントリにアイテムを追加するハンドラ"""

    def __init__(
        self,
        player_inventory_repository: PlayerInventoryRepository,
        unit_of_work: UnitOfWork,
    ):
        self._player_inventory_repository = player_inventory_repository
        self._unit_of_work = unit_of_work
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: ItemTakenFromChestEvent) -> None:
        try:
            self._handle_impl(event)
        except (ApplicationException, DomainException):
            raise
        except Exception as e:
            self._logger.exception("Unexpected error in ItemTakenFromChestHandler: %s", e)
            raise SystemErrorException(
                f"Item taken from chest handling failed: {e}",
                original_exception=e,
            ) from e

    def _handle_impl(self, event: ItemTakenFromChestEvent) -> None:
        player_id = PlayerId.create(event.player_id_value)
        inventory = self._player_inventory_repository.find_by_id(player_id)
        if not inventory:
            self._logger.debug(
                "Player inventory not found for player_id=%s (expected if stale), skipping",
                event.player_id_value,
            )
            return

        inventory.acquire_item(event.item_instance_id)
        self._player_inventory_repository.save(inventory)
        self._logger.debug(
            "Added item %s to player %s inventory (taken from chest %s)",
            event.item_instance_id,
            event.player_id_value,
            event.chest_id,
        )
