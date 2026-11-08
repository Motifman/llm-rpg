from __future__ import annotations

import re

from ai_rpg_world.game_world.domain.design_flaw import (
    DesignFlaw,
    DesignLocation,
    DesignWarning,
    NoScenarioFile,
    ScenarioFile,
)
from ai_rpg_world.game_world.infrastructure.scenario.scenario_layout import Step, YamlPath

_VERB_INSIDE_NOUN: dict[str, tuple[str, tuple[str, ...]]] = {
    "object_interaction": ("object", ("interactions",)),
    "item_interaction": ("item_spec", ("interactions",)),
    "item_use": ("item_spec", ("use",)),
    "section_access": ("section", ("access",)),
    "passage_traversal": ("passage", ()),
    "world_stage_effects": ("world_stage", ()),
    "group_decision_rules": ("group_decision", ()),
}
_TOP_OF_WORLD_FIELD = {"world_rules": "rules", "built_in_action_perceptions": "built_in_action_perceptions"}
_TOP_DECLARATIONS = ("ending", "built_in_action_perceptions")
_FIELD_STEP = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


class ScenarioOrigins:
    def __init__(self) -> None:
        self._by_steps: dict[tuple[Step, ...], ScenarioFile] = {}
        self._declarations: dict[tuple[str, str], YamlPath] = {}
        self._last_file: ScenarioFile | NoScenarioFile = NoScenarioFile()

    def record(self, value: object, file: ScenarioFile, path: YamlPath | None = None) -> None:
        at = path if path is not None else YamlPath.root()
        if not at.steps:
            self._last_file = file
        else:
            if at.steps in self._by_steps and not isinstance(value, dict):
                self._forget_below(at.steps)
            self._by_steps[at.steps] = file
            location = at.location()
            if location.declaration != "world" and location.field == "":
                self._declarations[(location.declaration, location.name)] = at
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(key, str):
                    self.record(child, file, at / key)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                self.record(child, file, at / index)

    def file_of(self, path: YamlPath) -> ScenarioFile | NoScenarioFile:
        steps = path.steps
        while steps:
            if steps in self._by_steps:
                return self._by_steps[steps]
            steps = steps[:-1]
        return self._last_file

    def locate(self, path: YamlPath) -> DesignLocation:
        return path.location().in_file(self.file_of(path))

    def located(self, flaw: DesignFlaw) -> DesignFlaw:
        return DesignFlaw(self._with_file(flaw.location), flaw.reason)

    def located_warning(self, warning: DesignWarning) -> DesignWarning:
        return DesignWarning(self._with_file(warning.location), warning.reason)

    def _with_file(self, location: DesignLocation) -> DesignLocation:
        if not isinstance(location.file, NoScenarioFile):
            return location
        path = self._path_of(location)
        return location if path is None else location.in_file(self.file_of(path))

    def _path_of(self, location: DesignLocation) -> YamlPath | None:
        field_steps = _field_steps(location.field)
        if location.declaration == "world":
            top = _TOP_OF_WORLD_FIELD.get(str(field_steps[0])) if field_steps else None
            return None if top is None else YamlPath((top, *field_steps[1:]))
        if location.declaration in _TOP_DECLARATIONS:
            return YamlPath((location.declaration, *field_steps))
        if location.declaration in _VERB_INSIDE_NOUN:
            noun, inside = _VERB_INSIDE_NOUN[location.declaration]
            noun_name, _, verb_name = location.name.partition("/")
            noun_path = self._declarations.get((noun, noun_name))
            if noun_path is None:
                return None
            verb_steps = (*inside, verb_name) if inside == ("interactions",) else inside
            return YamlPath((*noun_path.steps, *verb_steps, *field_steps))
        declared = self._declarations.get((location.declaration, location.name))
        return None if declared is None else YamlPath((*declared.steps, *field_steps))

    def _forget_below(self, steps: tuple[Step, ...]) -> None:
        for recorded in [recorded for recorded in self._by_steps if recorded[: len(steps)] == steps]:
            del self._by_steps[recorded]


def _field_steps(field: str) -> tuple[Step, ...]:
    return tuple(int(index) if index else name for name, index in _FIELD_STEP.findall(field))
