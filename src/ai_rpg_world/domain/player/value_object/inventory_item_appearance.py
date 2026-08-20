from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId


@dataclass(frozen=True)
class InventoryItemAppearance:
    """所持品探索用に、他集約から渡された見た目。リポジトリではない。"""

    item_spec_id: ItemSpecId
    is_spoiled: bool
