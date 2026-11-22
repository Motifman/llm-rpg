from __future__ import annotations

from dataclasses import dataclass
from typing import final


@final
@dataclass(frozen=True)
class FreeToAct:
    pass


@final
@dataclass(frozen=True)
class InTheMiddleOfAction:
    pass


@final
@dataclass(frozen=True)
class UnableToAct:
    pass


ReadinessToAct = FreeToAct | InTheMiddleOfAction | UnableToAct
