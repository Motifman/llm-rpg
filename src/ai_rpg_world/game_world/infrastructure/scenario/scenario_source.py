from __future__ import annotations

from pathlib import Path

from ai_rpg_world.game_world.domain.design_flaw import DesignFlaw
from ai_rpg_world.game_world.infrastructure.scenario.scenario_layout import YamlPath
from ai_rpg_world.game_world.infrastructure.scenario.yaml_document import YamlDocument, read_yaml_document

_INCLUDES = "includes"


def read_scenario_source(scenario: Path) -> YamlDocument:
    document = _read_file(scenario)
    if not isinstance(document.value, dict):
        if document.flaws:
            return document
        return YamlDocument(None, (DesignFlaw(YamlPath.root().location(), "a scenario must be a mapping"),))
    flaws = list(document.flaws)
    written = dict(document.value)
    includes = written.pop(_INCLUDES, [])
    at = YamlPath.root() / _INCLUDES
    if not isinstance(includes, list):
        return YamlDocument(written, (*flaws, DesignFlaw(at.location(), "includes must be a list of files")))
    merged: dict[object, object] = {}
    for index, name in enumerate(includes):
        included = _included(scenario.parent, name, at / index, flaws)
        merged = _overlaid(merged, included)
    return YamlDocument(_overlaid(merged, written), tuple(flaws))


def _included(directory: Path, name: object, at: YamlPath, flaws: list[DesignFlaw]) -> dict[object, object]:
    if not isinstance(name, str):
        flaws.append(DesignFlaw(at.location(), f"an include must be a file name, got {name!r}"))
        return {}
    path = directory / name
    if not path.is_file():
        flaws.append(DesignFlaw(at.location(), f"include {name!r} is not found"))
        return {}
    try:
        document = _read_file(path)
    except (OSError, UnicodeDecodeError) as error:
        flaws.append(DesignFlaw(at.location(), f"include {name!r} is not readable: {error}"))
        return {}
    flaws.extend(DesignFlaw(flaw.location, f"in {name}: {flaw.reason}") for flaw in document.flaws)
    if not isinstance(document.value, dict):
        if not document.flaws:
            flaws.append(DesignFlaw(at.location(), f"include {name!r} must be a mapping"))
        return {}
    if _INCLUDES in document.value:
        flaws.append(DesignFlaw(at.location(), f"include {name!r} must not include other files"))
    return {key: value for key, value in document.value.items() if key != _INCLUDES}


def _read_file(path: Path) -> YamlDocument:
    return read_yaml_document(path.read_text(encoding="utf-8"))


def _overlaid(base: dict[object, object], overlay: dict[object, object]) -> dict[object, object]:
    merged = dict(base)
    for key, value in overlay.items():
        below = merged.get(key)
        if isinstance(below, dict) and isinstance(value, dict):
            merged[key] = _overlaid(below, value)
        else:
            merged[key] = value
    return merged
