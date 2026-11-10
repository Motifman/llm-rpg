from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import final

from ai_rpg_world.game_world.domain.action.trigger import Trigger
from ai_rpg_world.game_world.domain.condition.condition import FailureReason, HiddenFailure
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.declaration.character.character_declaration import (
    CharacterDeclaration,
    UsesWorldDefault,
)
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ItemSpecDeclaration,
    LastsIndefinitely,
    NotALightSource,
)
from ai_rpg_world.game_world.domain.objects_and_items import PersonInventory
from ai_rpg_world.game_world.domain.person import PersonVitals
from ai_rpg_world.game_world.domain.value_object import (
    Capacity,
    DescriptionText,
    DisplayName,
    HitPoints,
    ItemSpecId,
    PersonId,
    SpotId,
    WorldId,
)
from ai_rpg_world.game_world.domain.value_object.hands_needed import HandsNeeded

WORLD = WorldId("effect_world")
ALICE = PersonId("alice")
BOB = PersonId("bob")
CAROL = PersonId("carol")


def item_spec(name: str) -> ItemSpecDeclaration:
    return ItemSpecDeclaration(
        item_spec_id=ItemSpecId(name),
        name=DisplayName(name),
        description=DescriptionText(f"{name} の説明"),
        state_keys=(),
        lights_up=NotALightSource(),
        hands_needed=HandsNeeded(1),
        lasts=LastsIndefinitely(),
    )


def character(person: PersonId) -> CharacterDeclaration:
    return CharacterDeclaration(
        person_id=person,
        appearance=DescriptionText(f"{person.value} の見た目"),
        spawn_spot=SpotId("plaza"),
        initial_items=(),
        initial_held=(),
        initial_groups=(),
        knows_at_start=(),
        max_hp=UsesWorldDefault(),
        pack_capacity=UsesWorldDefault(),
    )


def vitals(person: PersonId, hp: int = 10, maximum: int = 10) -> PersonVitals:
    return PersonVitals.start(person, HitPoints(current=hp, maximum=maximum))


def inventory(person: PersonId, capacity: int = 10) -> PersonInventory:
    return PersonInventory.start(person, Capacity(capacity))


@final
@dataclass(frozen=True)
class EachPersonIsOneOf:
    people: frozenset[PersonId]

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return trigger.person_as(SubjectKind.EACH_PERSON) in self.people

    def requirements(self) -> Requirements:
        return replace(Requirements.nothing(), subjects=frozenset({SubjectKind.EACH_PERSON}))

    def failure_reason(self, facts: WorldFacts, trigger: Trigger) -> FailureReason | HiddenFailure | None:
        return None

    def explains_failure(self) -> bool:
        return False


@final
@dataclass(frozen=True)
class FixedTruth:
    truth: bool
    needs: Requirements = field(default_factory=Requirements.nothing)

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return self.truth

    def requirements(self) -> Requirements:
        return self.needs

    def failure_reason(self, facts: WorldFacts, trigger: Trigger) -> FailureReason | HiddenFailure | None:
        return None

    def explains_failure(self) -> bool:
        return False
