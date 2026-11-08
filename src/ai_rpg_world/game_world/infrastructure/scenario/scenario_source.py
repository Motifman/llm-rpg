from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import final

from ai_rpg_world.game_world.domain.design_flaw import DesignFlaw, DesignLocation, ScenarioFile
from ai_rpg_world.game_world.infrastructure.scenario.scenario_layout import YamlPath
from ai_rpg_world.game_world.infrastructure.scenario.scenario_origins import ScenarioOrigins
from ai_rpg_world.game_world.infrastructure.scenario.yaml_document import YamlDocument, read_yaml_document

_INCLUDES = "includes"


@final
@dataclass(frozen=True)
class ScenarioSource:
    value: object
    flaws: tuple[DesignFlaw, ...]
    origins: ScenarioOrigins


def read_scenario_source(scenario: Path) -> ScenarioSource:
    file = ScenarioFile(scenario.name)
    origins = ScenarioOrigins()
    document = _read_file(scenario, file)
    if not isinstance(document.value, dict):
        if document.flaws:
            return ScenarioSource(None, document.flaws, origins)
        flaw = DesignFlaw(YamlPath.root().location().in_file(file), "a scenario must be a mapping")
        return ScenarioSource(None, (flaw,), origins)
    flaws = list(document.flaws)
    written = dict(document.value)
    includes = written.pop(_INCLUDES, [])
    at = YamlPath.root() / _INCLUDES
    if not isinstance(includes, list):
        flaws.append(DesignFlaw(at.location().in_file(file), "includes must be a list of files"))
        includes = []
    merged: dict[object, object] = {}
    for index, name in enumerate(includes):
        included = _included(scenario.parent, name, (at / index).location().in_file(file), flaws)
        if included is None:
            continue
        included_value, included_file = included
        origins.record(included_value, included_file)
        merged = _overlaid(merged, included_value)
    origins.record(written, file)
    return ScenarioSource(_overlaid(merged, written), tuple(flaws), origins)


def _included(
    directory: Path, name: object, at: DesignLocation, flaws: list[DesignFlaw]
) -> tuple[dict[object, object], ScenarioFile] | None:
    if not isinstance(name, str):
        flaws.append(DesignFlaw(at, f"an include must be a file name, got {name!r}"))
        return None
    path = directory / name
    if not path.is_file():
        flaws.append(DesignFlaw(at, f"include {name!r} is not found"))
        return None
    file = ScenarioFile(name)
    try:
        document = _read_file(path, file)
    except (OSError, UnicodeDecodeError) as error:
        flaws.append(DesignFlaw(at, f"include {name!r} is not readable: {error}"))
        return None
    flaws.extend(document.flaws)
    if not isinstance(document.value, dict):
        if not document.flaws:
            flaws.append(DesignFlaw(at, f"include {name!r} must be a mapping"))
        return None
    if _INCLUDES in document.value:
        flaws.append(DesignFlaw(at, f"include {name!r} must not include other files"))
    return {key: value for key, value in document.value.items() if key != _INCLUDES}, file


def _read_file(path: Path, file: ScenarioFile) -> YamlDocument:
    document = read_yaml_document(path.read_text(encoding="utf-8"))
    return YamlDocument(
        document.value, tuple(DesignFlaw(flaw.location.in_file(file), flaw.reason) for flaw in document.flaws)
    )


def _overlaid(base: dict[object, object], overlay: dict[object, object]) -> dict[object, object]:
    merged = dict(base)
    for key, value in overlay.items():
        below = merged.get(key)
        if isinstance(below, dict) and isinstance(value, dict):
            merged[key] = _overlaid(below, value)
        else:
            merged[key] = value
    return merged
