from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar, Union, final

T = TypeVar("T", covariant=True)
R = TypeVar("R")


class TextsByHearing(Protocol[T]):
    def when_clear(self) -> T: ...

    def when_muffled(self) -> T: ...

    def when_faint(self) -> T: ...

    def when_nothing(self) -> T: ...


@final
@dataclass(frozen=True)
class HearsClearly:
    def read(self, texts: TextsByHearing[R]) -> R:
        return texts.when_clear()


@final
@dataclass(frozen=True)
class HearsMuffled:
    def read(self, texts: TextsByHearing[R]) -> R:
        return texts.when_muffled()


@final
@dataclass(frozen=True)
class HearsFaintly:
    def read(self, texts: TextsByHearing[R]) -> R:
        return texts.when_faint()


@final
@dataclass(frozen=True)
class HearsNothing:
    def read(self, texts: TextsByHearing[R]) -> R:
        return texts.when_nothing()


HearingQuality = Union[HearsClearly, HearsMuffled, HearsFaintly, HearsNothing]
