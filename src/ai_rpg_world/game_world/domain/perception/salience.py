from __future__ import annotations

from dataclasses import dataclass
from typing import final


@final
@dataclass(frozen=True)
class Notable:
    def stands_out(self) -> bool:
        return True


@final
@dataclass(frozen=True)
class Background:
    def stands_out(self) -> bool:
        return False


Salience = Notable | Background
