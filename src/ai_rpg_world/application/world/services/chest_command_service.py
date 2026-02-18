"""
チェスト収納・取得のアプリケーションサービス。

Command でプレイヤーが選んだ「どのアイテムを」「どのチェストに」を受け取り、
PhysicalMapAggregate に情報を注入してイベントを発行し、
イベントハンドラがプレイヤーインベントリを更新する。
"""

import logging
from typing import Callable, Any

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.repository.player_inventory_repository import PlayerInventoryRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.world.entity.world_object_component import ChestComponent
from ai_rpg_world.domain.world.exception.map_exception import (
    ObjectNotFoundException,
    ItemNotInChestException as DomainItemNotInChestException,
)

from ai_rpg_world.application.world.contracts.commands import (
    StoreItemInChestCommand,
    TakeItemFromChestCommand,
)
from ai_rpg_world.application.world.exceptions.base_exception import WorldApplicationException, WorldSystemErrorException
from ai_rpg_world.application.world.exceptions.command.chest_command_exception import (
    ChestCommandException,
    ChestNotFoundException,
    ItemNotInPlayerInventoryException,
    PlayerInventoryNotFoundException,
    ItemNotInChestCommandException,
)


class ChestCommandService:
    """チェスト収納・取得コマンドサービス"""

    def __init__(
        self,
        physical_map_repository: PhysicalMapRepository,
        player_inventory_repository: PlayerInventoryRepository,
        unit_of_work: UnitOfWork,
    ):
        self._physical_map_repository = physical_map_repository
        self._player_inventory_repository = player_inventory_repository
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
            raise ChestCommandException(str(e), **context)
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

    def store_item_in_chest(self, command: StoreItemInChestCommand) -> None:
        """チェストにアイテムを収納する。"""
        self._execute_with_error_handling(
            operation=lambda: self._store_item_in_chest_impl(command),
            context={
                "action": "store_item_in_chest",
                "player_id": command.player_id,
                "spot_id": command.spot_id,
                "chest_id": command.chest_world_object_id,
                "item_instance_id": command.item_instance_id,
            },
        )

    def _store_item_in_chest_impl(self, command: StoreItemInChestCommand) -> None:
        with self._unit_of_work:
            spot_id = SpotId.create(command.spot_id)
            physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
            if not physical_map:
                raise ChestNotFoundException(command.spot_id, command.chest_world_object_id)

            try:
                chest_obj = physical_map.get_object(WorldObjectId.create(command.chest_world_object_id))
            except ObjectNotFoundException:
                raise ChestNotFoundException(command.spot_id, command.chest_world_object_id)
            if not isinstance(chest_obj.component, ChestComponent):
                raise ChestNotFoundException(command.spot_id, command.chest_world_object_id)

            player_id = PlayerId.create(command.player_id)
            inventory = self._player_inventory_repository.find_by_id(player_id)
            if not inventory:
                raise PlayerInventoryNotFoundException(command.player_id)

            item_instance_id = ItemInstanceId.create(command.item_instance_id)
            if not inventory.has_item(item_instance_id):
                raise ItemNotInPlayerInventoryException(command.player_id, command.item_instance_id)

            self._unit_of_work.register_aggregate(physical_map)
            physical_map.store_item_in_chest(
                actor_id=WorldObjectId.create(command.actor_world_object_id),
                target_chest_id=WorldObjectId.create(command.chest_world_object_id),
                item_instance_id=item_instance_id,
                player_id_value=command.player_id,
            )
            self._physical_map_repository.save(physical_map)

    def take_item_from_chest(self, command: TakeItemFromChestCommand) -> None:
        """チェストからアイテムを取得する。"""
        self._execute_with_error_handling(
            operation=lambda: self._take_item_from_chest_impl(command),
            context={
                "action": "take_item_from_chest",
                "player_id": command.player_id,
                "spot_id": command.spot_id,
                "chest_id": command.chest_world_object_id,
                "item_instance_id": command.item_instance_id,
            },
        )

    def _take_item_from_chest_impl(self, command: TakeItemFromChestCommand) -> None:
        with self._unit_of_work:
            spot_id = SpotId.create(command.spot_id)
            physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
            if not physical_map:
                raise ChestNotFoundException(command.spot_id, command.chest_world_object_id)

            try:
                chest_obj = physical_map.get_object(WorldObjectId.create(command.chest_world_object_id))
            except ObjectNotFoundException:
                raise ChestNotFoundException(command.spot_id, command.chest_world_object_id)
            if not isinstance(chest_obj.component, ChestComponent):
                raise ChestNotFoundException(command.spot_id, command.chest_world_object_id)

            player_id = PlayerId.create(command.player_id)
            inventory = self._player_inventory_repository.find_by_id(player_id)
            if not inventory:
                raise PlayerInventoryNotFoundException(command.player_id)

            item_instance_id = ItemInstanceId.create(command.item_instance_id)
            self._unit_of_work.register_aggregate(physical_map)
            try:
                physical_map.take_item_from_chest(
                    actor_id=WorldObjectId.create(command.actor_world_object_id),
                    target_chest_id=WorldObjectId.create(command.chest_world_object_id),
                    item_instance_id=item_instance_id,
                    player_id_value=command.player_id,
                )
            except DomainItemNotInChestException:
                raise ItemNotInChestCommandException(
                    command.spot_id,
                    command.chest_world_object_id,
                    command.item_instance_id,
                )
            self._physical_map_repository.save(physical_map)
