from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.lighting.sight_quality import SeesClearly, SeesShapes
from ai_rpg_world.game_world.domain.sound.hearing_quality import HearsClearly, HearsFaintly, HearsMuffled


@final
@dataclass(frozen=True)
class Felt:
    pass


@final
@dataclass(frozen=True)
class Told:
    pass


PerceivedQuality = SeesClearly | SeesShapes | HearsClearly | HearsMuffled | HearsFaintly | Felt | Told
