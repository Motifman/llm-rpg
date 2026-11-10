from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.value_object import PersonId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign


@final
@dataclass(frozen=True)
class MissedNoticesMemento:
    person: PersonId
    notices: tuple[MissedNotice, ...]


class MissedNotices:
    def __init__(self, person: PersonId, notices: Sequence[MissedNotice]) -> None:
        self._person = person
        self._notices = list(notices)

    @classmethod
    def start(cls, person: PersonId) -> MissedNotices:
        return cls(person, ())

    @classmethod
    def from_memento(cls, memento: MissedNoticesMemento, design: WorldDesign) -> MissedNotices:
        return cls(memento.person, memento.notices)

    @property
    def person(self) -> PersonId:
        return self._person

    def memento(self) -> MissedNoticesMemento:
        return MissedNoticesMemento(person=self._person, notices=tuple(self._notices))

    def keep(self, notice: MissedNotice) -> None:
        self._notices.append(notice)

    def clear(self) -> None:
        self._notices.clear()

    def notices(self) -> tuple[MissedNotice, ...]:
        return tuple(self._notices)
