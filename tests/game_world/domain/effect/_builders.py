from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.character.character_declaration import CharacterDeclaration
from ai_rpg_world.game_world.domain.declaration.object_and_item import ItemSpecDeclaration, NotALightSource
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
    )


def vitals(person: PersonId, hp: int = 10, maximum: int = 10) -> PersonVitals:
    return PersonVitals.start(person, HitPoints(current=hp, maximum=maximum))


def inventory(person: PersonId, capacity: int = 10) -> PersonInventory:
    return PersonInventory(person, Capacity(capacity))
