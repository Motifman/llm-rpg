from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.exception.game_world_exception import RepeatedMementoKeyException
from ai_rpg_world.game_world.domain.value_object import Ticks, WorldId, WorldTick
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.value_object.reaction_id import ReactionId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.verb.happening_declaration import HappeningDeclaration
    from ai_rpg_world.game_world.domain.declaration.verb.reaction_declaration import ReactionDeclaration
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign


@final
@dataclass(frozen=True)
class NeverFired:
    def has_passed(self, ticks: Ticks, now: WorldTick) -> bool:
        return False


@final
@dataclass(frozen=True)
class HappeningLastFiredAt:
    happening: HappeningId
    at: WorldTick


@final
@dataclass(frozen=True)
class ReactionLastTruth:
    reaction: ReactionId
    truth: bool


@final
@dataclass(frozen=True)
class ScenarioProgressMemento:
    world_id: WorldId
    last_fired: frozenset[HappeningLastFiredAt]
    reaction_truths: frozenset[ReactionLastTruth]

    def __post_init__(self) -> None:
        happenings = [fired.happening for fired in self.last_fired]
        if len(set(happenings)) != len(happenings):
            raise RepeatedMementoKeyException(f"world {self.world_id} has a happening last fired at two ticks")
        reactions = [noted.reaction for noted in self.reaction_truths]
        if len(set(reactions)) != len(reactions):
            raise RepeatedMementoKeyException(f"world {self.world_id} has a reaction with two truths")


class ScenarioProgress:
    def __init__(
        self,
        world_id: WorldId,
        last_fired: Mapping[HappeningId, WorldTick],
        reaction_truths: Mapping[ReactionId, bool],
    ) -> None:
        self._world_id = world_id
        self._last_fired = dict(last_fired)
        self._reaction_truths = dict(reaction_truths)

    @classmethod
    def start(cls, world_id: WorldId) -> ScenarioProgress:
        return cls(world_id, {}, {})

    @classmethod
    def from_memento(cls, memento: ScenarioProgressMemento, design: WorldDesign) -> ScenarioProgress:
        return cls(
            memento.world_id,
            {fired.happening: fired.at for fired in memento.last_fired},
            {noted.reaction: noted.truth for noted in memento.reaction_truths},
        )

    @property
    def world_id(self) -> WorldId:
        return self._world_id

    def memento(self) -> ScenarioProgressMemento:
        return ScenarioProgressMemento(
            world_id=self._world_id,
            last_fired=frozenset(HappeningLastFiredAt(happening, at) for happening, at in self._last_fired.items()),
            reaction_truths=frozenset(
                ReactionLastTruth(reaction, truth) for reaction, truth in self._reaction_truths.items()
            ),
        )

    def note_happening_fired(self, happening: HappeningDeclaration, now: WorldTick) -> None:
        self._last_fired[happening.happening_id] = now

    def note_reaction_truth(self, reaction: ReactionDeclaration, truth: bool) -> None:
        self._reaction_truths[reaction.reaction_id] = truth

    def may_fire(self, happening: HappeningDeclaration, now: WorldTick) -> bool:
        last_fired = self._last_fired.get(happening.happening_id)
        if last_fired is None:
            return True
        return not happening.once and last_fired != now

    def reaction_changed(self, reaction: ReactionDeclaration, truth: bool) -> bool:
        noted = self._reaction_truths.get(reaction.reaction_id)
        return noted is not None and noted != truth

    def last_fired_at(self, happening: HappeningId) -> WorldTick | NeverFired:
        return self._last_fired.get(happening, NeverFired())
