"""
意図的ドロップのアプリケーションサービス。

インベントリの指定スロットのアイテムを地面に落とす。
ItemDroppedFromInventoryEvent が発行され、同期的なハンドラが GROUND_ITEM を配置する。
"""

import logging
from typing import Callable, Any

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.player.repository.player_inventory_repository import PlayerInventoryRepository
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.player.exception.player_exceptions import (
    ItemNotInSlotException,
    ItemReservedException,
)
from ai_rpg_world.domain.common.exception import DomainException

from ai_rpg_world.application.world.contracts.commands import DropItemCommand
from ai_rpg_world.application.world.exceptions.base_exception import WorldApplicationException, WorldSystemErrorException
from ai_rpg_world.application.world.exceptions.command.place_command_exception import (
    PlaceCommandException,
    NoItemInSlotException,
    ItemReservedForDropException,
    PlacementSpotNotFoundException,
)


class DropItemApplicationService:
    """意図的ドロップコマンドサービス"""

    def __init__(
        self,
        player_inventory_repository: PlayerInventoryRepository,
        player_status_repository: PlayerStatusRepository,
        unit_of_work: UnitOfWork,
    ):
        self._player_inventory_repository = player_inventory_repository
        self._player_status_repository = player_status_repository
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
        except ItemNotInSlotException:
            raise NoItemInSlotException(
                context.get("player_id", 0),
                context.get("slot_id", 0),
            )
        except ItemReservedException:
            raise ItemReservedForDropException(
                context.get("player_id", 0),
                context.get("slot_id", 0),
            )
        except DomainException as e:
            raise PlaceCommandException(str(e), **context)
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
            ) from e

    def drop_item(self, command: DropItemCommand) -> None:
        """指定スロットのアイテムを地面に落とす"""
        self._execute_with_error_handling(
            operation=lambda: self._drop_item_impl(command),
            context={
                "action": "drop_item",
                "player_id": command.player_id,
                "slot_id": command.inventory_slot_id,
            },
        )

    def _drop_item_impl(self, command: DropItemCommand) -> None:
        with self._unit_of_work:
            player_id = PlayerId(command.player_id)
            slot_id = SlotId(command.inventory_slot_id)

            player_status = self._player_status_repository.find_by_id(player_id)
            if not player_status or not player_status.current_spot_id or player_status.current_coordinate is None:
                raise PlacementSpotNotFoundException(command.player_id, 0)

            inventory = self._player_inventory_repository.find_by_id(player_id)
            if not inventory:
                raise PlacementSpotNotFoundException(command.player_id, 0)

            self._unit_of_work.register_aggregate(inventory)

            inventory.drop_item(slot_id)

            self._player_inventory_repository.save(inventory)
