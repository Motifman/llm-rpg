from __future__ import annotations

from typing import FrozenSet, Protocol

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class SpotGraphTravelContextProvider(Protocol):
    """スポット間移動時の所持品・ワールドフラグを供給する（アプリ層の境界）。"""

    def owned_item_spec_ids_for(self, player_id: PlayerId) -> FrozenSet[ItemSpecId]:
        ...

    def world_flags(self) -> FrozenSet[str]:
        ...
