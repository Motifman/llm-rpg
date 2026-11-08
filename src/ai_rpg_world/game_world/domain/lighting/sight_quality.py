from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar, final

T = TypeVar("T", covariant=True)
R = TypeVar("R")


class TextsBySight(Protocol[T]):
    def when_clear(self) -> T: ...

    def when_shapes(self) -> T: ...

    def when_nothing(self) -> T: ...


@final
@dataclass(frozen=True)
class SeesClearly:
    def read(self, texts: TextsBySight[R]) -> R:
        return texts.when_clear()


@final
@dataclass(frozen=True)
class SeesShapes:
    def read(self, texts: TextsBySight[R]) -> R:
        return texts.when_shapes()


@final
@dataclass(frozen=True)
class SeesNothing:
    def read(self, texts: TextsBySight[R]) -> R:
        return texts.when_nothing()


SightQuality = SeesClearly | SeesShapes | SeesNothing
