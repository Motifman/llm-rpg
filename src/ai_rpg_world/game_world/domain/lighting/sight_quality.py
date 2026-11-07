from __future__ import annotations

from dataclasses import dataclass
from typing import final


@final
@dataclass(frozen=True)
class SeesClearly:
    pass


@final
@dataclass(frozen=True)
class SeesShapes:
    pass


@final
@dataclass(frozen=True)
class SeesNothing:
    pass


SightQuality = SeesClearly | SeesShapes | SeesNothing
