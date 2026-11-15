from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.perception.perceived_quality import NoticedOnWaking
from ai_rpg_world.game_world.domain.perception.perception_outcome import Perceived
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick


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
    def from_memento(cls, memento: MissedNoticesMemento) -> MissedNotices:
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

    def perceived_on_waking(self, woke_at: WorldTick) -> tuple[Perceived, ...]:
        # 倒れている間の時刻で渡すと、Being が時刻で並べ直して「目が覚めた」より前に記憶に入る。
        return tuple(
            Perceived(
                perceiver=self._person,
                text=notice.text,
                quality=NoticedOnWaking(),
                happened_at=woke_at,
                calls_attention=False,
            )
            for notice in self._notices
        )
