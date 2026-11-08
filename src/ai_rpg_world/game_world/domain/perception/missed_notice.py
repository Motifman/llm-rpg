from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen
from ai_rpg_world.game_world.domain.people.text_about_people import TextAboutPeople
from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.perception.not_noticed_later import NotNoticedLater
from ai_rpg_world.game_world.domain.value_object import WorldTick


@final
@dataclass(frozen=True)
class MissedNotice:
    text: TextWithAssignedPeople
    happened_at: WorldTick

    @classmethod
    def from_text(
        cls, noticed_later: TextAboutPeople | NotNoticedLater, view: PeopleAsSeen, at: WorldTick
    ) -> MissedNotice | NotNoticedLater:
        if isinstance(noticed_later, NotNoticedLater):
            return NotNoticedLater()
        return cls(text=noticed_later.seen_by(view), happened_at=at)
