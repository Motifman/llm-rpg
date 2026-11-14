from __future__ import annotations

import random


class SeedableRandomSource:
    def __init__(self, seed: int | None = None) -> None:
        self._random = random.Random(seed)

    def next_fraction(self) -> float:
        return self._random.random()
