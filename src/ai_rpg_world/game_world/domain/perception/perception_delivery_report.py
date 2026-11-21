from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import final

from ai_rpg_world.game_world.domain.perception.delivery_rank import Sense
from ai_rpg_world.game_world.domain.perception.not_perceived_reason import NotPerceivedReason
from ai_rpg_world.game_world.domain.perception.perception_cause import PerceptionCause
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts.location import NotAtSpot


@final
@dataclass(frozen=True)
class StimulusDescription:
    sense: Sense
    text: str
    where: SpotId | NotAtSpot
    addressed_to: frozenset[PersonId]


@final
@dataclass(frozen=True)
class StimulusDeliveryResult:
    stimulus: StimulusDescription
    perceived_by: tuple[PersonId, ...]
    kept_for: tuple[PersonId, ...]
    missed_by: Mapping[PersonId, NotPerceivedReason] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "missed_by", MappingProxyType(dict(self.missed_by)))


@final
@dataclass(frozen=True)
class PerceptionDeliveryReport:
    cause: PerceptionCause
    at: WorldTick
    stimuli: tuple[StimulusDeliveryResult, ...]
