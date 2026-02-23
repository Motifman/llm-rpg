"""
設置・破壊のアプリケーションサービス。

スロット指定で設置可能アイテムをプレイヤー前方に設置し、
前方の設置物を破壊してアイテム化してインベントリに収納する。
"""

import logging
from typing import Callable, Any, Optional

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ChestComponent,
    DoorComponent,
    PlaceableComponent,
    StaticPlaceableInnerComponent,
    GroundItemComponent,
)
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.player.repository.player_inventory_repository import PlayerInventoryRepository
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException

from ai_rpg_world.application.world.contracts.commands import PlaceObjectCommand, DestroyPlaceableCommand
from ai_rpg_world.application.world.exceptions.base_exception import WorldApplicationException, WorldSystemErrorException
from ai_rpg_world.application.world.exceptions.command.place_command_exception import (
    PlaceCommandException,
    ItemNotPlaceableException,
    NoItemInSlotException,
    PlacementSpotNotFoundException,
    PlacementBlockedException,
    NoPlaceableInFrontException,
)


def _build_placeable_component(placeable_object_type: str, item_spec_id: ItemSpecId) -> PlaceableComponent:
    """ItemSpec の placeable_object_type から PlaceableComponent を組み立てる"""
    inner: Any
    if placeable_object_type == "CHEST":
        inner = ChestComponent(is_open=False, item_ids=[])
    elif placeable_object_type == "DOOR":
        inner = DoorComponent(is_open=False, is_locked=False)
    else:
        inner = StaticPlaceableInnerComponent()
    return PlaceableComponent(item_spec_id=item_spec_id, inner=inner, trigger_on_step=None)


