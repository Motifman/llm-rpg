from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar, final

from ai_rpg_world.game_world.domain.design_flaw import DesignFlaw
from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException
from ai_rpg_world.game_world.domain.exception.world_design_exception import (
    UnknownNameFlaw,
    WorldDesignFlawsException,
)
from ai_rpg_world.game_world.infrastructure.scenario.scenario_layout import YamlPath

_Built = TypeVar("_Built")
_Enum = TypeVar("_Enum", bound=Enum)


class Unreadable(Exception):
    def __init__(self, flaw: DesignFlaw) -> None:
        self.flaw = flaw
        super().__init__(str(flaw))


class ReferencesUnreadable(Exception):
    pass


@final
@dataclass(frozen=True)
class YamlNode:
    value: object
    path: YamlPath

    def unreadable(self, reason: str) -> Unreadable:
        return Unreadable(DesignFlaw(self.path.location(), reason))

    def build(self, construct: Callable[[], _Built]) -> _Built:
        try:
            return construct()
        except GameWorldDomainException as error:
            if isinstance(error, (UnknownNameFlaw, WorldDesignFlawsException)):
                raise
            raise self.unreadable(str(error)) from error

    def is_mapping(self) -> bool:
        return isinstance(self.value, dict)

    def fields(self, *allowed: str) -> YamlFields:
        mapping = self._mapping()
        for key in mapping:
            if key not in allowed:
                raise YamlNode(None, self.path / key).unreadable(
                    f"unknown field {key!r}; the fields are {sorted(allowed)}"
                )
        return YamlFields(self, mapping)

    def entries(self) -> list[tuple[str, YamlNode]]:
        return [(key, YamlNode(value, self.path / key)) for key, value in self._mapping().items()]

    def items(self) -> list[YamlNode]:
        if not isinstance(self.value, list):
            raise self.unreadable(f"expected a list, got {self.value!r}")
        return [YamlNode(item, self.path / index) for index, item in enumerate(self.value)]

    def text(self) -> str:
        if not isinstance(self.value, str):
            raise self.unreadable(f"expected text, got {self.value!r}")
        return self.value

    def integer(self) -> int:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise self.unreadable(f"expected a whole number, got {self.value!r}")
        return self.value

    def number(self) -> float:
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise self.unreadable(f"expected a number, got {self.value!r}")
        return float(self.value)

    def boolean(self) -> bool:
        if not isinstance(self.value, bool):
            raise self.unreadable(f"expected true or false, got {self.value!r}")
        return self.value

    def is_null(self) -> bool:
        return self.value is None

    def enum(self, enum_type: type[_Enum]) -> _Enum:
        choices = {member.name.lower(): member for member in enum_type}
        if not isinstance(self.value, str) or self.value not in choices:
            raise self.unreadable(f"expected one of {sorted(choices)}, got {self.value!r}")
        return choices[self.value]

    def _mapping(self) -> dict[str, object]:
        if not isinstance(self.value, dict):
            raise self.unreadable(f"expected a mapping, got {self.value!r}")
        return {str(key): value for key, value in self.value.items()}


@final
class YamlFields:
    def __init__(self, node: YamlNode, mapping: dict[str, object]) -> None:
        self.node = node
        self._mapping = mapping

    def required(self, key: str) -> YamlNode:
        if key not in self._mapping:
            raise YamlNode(None, self.node.path / key).unreadable(f"field {key!r} is required")
        return YamlNode(self._mapping[key], self.node.path / key)

    def optional(self, key: str) -> YamlNode | None:
        if key not in self._mapping:
            return None
        return YamlNode(self._mapping[key], self.node.path / key)

    def nested(self, key: str) -> YamlNode:
        return YamlNode(self._mapping.get(key, {}), self.node.path / key)

    def nested_or_null(self, key: str) -> YamlNode:
        return YamlNode(self._mapping.get(key), self.node.path / key)

    def has(self, key: str) -> bool:
        return key in self._mapping


@final
class FlawCollector:
    def __init__(self) -> None:
        self._flaws: list[DesignFlaw] = []

    @property
    def flaws(self) -> tuple[DesignFlaw, ...]:
        return tuple(self._flaws)

    def attempt(self, read: Callable[[], _Built]) -> _Built | None:
        try:
            return read()
        except Unreadable as unreadable:
            self.record((unreadable.flaw,))
        except UnknownNameFlaw as unknown:
            self.record((unknown.flaw,))
        except WorldDesignFlawsException as flawed:
            self.record(flawed.flaws)
        except ReferencesUnreadable:
            pass
        return None

    def record(self, flaws: tuple[DesignFlaw, ...]) -> None:
        self._flaws.extend(flaw for flaw in flaws if flaw not in self._flaws)
