from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, TypeVar, final

from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId

_T = TypeVar("_T", covariant=True)
_R = TypeVar("_R")


class ByWhereItemWas(Protocol[_T]):
    def when_carried(self, person: PersonId) -> _T: ...

    def when_lying(self, spot: SpotId) -> _T: ...


@final
@dataclass(frozen=True)
class CarriedBy:
    person: PersonId

    def read(self, cases: ByWhereItemWas[_R]) -> _R:
        return cases.when_carried(self.person)


@final
@dataclass(frozen=True)
class LyingAt:
    spot: SpotId

    def read(self, cases: ByWhereItemWas[_R]) -> _R:
        return cases.when_lying(self.spot)


WhereItemWas = CarriedBy | LyingAt
