from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.declaration.spot import (
    NoAmbientSound,
    NoSmell,
    PassageDeclaration,
    SpotDeclaration,
    Temperature,
    Unchanged,
)
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.value_object import DescriptionText, PassageStateName

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates


@final
@dataclass(frozen=True)
class ChangePassageStateEffect:
    passage: PassageDeclaration
    state: PassageStateName

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.passages().change_state(self.passage, self.state)

    def requirements(self) -> Requirements:
        return Requirements.nothing()


@final
@dataclass(frozen=True)
class RevealPassageEffect:
    passage: PassageDeclaration

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.passages().reveal(self.passage)

    def requirements(self) -> Requirements:
        return Requirements.nothing()


@final
@dataclass(frozen=True)
class RemovePassageEffect:
    passage: PassageDeclaration

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.passages().remove(self.passage)

    def requirements(self) -> Requirements:
        return Requirements.nothing()


@final
@dataclass(frozen=True)
class ChangeAtmosphereEffect:
    spot: SpotDeclaration
    lighting: Lighting | Unchanged
    temperature: Temperature | Unchanged
    ambient_sound: DescriptionText | NoAmbientSound | Unchanged
    smell: DescriptionText | NoSmell | Unchanged

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        changed = (
            facts.atmospheres()
            .atmosphere_of(self.spot)
            .with_changes(
                lighting=self.lighting,
                temperature=self.temperature,
                ambient_sound=self.ambient_sound,
                smell=self.smell,
            )
        )
        world.atmospheres().change(self.spot, changed)

    def requirements(self) -> Requirements:
        return Requirements.nothing()
