from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.value_object import DescriptionText


@final
@dataclass(frozen=True)
class CharacterBriefing:
    known_facts: DescriptionText
    objective: DescriptionText
