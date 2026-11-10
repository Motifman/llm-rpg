from __future__ import annotations

from functools import cache
from typing import Any, Protocol, TypeVar

from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from tests.game_world.support.world_design_for_tests import compose_world

_Rebuilt = TypeVar("_Rebuilt", bound="RebuildsFromMemento")


class RebuildsFromMemento(Protocol):
    def memento(self) -> Any: ...

    @classmethod
    def from_memento(cls: type[_Rebuilt], memento: Any, design: WorldDesign) -> _Rebuilt: ...


@cache
def _empty_design() -> WorldDesign:
    return compose_world()


def rebuilt_from_memento(original: _Rebuilt, design: WorldDesign | None = None) -> _Rebuilt:
    return type(original).from_memento(original.memento(), design if design is not None else _empty_design())
