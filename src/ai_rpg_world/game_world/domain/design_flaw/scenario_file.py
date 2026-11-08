from __future__ import annotations

from dataclasses import dataclass
from typing import final


@final
@dataclass(frozen=True)
class ScenarioFile:
    name: str

    def __str__(self) -> str:
        return self.name


@final
@dataclass(frozen=True)
class NoScenarioFile:
    pass
