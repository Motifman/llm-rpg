from __future__ import annotations

from dataclasses import dataclass
from typing import final

import yaml

from ai_rpg_world.game_world.domain.design_flaw import DesignFlaw
from ai_rpg_world.game_world.infrastructure.scenario.scenario_layout import YamlPath


@final
@dataclass(frozen=True)
class YamlDocument:
    value: object
    flaws: tuple[DesignFlaw, ...]


def read_yaml_document(text: str) -> YamlDocument:
    try:
        node = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError as error:
        return YamlDocument(None, (DesignFlaw(YamlPath.root().location(), f"not readable as YAML: {error}"),))
    if node is None:
        return YamlDocument({}, ())
    flaws: list[DesignFlaw] = []
    try:
        value = _plain(node, YamlPath.root(), flaws)
    except yaml.YAMLError as error:
        return YamlDocument(None, (DesignFlaw(YamlPath.root().location(), f"not readable as YAML: {error}"),))
    return YamlDocument(value, tuple(flaws))


def _plain(node: yaml.Node, path: YamlPath, flaws: list[DesignFlaw]) -> object:
    if isinstance(node, yaml.MappingNode):
        mapping: dict[object, object] = {}
        for key_node, value_node in node.value:
            key = _plain(key_node, path, flaws)
            if not isinstance(key, (str, int)):
                flaws.append(DesignFlaw(path.location(), f"a key must be a word, got {key!r}"))
                continue
            if key in mapping:
                flaws.append(DesignFlaw((path / key).location(), f"key {key!r} is written more than once"))
                continue
            mapping[key] = _plain(value_node, path / key, flaws)
        return mapping
    if isinstance(node, yaml.SequenceNode):
        return [_plain(item, path / index, flaws) for index, item in enumerate(node.value)]
    scalar: object = yaml.SafeLoader("").construct_object(node)  # type: ignore[no-untyped-call]
    return scalar
