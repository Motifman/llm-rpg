from __future__ import annotations

from dataclasses import dataclass, replace
from typing import final

from ai_rpg_world.game_world.domain.design_flaw.scenario_file import NoScenarioFile, ScenarioFile

_NOT_FROM_A_FILE = NoScenarioFile()


@final
@dataclass(frozen=True)
class DesignLocation:
    declaration: str
    name: str
    field: str
    file: ScenarioFile | NoScenarioFile = _NOT_FROM_A_FILE

    def in_file(self, file: ScenarioFile | NoScenarioFile) -> DesignLocation:
        return replace(self, file=file)

    def __str__(self) -> str:
        place = f"{self.declaration} {self.name!r} {self.field}"
        if isinstance(self.file, ScenarioFile):
            return f"{self.file}: {place}"
        return place
