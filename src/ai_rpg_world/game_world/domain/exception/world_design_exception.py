from __future__ import annotations

from collections.abc import Iterable

from ai_rpg_world.game_world.domain.design_flaw import DesignFlaw
from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


def _describe(flaw: DesignFlaw) -> str:
    location = flaw.location
    return f"{location.declaration} {location.name!r} {location.field}: {flaw.reason}"


class BlankDeclaredNameException(GameWorldDomainException):
    error_code = "GAME_WORLD.BLANK_DECLARED_NAME"


class WorldDesignException(GameWorldDomainException):
    error_code = "GAME_WORLD.WORLD_DESIGN"


class NoDesignFlawsException(WorldDesignException):
    error_code = "GAME_WORLD.NO_DESIGN_FLAWS"


class WorldDesignFlawsException(WorldDesignException):
    error_code = "GAME_WORLD.WORLD_DESIGN_FLAWS"

    def __init__(self, flaws: Iterable[DesignFlaw]) -> None:
        self.flaws = tuple(flaws)
        if not self.flaws:
            raise NoDesignFlawsException("WorldDesignFlawsException needs at least one DesignFlaw")
        super().__init__("\n".join(_describe(flaw) for flaw in self.flaws))


class UnknownNameFlaw(WorldDesignException):
    error_code = "GAME_WORLD.UNKNOWN_NAME"

    def __init__(self, flaw: DesignFlaw) -> None:
        self.flaw = flaw
        super().__init__(_describe(flaw))
