"""
消費可能アイテム使用のアプリケーションサービス。

インベントリの指定スロットの CONSUMABLE アイテムを使用する。
効果（HP/MP回復など）は ConsumableUsedEvent 経由で ConsumableEffectHandler が適用する。
"""

import logging
from typing import Callable, Any, Optional

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.item.event.item_event import ConsumableUsedEvent
from ai_rpg_world.domain.item.enum.item_enum import ItemType
from ai_rpg_world.domain.player.repository.player_inventory_repository import PlayerInventoryRepository
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.player.exception.player_exceptions import (
    ItemNotInSlotException,
    ItemReservedException,
)
from ai_rpg_world.domain.common.exception import DomainException

from ai_rpg_world.application.world.contracts.commands import UseItemCommand
from ai_rpg_world.application.world.exceptions.base_exception import WorldApplicationException, WorldSystemErrorException
from ai_rpg_world.application.world.exceptions.command.use_command_exception import (
    UseCommandException,
    NoItemInSlotForUseException,
    ItemReservedForUseException,
    ItemNotConsumableException,
    PlayerDownedCannotUseItemException,
    UseItemPlayerNotFoundException,
)


class UseItemApplicationService:
    """消費可能アイテム使用コマンドサービス"""

    def __init__(
        self,
        player_inventory_repository: PlayerInventoryRepository,
        player_status_repository: PlayerStatusRepository,
        item_repository: ItemRepository,
        unit_of_work: UnitOfWork,
        event_publisher: Optional[EventPublisher] = None,
    ):
        self._player_inventory_repository = player_inventory_repository
        self._player_status_repository = player_status_repository
        self._item_repository = item_repository
        self._unit_of_work = unit_of_work
        self._event_publisher = event_publisher
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
            raise NoItemInSlotForUseException(
                context.get("player_id", 0),
                context.get("slot_id", 0),
            )
        except ItemReservedException:
            raise ItemReservedForUseException(
                context.get("player_id", 0),
                context.get("slot_id", 0),
            )
        except DomainException as e:
            raise UseCommandException(
                str(e),
                error_code="DOMAIN_ERROR",
                **context,
            )
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

    def use_item(self, command: UseItemCommand) -> None:
        """指定スロットの消費可能アイテムを使用する"""
        self._execute_with_error_handling(
            operation=lambda: self._use_item_impl(command),
            context={
                "action": "use_item",
                "player_id": command.player_id,
                "slot_id": command.inventory_slot_id,
            },
        )

    def _use_item_impl(self, command: UseItemCommand) -> None:
        with self._unit_of_work:
            player_id = PlayerId(command.player_id)
            slot_id = SlotId(command.inventory_slot_id)

            player_status = self._player_status_repository.find_by_id(player_id)
            if not player_status:
                raise UseItemPlayerNotFoundException(command.player_id)

            if not player_status.can_receive_healing():
                raise PlayerDownedCannotUseItemException(command.player_id, command.inventory_slot_id)

            inventory = self._player_inventory_repository.find_by_id(player_id)
            if not inventory:
                raise UseItemPlayerNotFoundException(command.player_id)

            item_instance_id = inventory.get_item_instance_id_by_slot(slot_id)
            if item_instance_id is None:
                raise NoItemInSlotForUseException(command.player_id, command.inventory_slot_id)

            if inventory.is_item_reserved(item_instance_id):
                raise ItemReservedException(
                    f"Item {item_instance_id} is reserved and cannot be used"
                )

            item = self._item_repository.find_by_id(item_instance_id)
            if not item:
                raise NoItemInSlotForUseException(command.player_id, command.inventory_slot_id)

            if item.item_spec.item_type != ItemType.CONSUMABLE:
                raise ItemNotConsumableException(command.player_id, command.inventory_slot_id)

            item.use()
            self._unit_of_work.add_events_from_aggregate(item)

            if item.quantity == 0:
                self._item_repository.delete(item_instance_id)
                inventory.remove_item_for_placement(slot_id)
                self._player_inventory_repository.save(inventory)
            else:
                self._item_repository.save(item)

            if (
                self._event_publisher
                and item.item_spec.consume_effect is not None
            ):
                self._event_publisher.publish(
                    ConsumableUsedEvent.create(
                        aggregate_id=player_id,
                        aggregate_type="PlayerStatusAggregate",
                        item_spec_id=item.item_spec.item_spec_id,
                    )
                )
