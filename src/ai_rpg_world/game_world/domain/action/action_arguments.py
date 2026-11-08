from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.exception.action_argument_exception import BlankTextArgumentException
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName


@final
@dataclass(frozen=True)
class TextArgumentValue:
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise BlankTextArgumentException(f"TextArgumentValue must be non-blank, got {self.text!r}")


ActionArguments = Mapping[ArgumentName, TextArgumentValue | ItemInstanceId]
