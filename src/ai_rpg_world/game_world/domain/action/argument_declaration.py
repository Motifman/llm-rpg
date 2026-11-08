from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName


@final
@dataclass(frozen=True)
class TextArgument:
    pass


@final
@dataclass(frozen=True)
class ItemArgument:
    pass


@final
@dataclass(frozen=True)
class ArgumentDeclaration:
    name: ArgumentName
    kind: TextArgument | ItemArgument
