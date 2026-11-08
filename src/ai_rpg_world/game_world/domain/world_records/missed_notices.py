from __future__ import annotations

from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.value_object import PersonId


class MissedNotices:
    def __init__(self, person: PersonId) -> None:
        self._person = person
        self._notices: list[MissedNotice] = []

    @property
    def person(self) -> PersonId:
        return self._person

    def keep(self, notice: MissedNotice) -> None:
        self._notices.append(notice)

    def clear(self) -> None:
        self._notices.clear()

    def notices(self) -> tuple[MissedNotice, ...]:
        return tuple(self._notices)
