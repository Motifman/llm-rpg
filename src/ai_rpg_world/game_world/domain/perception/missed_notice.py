from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.value_object import WorldTick


@final
@dataclass(frozen=True)
class MissedNotice:
    text: TextWithAssignedPeople
    happened_at: WorldTick
