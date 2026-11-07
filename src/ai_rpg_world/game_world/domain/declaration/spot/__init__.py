from ai_rpg_world.game_world.domain.declaration.spot.passage_declaration import (
    PassageDeclaration,
    PassageStateDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.spot.spot_atmosphere import NoAmbientSound, NoSmell, SpotAtmosphere
from ai_rpg_world.game_world.domain.declaration.spot.spot_declaration import SpotDeclaration
from ai_rpg_world.game_world.domain.declaration.spot.spot_section_declaration import NoCapacity, SpotSectionDeclaration
from ai_rpg_world.game_world.domain.declaration.spot.temperature import Temperature
from ai_rpg_world.game_world.domain.declaration.spot.unchanged import Unchanged

__all__ = [
    "NoAmbientSound",
    "NoCapacity",
    "NoSmell",
    "PassageDeclaration",
    "PassageStateDeclaration",
    "SpotAtmosphere",
    "SpotDeclaration",
    "SpotSectionDeclaration",
    "Temperature",
    "Unchanged",
]
