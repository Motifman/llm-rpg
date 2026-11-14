from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.eventing import AggregateRoot, DomainEvent, new_event_stamp
from ai_rpg_world.game_world.domain.action.refusal_code import NoRefusal, RefusalCode
from ai_rpg_world.game_world.domain.exception.game_world_exception import require_distinct_memento_keys
from ai_rpg_world.game_world.domain.value_object import PersonId, Ticks, WorldId, WorldTick
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId
from ai_rpg_world.game_world.domain.value_object.reaction_id import ReactionId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.verb.happening_declaration import HappeningDeclaration
    from ai_rpg_world.game_world.domain.declaration.verb.reaction_declaration import ReactionDeclaration


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
class HappeningFiredEvent(DomainEvent):
    world_id: WorldId
    happening_id: HappeningId
    at: WorldTick
    audience: frozenset[PersonId]
    refusal: RefusalCode | NoRefusal


@final
@dataclass(frozen=True)
class ReactionFiredEvent(DomainEvent):
    world_id: WorldId
    reaction_id: ReactionId
    became: bool
    at: WorldTick
    refusal: RefusalCode | NoRefusal


ScenarioProgressEvent = HappeningFiredEvent | ReactionFiredEvent


@final
@dataclass(frozen=True)
class ScenarioProgressMemento:
    world_id: WorldId
    last_fired: frozenset[HappeningLastFiredAt]
    reaction_truths: frozenset[ReactionLastTruth]

    def __post_init__(self) -> None:
        require_distinct_memento_keys(
            [fired.happening for fired in self.last_fired],
            f"world {self.world_id.value} has a happening last fired at two ticks",
        )
        require_distinct_memento_keys(
            [noted.reaction for noted in self.reaction_truths],
            f"world {self.world_id.value} has a reaction with two truths",
        )


class ScenarioProgress(AggregateRoot[ScenarioProgressEvent]):
    def __init__(
        self,
        world_id: WorldId,
        last_fired: Mapping[HappeningId, WorldTick],
        reaction_truths: Mapping[ReactionId, bool],
    ) -> None:
        super().__init__()
        self._world_id = world_id
        self._last_fired = dict(last_fired)
        self._reaction_truths = dict(reaction_truths)

    @classmethod
    def start(cls, world_id: WorldId) -> ScenarioProgress:
        return cls(world_id, {}, {})

    @classmethod
    def from_memento(cls, memento: ScenarioProgressMemento) -> ScenarioProgress:
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

    def note_happening_fired(
        self,
        happening: HappeningDeclaration,
        now: WorldTick,
        audience: frozenset[PersonId],
        refusal: RefusalCode | NoRefusal,
    ) -> None:
        self._last_fired[happening.happening_id] = now
        # 断られた発火は何も変えていないので、知らせると起きていないことを伝えてしまう
        notified = audience if isinstance(refusal, NoRefusal) else frozenset()
        self.add_event(
            HappeningFiredEvent(
                **new_event_stamp(),
                world_id=self._world_id,
                happening_id=happening.happening_id,
                at=now,
                audience=notified,
                refusal=refusal,
            )
        )

    def note_reaction_fired(
        self, reaction: ReactionDeclaration, truth: bool, now: WorldTick, refusal: RefusalCode | NoRefusal
    ) -> None:
        self._reaction_truths[reaction.reaction_id] = truth
        self.add_event(
            ReactionFiredEvent(
                **new_event_stamp(),
                world_id=self._world_id,
                reaction_id=reaction.reaction_id,
                became=truth,
                at=now,
                refusal=refusal,
            )
        )

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
