"""
InventorySlotOverflowEvent を受けて、溢れたアイテムをプレイヤー位置にドロップ（GROUND_ITEM）する同期ハンドラ。
当たり判定なしのため同一座標に複数ドロップ可能。
"""

import logging

from ai_rpg_world.application.common.exceptions import SystemErrorException
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.player.event.inventory_events import InventorySlotOverflowEvent
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import GroundItemComponent
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum


class InventoryOverflowDropHandler(EventHandler[InventorySlotOverflowEvent]):
    """インベントリ満杯で溢れたアイテムをその場にドロップするハンドラ"""

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        physical_map_repository: PhysicalMapRepository,
    ):
        self._player_status_repository = player_status_repository
        self._physical_map_repository = physical_map_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: InventorySlotOverflowEvent) -> None:
        try:
            self._handle_impl(event)
        except (DomainException, SystemErrorException):
            raise
        except Exception as e:
            self._logger.exception("Unexpected error in InventoryOverflowDropHandler: %s", e)
            raise SystemErrorException(
                f"Inventory overflow drop handling failed: {e}",
                original_exception=e,
            ) from e

    def _handle_impl(self, event: InventorySlotOverflowEvent) -> None:
        player_id = event.aggregate_id
        player_status = self._player_status_repository.find_by_id(player_id)
        if not player_status or not player_status.current_spot_id or player_status.current_coordinate is None:
            self._logger.debug(
                "Player status or position not found for player_id=%s, cannot drop overflow item",
                event.aggregate_id,
            )
            return

        physical_map = self._physical_map_repository.find_by_spot_id(player_status.current_spot_id)
        if not physical_map:
            self._logger.debug(
                "Physical map not found for spot_id=%s, cannot drop overflow item",
                player_status.current_spot_id,
            )
            return

        coord = player_status.current_coordinate
        ground_object_id = self._physical_map_repository.generate_world_object_id()
        component = GroundItemComponent(item_instance_id=event.overflowed_item_instance_id)
        world_object = WorldObject(
            object_id=ground_object_id,
            coordinate=coord,
            object_type=ObjectTypeEnum.GROUND_ITEM,
            is_blocking=False,
            component=component,
        )
        physical_map.add_object(world_object)
        self._physical_map_repository.save(physical_map)
        self._logger.debug(
            "Dropped overflow item %s at spot %s coord %s for player %s",
            event.overflowed_item_instance_id,
            player_status.current_spot_id,
            coord,
            event.aggregate_id,
        )
