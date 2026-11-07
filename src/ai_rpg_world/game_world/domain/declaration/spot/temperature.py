from __future__ import annotations

from enum import Enum
from functools import total_ordering


@total_ordering
class Temperature(Enum):
    FREEZING = "FREEZING"
    COLD = "COLD"
    NORMAL = "NORMAL"
    WARM = "WARM"
    HOT = "HOT"

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Temperature):
            return NotImplemented
        return _COLDEST_FIRST.index(self) < _COLDEST_FIRST.index(other)


_COLDEST_FIRST: tuple[Temperature, ...] = tuple(Temperature)
