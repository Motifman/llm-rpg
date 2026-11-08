from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.sound.loudness import Loudness


@final
@dataclass(frozen=True)
class SoundDeclaration:
    loudness: Loudness
    clear: TextWithUnassignedPeople
    muffled: TextWithUnassignedPeople
