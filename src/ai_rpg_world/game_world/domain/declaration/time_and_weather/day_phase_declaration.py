from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.no_announcement import NoAnnouncement
from ai_rpg_world.game_world.domain.declaration.time_and_weather.day_phase_name import DayPhaseName
from ai_rpg_world.game_world.domain.declaration.time_and_weather.time_of_day import TimeOfDay
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople


@final
@dataclass(frozen=True)
class DayPhaseDeclaration:
    name: DayPhaseName
    begins_at: TimeOfDay
    dark: bool
    announcement: TextWithUnassignedPeople | NoAnnouncement
