from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.object_and_item import ItemSpecDeclaration
from ai_rpg_world.game_world.domain.effect.effect import Effect


@final
@dataclass(frozen=True)
class ItemUseDeclaration:
    item_spec: ItemSpecDeclaration
    effect: Effect
