from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.action.action_arguments import TextArgumentValue
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName


@final
@dataclass(frozen=True)
class TextArgument:
    def accepts(self, value: TextArgumentValue | ItemInstanceId) -> bool:
        return isinstance(value, TextArgumentValue)


@final
@dataclass(frozen=True)
class ItemArgument:
    def accepts(self, value: TextArgumentValue | ItemInstanceId) -> bool:
        return isinstance(value, ItemInstanceId)


@final
@dataclass(frozen=True)
class ArgumentDeclaration:
    name: ArgumentName
    kind: TextArgument | ItemArgument

    def accepts(self, value: TextArgumentValue | ItemInstanceId) -> bool:
        return self.kind.accepts(value)
