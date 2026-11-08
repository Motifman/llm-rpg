from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.perception.missed_notice import MissedNotice
from ai_rpg_world.game_world.domain.perception.perceived_quality import PerceivedQuality
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick


@final
@dataclass(frozen=True)
class Perceived:
    perceiver: PersonId
    text: TextWithAssignedPeople
    quality: PerceivedQuality
    happened_at: WorldTick
    calls_attention: bool


@final
@dataclass(frozen=True)
class NotPerceived:
    pass


@final
@dataclass(frozen=True)
class NoticedLater:
    notice: MissedNotice


PerceptionOutcome = Perceived | NotPerceived | NoticedLater
