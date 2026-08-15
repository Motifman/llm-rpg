from ai_rpg_world.application.inventory.contracts.dtos import (
    PlayerInventoryItemView,
    PlayerInventoryView,
)
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class PlayerInventoryQueryService:
    """プレイヤー所持品の照会サービス。"""

    def __init__(
        self,
        player_inventory_repository: PlayerInventoryRepository,
        item_repository: ItemRepository,
    ) -> None:
        self._player_inventory_repository = player_inventory_repository
        self._item_repository = item_repository

    def list_held_items(self, player_id: PlayerId) -> PlayerInventoryView:
        inv = self._player_inventory_repository.find_by_id(player_id)
        if inv is None:
            return PlayerInventoryView(items=())

        counts: dict[int, int] = {}
        specs: dict[int, tuple[str, str]] = {}
        for _slot_id, iid in inv.iter_occupied_slots():
            item = self._item_repository.find_by_id(iid)
            if item is None:
                continue
            sid = item.item_spec.item_spec_id.value
            counts[sid] = counts.get(sid, 0) + 1
            if sid not in specs:
                specs[sid] = (item.item_spec.name, item.item_spec.description)

        items = tuple(
            PlayerInventoryItemView(
                item_spec_id=sid,
                name=specs[sid][0],
                description=specs[sid][1],
                quantity=counts[sid],
            )
            for sid in specs
        )
        return PlayerInventoryView(items=items)
