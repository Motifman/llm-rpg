from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar, final

_T = TypeVar("_T", covariant=True)
_R = TypeVar("_R")


class TextsBySight(Protocol[_T]):
    def when_clear(self) -> _T: ...

    def when_shapes(self) -> _T: ...

    def when_nothing(self) -> _T: ...


@final
@dataclass(frozen=True)
class SeesClearly:
    def read(self, texts: TextsBySight[_R]) -> _R:
        return texts.when_clear()


@final
@dataclass(frozen=True)
class SeesShapes:
    def read(self, texts: TextsBySight[_R]) -> _R:
        return texts.when_shapes()


@final
@dataclass(frozen=True)
class SeesNothing:
    def read(self, texts: TextsBySight[_R]) -> _R:
        return texts.when_nothing()


SightQuality = SeesClearly | SeesShapes | SeesNothing
