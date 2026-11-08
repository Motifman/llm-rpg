from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.object_and_item import ItemSpecDeclaration, ObjectDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.interaction_declaration import InteractionDeclaration


@final
@dataclass(frozen=True)
class ObjectInteractionDeclaration:
    obj: ObjectDeclaration
    interaction: InteractionDeclaration


@final
@dataclass(frozen=True)
class ItemInteractionDeclaration:
    item_spec: ItemSpecDeclaration
    interaction: InteractionDeclaration
