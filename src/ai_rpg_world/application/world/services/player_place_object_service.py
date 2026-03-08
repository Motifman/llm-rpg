"""LLM 向けの設置・破壊 facade。"""

from ai_rpg_world.application.world.contracts.commands import (
    DestroyPlaceableCommand,
    PlaceObjectCommand,
)
from ai_rpg_world.application.world.exceptions.command.place_command_exception import (
    PlacementSpotNotFoundException,
)
from ai_rpg_world.application.world.services.place_object_service import (
    PlaceObjectApplicationService,
)
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class PlayerPlaceObjectApplicationService:
    """LLM から使いやすい設置・破壊 API。"""

    def __init__(
        self,
        place_object_service: PlaceObjectApplicationService,
        player_status_repository: PlayerStatusRepository,
    ) -> None:
        self._place_object_service = place_object_service
        self._player_status_repository = player_status_repository

    def place_from_inventory_slot(self, *, player_id: int, inventory_slot_id: int) -> None:
        status = self._player_status_repository.find_by_id(PlayerId.create(player_id))
        if status is None or status.current_spot_id is None:
            raise PlacementSpotNotFoundException(player_id, 0)
        self._place_object_service.place_object(
            PlaceObjectCommand(
                player_id=player_id,
                spot_id=int(status.current_spot_id),
                inventory_slot_id=inventory_slot_id,
            )
        )

    def destroy_in_front(self, *, player_id: int) -> None:
        status = self._player_status_repository.find_by_id(PlayerId.create(player_id))
        if status is None or status.current_spot_id is None:
            raise PlacementSpotNotFoundException(player_id, 0)
        self._place_object_service.destroy_placeable(
            DestroyPlaceableCommand(
                player_id=player_id,
                spot_id=int(status.current_spot_id),
            )
        )
