from __future__ import annotations

from typing import Protocol


class RandomSource(Protocol):
    def next_fraction(self) -> float: ...
