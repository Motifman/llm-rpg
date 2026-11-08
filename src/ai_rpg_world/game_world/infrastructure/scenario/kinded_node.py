from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.infrastructure.scenario.yaml_node import YamlFields, YamlNode

FAILURE_TEXT = "failure_text"


@final
@dataclass(frozen=True)
class KindedNode:
    kind: str
    body: YamlNode
    failure_text: YamlNode | None

    def single(self, field: str) -> YamlNode:
        if self.body.is_mapping() and isinstance(self.body.value, dict) and set(self.body.value) == {field}:
            return self.body.fields(field).required(field)
        return self.body

    def fields(self, *names: str) -> YamlFields:
        return self.body.fields(*names)

    def nothing(self) -> None:
        if self.body.is_null():
            return
        self.body.fields()


def split_kind(node: YamlNode, kinds: Collection[str], explains_failure: bool) -> KindedNode:
    if isinstance(node.value, str) and node.value in kinds:
        return KindedNode(node.value, YamlNode(None, node.path / node.value), None)
    entries = dict(node.entries())
    failure_text = entries.pop(FAILURE_TEXT, None) if explains_failure else None
    written = sorted(entries)
    if len(written) != 1:
        raise node.unreadable(f"a node needs exactly one kind, got {written}; the kinds are {sorted(kinds)}")
    kind = written[0]
    if kind not in kinds:
        raise entries[kind].unreadable(f"unknown kind {kind!r}; the kinds are {sorted(kinds)}")
    return KindedNode(kind, entries[kind], failure_text)
