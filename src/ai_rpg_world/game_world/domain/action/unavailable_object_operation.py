from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.people import TextAboutPeople
from ai_rpg_world.game_world.domain.value_object import DisplayName, ObjectId


@final
@dataclass(frozen=True)
class UnavailableObjectOperation:
    obj: ObjectId
    label: DisplayName
    reason: TextAboutPeople
