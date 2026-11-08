from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar, Union, final

_T = TypeVar("_T", covariant=True)
_R = TypeVar("_R")


class TextsByHearing(Protocol[_T]):
    def when_clear(self) -> _T: ...

    def when_muffled(self) -> _T: ...

    def when_faint(self) -> _T: ...

    def when_nothing(self) -> _T: ...


@final
@dataclass(frozen=True)
class HearsClearly:
    def read(self, texts: TextsByHearing[_R]) -> _R:
        return texts.when_clear()


@final
@dataclass(frozen=True)
class HearsMuffled:
    def read(self, texts: TextsByHearing[_R]) -> _R:
        return texts.when_muffled()


@final
@dataclass(frozen=True)
class HearsFaintly:
    def read(self, texts: TextsByHearing[_R]) -> _R:
        return texts.when_faint()


@final
@dataclass(frozen=True)
class HearsNothing:
    def read(self, texts: TextsByHearing[_R]) -> _R:
        return texts.when_nothing()


HearingQuality = Union[HearsClearly, HearsMuffled, HearsFaintly, HearsNothing]
