from __future__ import annotations

from dataclasses import dataclass
from typing import final

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


@final
@dataclass(frozen=True)
class Unidentified:
    pass
