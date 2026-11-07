from __future__ import annotations

from enum import Enum

from ai_rpg_world.game_world.domain.lighting.sight_quality import SeesClearly, SeesNothing, SeesShapes, SightQuality


class Lighting(Enum):
    BRIGHT = "BRIGHT"
    DUSKY = "DUSKY"
    DARK = "DARK"
    PITCH_DARK = "PITCH_DARK"

    def sight(self) -> SightQuality:
        return _SIGHT[self]


_SIGHT: dict[Lighting, SightQuality] = {
    Lighting.BRIGHT: SeesClearly(),
    Lighting.DUSKY: SeesClearly(),
    Lighting.DARK: SeesShapes(),
    Lighting.PITCH_DARK: SeesNothing(),
}
