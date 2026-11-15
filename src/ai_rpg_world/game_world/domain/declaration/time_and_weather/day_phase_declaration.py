from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.declaration.no_announcement import NoAnnouncement
from ai_rpg_world.game_world.domain.declaration.time_and_weather.day_phase_name import DayPhaseName
from ai_rpg_world.game_world.domain.declaration.time_and_weather.everyone_awake import EveryoneAwake
from ai_rpg_world.game_world.domain.declaration.time_and_weather.time_of_day import TimeOfDay
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.perception.stimulus import Stimulus


@final
@dataclass(frozen=True)
class DayPhaseDeclaration:
    name: DayPhaseName
    begins_at: TimeOfDay
    dark: bool
    announcement: TextWithUnassignedPeople | NoAnnouncement
    audience: PeopleSelection | EveryoneAwake

    def addressees(self, facts: WorldFacts, at: WorldTick) -> frozenset[PersonId]:
        # action と perception をモジュールの頭で import すると循環する。
        from ai_rpg_world.game_world.domain.action.trigger import WorldTimePassing

        chosen = self.audience.select(facts, WorldTimePassing(at))
        # 倒れている人にためると、目覚めたときに古い時間帯が届いて今の時刻と食い違う (D2203)。
        return frozenset(
            person
            for person in chosen
            if not facts.vitals(person).is_down() and not facts.outcomes().has_left_the_world(person)
        )

    def stimuli_when_entered(self, audience: frozenset[PersonId], at: WorldTick) -> tuple[Stimulus, ...]:
        from ai_rpg_world.game_world.domain.perception.announcement_stimulus import AnnouncementStimulus
        from ai_rpg_world.game_world.domain.perception.salience import Background

        if isinstance(self.announcement, NoAnnouncement):
            return ()
        return (
            AnnouncementStimulus(
                audience=audience,
                text=self.announcement.about({}),
                salience=Background(),
                at=at,
                kept_while_fainted=False,
            ),
        )
