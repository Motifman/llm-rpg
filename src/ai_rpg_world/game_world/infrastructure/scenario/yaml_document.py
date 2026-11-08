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
    walk = _Walk()
    try:
        value = walk.plain(node, YamlPath.root())
    except yaml.YAMLError as error:
        return YamlDocument(None, (DesignFlaw(YamlPath.root().location(), f"not readable as YAML: {error}"),))
    except _TooLarge:
        return YamlDocument(
            None, (DesignFlaw(YamlPath.root().location(), f"expands into more than {_MOST_NODES} nodes"),)
        )
    return YamlDocument(value, tuple(walk.flaws))


class _TooLarge(Exception):
    pass


_MOST_NODES = 200_000


class _Walk:
    def __init__(self) -> None:
        self.flaws: list[DesignFlaw] = []
        self._visited = 0
        self._inside: set[int] = set()

    def plain(self, node: yaml.Node, path: YamlPath) -> object:
        self._visited += 1
        if self._visited > _MOST_NODES:
            raise _TooLarge()
        if id(node) in self._inside:
            self.flaws.append(DesignFlaw(path.location(), "an alias refers to a node that contains it"))
            return None
        if isinstance(node, yaml.MappingNode):
            self._inside.add(id(node))
            mapping = self._mapping(node, path)
            self._inside.discard(id(node))
            return mapping
        if isinstance(node, yaml.SequenceNode):
            self._inside.add(id(node))
            items = [self.plain(item, path / index) for index, item in enumerate(node.value)]
            self._inside.discard(id(node))
            return items
        scalar: object = yaml.SafeLoader("").construct_object(node)  # type: ignore[no-untyped-call]
        return scalar

    def _mapping(self, node: yaml.MappingNode, path: YamlPath) -> dict[object, object]:
        mapping: dict[object, object] = {}
        for key_node, value_node in node.value:
            key = self.plain(key_node, path)
            if not isinstance(key, str):
                self.flaws.append(DesignFlaw(path.location(), f"a key must be a word, got {key!r}"))
                continue
            if key in mapping:
                self.flaws.append(DesignFlaw((path / key).location(), f"key {key!r} is written more than once"))
                continue
            mapping[key] = self.plain(value_node, path / key)
        return mapping
