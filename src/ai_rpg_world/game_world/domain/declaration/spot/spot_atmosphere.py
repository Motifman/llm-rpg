from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TypeVar, final

from ai_rpg_world.game_world.domain.declaration.spot.temperature import Temperature
from ai_rpg_world.game_world.domain.declaration.spot.unchanged import Unchanged
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.value_object import DescriptionText


@final
@dataclass(frozen=True)
class NoAmbientSound:
    pass


@final
@dataclass(frozen=True)
class NoSmell:
    pass


@final
@dataclass(frozen=True)
class SpotAtmosphere:
    lighting: Lighting
    outdoor: bool
    temperature: Temperature
    ambient_sound: DescriptionText | NoAmbientSound
    smell: DescriptionText | NoSmell

    def with_changes(
        self,
        lighting: Lighting | Unchanged,
        temperature: Temperature | Unchanged,
        ambient_sound: DescriptionText | NoAmbientSound | Unchanged,
        smell: DescriptionText | NoSmell | Unchanged,
    ) -> SpotAtmosphere:
        return replace(
            self,
            lighting=_kept_or(self.lighting, lighting),
            temperature=_kept_or(self.temperature, temperature),
            ambient_sound=_kept_or(self.ambient_sound, ambient_sound),
            smell=_kept_or(self.smell, smell),
        )


_Field = TypeVar("_Field")


def _kept_or(current: _Field, change: _Field | Unchanged) -> _Field:
    if isinstance(change, Unchanged):
        return current
    return change