class PlaceObjectApplicationService:
    """設置・破壊コマンドサービス"""

    def __init__(
        self,
        physical_map_repository: PhysicalMapRepository,
        player_inventory_repository: PlayerInventoryRepository,
        player_status_repository: PlayerStatusRepository,
        item_repository: ItemRepository,
        item_spec_repository: ItemSpecRepository,
        unit_of_work: UnitOfWork,
    ):
        self._physical_map_repository = physical_map_repository
        self._player_inventory_repository = player_inventory_repository
        self._player_status_repository = player_status_repository
        self._item_repository = item_repository
        self._item_spec_repository = item_spec_repository
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
            )

    def place_object(self, command: PlaceObjectCommand) -> None:
        """指定スロットのアイテムをプレイヤー前方に設置する"""
        self._execute_with_error_handling(
            operation=lambda: self._place_object_impl(command),
            context={
                "action": "place_object",
                "player_id": command.player_id,
                "spot_id": command.spot_id,
                "slot_id": command.inventory_slot_id,
            },
        )

    def _place_object_impl(self, command: PlaceObjectCommand) -> None:
        with self._unit_of_work:
            player_id = PlayerId(command.player_id)
            spot_id = SpotId.create(command.spot_id)
            slot_id = SlotId(command.inventory_slot_id)

            inventory = self._player_inventory_repository.find_by_id(player_id)
            if not inventory:
                raise PlacementSpotNotFoundException(command.player_id, command.spot_id)

            item_instance_id = inventory.get_item_instance_id_by_slot(slot_id)
            if item_instance_id is None:
                raise NoItemInSlotException(command.player_id, command.inventory_slot_id)

            item_aggregate = self._item_repository.find_by_id(item_instance_id)
            if not item_aggregate:
                raise PlaceCommandException(
                    f"Item instance {item_instance_id} not found",
                    error_code="ITEM_NOT_FOUND",
                    player_id=command.player_id,
                    spot_id=command.spot_id,
                )

            item_spec = item_aggregate.item_spec
            if not item_spec.is_placeable_item():
                raise ItemNotPlaceableException(command.player_id, command.inventory_slot_id)

            placeable_object_type = item_spec.get_placeable_object_type()
            if not placeable_object_type:
                raise ItemNotPlaceableException(command.player_id, command.inventory_slot_id)

            player_status = self._player_status_repository.find_by_id(player_id)
            if not player_status or not player_status.current_spot_id or player_status.current_coordinate is None:
                raise PlacementSpotNotFoundException(command.player_id, command.spot_id)

            if player_status.current_spot_id != spot_id:
                raise PlacementSpotNotFoundException(command.player_id, command.spot_id)

            physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
            if not physical_map:
                raise PlacementSpotNotFoundException(command.player_id, command.spot_id)

            actor_id = WorldObjectId.create(int(player_id))
            try:
                actor = physical_map.get_actor(actor_id)
            except ObjectNotFoundException:
                raise PlacementSpotNotFoundException(command.player_id, command.spot_id)

            front_coord = actor.coordinate.neighbor(actor.direction)

            try:
                physical_map.validate_placement(front_coord, is_blocking=True)
            except Exception:
                raise PlacementBlockedException(command.player_id, command.spot_id)

            self._unit_of_work.register_aggregate(physical_map)
            self._unit_of_work.register_aggregate(inventory)

            placed_object_id = self._physical_map_repository.generate_world_object_id()
            component = _build_placeable_component(placeable_object_type, item_spec.item_spec_id)
            object_type = ObjectTypeEnum(placeable_object_type)
            world_object = WorldObject(
                object_id=placed_object_id,
                coordinate=front_coord,
                object_type=object_type,
                is_blocking=True,
                component=component,
            )

            inventory.remove_item_for_placement(slot_id)
            physical_map.add_object(world_object)

            self._player_inventory_repository.save(inventory)
            self._physical_map_repository.save(physical_map)

    def destroy_placeable(self, command: DestroyPlaceableCommand) -> None:
        """プレイヤー前方の設置物を破壊してアイテム化し、インベントリに収納する"""
        self._execute_with_error_handling(
            operation=lambda: self._destroy_placeable_impl(command),
            context={
                "action": "destroy_placeable",
                "player_id": command.player_id,
                "spot_id": command.spot_id,
            },
        )

    def _destroy_placeable_impl(self, command: DestroyPlaceableCommand) -> None:
        with self._unit_of_work:
            player_id = PlayerId(command.player_id)
            spot_id = SpotId.create(command.spot_id)

            player_status = self._player_status_repository.find_by_id(player_id)
            if not player_status or not player_status.current_spot_id or player_status.current_coordinate is None:
                raise PlacementSpotNotFoundException(command.player_id, command.spot_id)

            physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
            if not physical_map:
                raise PlacementSpotNotFoundException(command.player_id, command.spot_id)

            actor_id = WorldObjectId.create(int(player_id))
            try:
                actor = physical_map.get_actor(actor_id)
            except ObjectNotFoundException:
                raise PlacementSpotNotFoundException(command.player_id, command.spot_id)

            front_coord = actor.coordinate.neighbor(actor.direction)
            objects_at_front = physical_map.get_objects_at(front_coord)
            target_object_id: Optional[WorldObjectId] = None
            item_spec_id_to_return: Optional[ItemSpecId] = None

            for obj in objects_at_front:
                if obj.component and isinstance(obj.component, PlaceableComponent):
                    target_object_id = obj.object_id
                    item_spec_id_to_return = obj.component.get_drop_item_spec_id()
                    break

            if target_object_id is None or item_spec_id_to_return is None:
                raise NoPlaceableInFrontException(command.player_id, command.spot_id)

            inventory = self._player_inventory_repository.find_by_id(player_id)
            if not inventory:
                raise PlacementSpotNotFoundException(command.player_id, command.spot_id)

            self._unit_of_work.register_aggregate(physical_map)
            self._unit_of_work.register_aggregate(inventory)

            physical_map.remove_object(target_object_id)

            new_item_instance_id = self._item_repository.generate_item_instance_id()
            from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
            spec_rm = self._item_spec_repository.find_by_id(item_spec_id_to_return)
            if not spec_rm:
                raise PlaceCommandException(
                    f"ItemSpec {item_spec_id_to_return} not found for drop",
                    error_code="ITEM_SPEC_NOT_FOUND",
                    player_id=command.player_id,
                    spot_id=command.spot_id,
                )
            item_spec = spec_rm.to_item_spec()
            new_item = ItemAggregate.create(
                item_instance_id=new_item_instance_id,
                item_spec=item_spec,
                durability=None,
                quantity=1,
            )
            self._item_repository.save(new_item)
            inventory.acquire_item(new_item_instance_id)

            self._physical_map_repository.save(physical_map)
            self._player_inventory_repository.save(inventory)
