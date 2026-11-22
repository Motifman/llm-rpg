from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.being.contract import PersonInText, UnidentifiedPerson
from ai_rpg_world.game_world.domain.people.person_handle import PersonHandle
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName


@final
@dataclass(frozen=True)
class NoVisibleName:
    pass


@final
@dataclass(frozen=True)
class PersonRef:
    handle: PersonHandle
    appearance: DescriptionText
    visible_name: DisplayName | NoVisibleName

    def for_being(self) -> PersonInText:
        visible = None if isinstance(self.visible_name, NoVisibleName) else self.visible_name.text
        return PersonInText(handle=self.handle.value, appearance=self.appearance.text, visible_name=visible)


@final
@dataclass(frozen=True)
class Unidentified:
    def for_being(self) -> UnidentifiedPerson:
        return UnidentifiedPerson()
