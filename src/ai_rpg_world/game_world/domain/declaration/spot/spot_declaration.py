from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.spot.spot_atmosphere import SpotAtmosphere
from ai_rpg_world.game_world.domain.value_object import DescriptionText, DisplayName, SpotId


@final
@dataclass(frozen=True)
class SpotDeclaration:
    spot_id: SpotId
    name: DisplayName
    description: DescriptionText
    atmosphere: SpotAtmosphere
