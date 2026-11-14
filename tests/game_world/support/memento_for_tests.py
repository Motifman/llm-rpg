from __future__ import annotations

from typing import Any, Protocol, TypeVar

_Rebuilt = TypeVar("_Rebuilt", bound="RebuildsFromMemento")


class RebuildsFromMemento(Protocol):
    def memento(self) -> Any: ...

    @classmethod
    def from_memento(cls: type[_Rebuilt], memento: Any, *reading: Any) -> _Rebuilt: ...


def rebuilt_from_memento(original: _Rebuilt, *reading: Any) -> _Rebuilt:
    return type(original).from_memento(original.memento(), *reading)
