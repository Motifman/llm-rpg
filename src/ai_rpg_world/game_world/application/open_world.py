from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.world_store import AggregateWithMemento, WorldStore
from ai_rpg_world.game_world.domain.declaration.initial_world import StartingPerson
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.objects_and_items import (
    GroundItems,
    Item,
    ItemSerialCounter,
    ObjectState,
    PersonInventory,
    SpotSearchProgress,
)
from ai_rpg_world.game_world.domain.people import PeopleRegister
from ai_rpg_world.game_world.domain.person import GroupMembership, PersonOutcomes, PersonVitals
from ai_rpg_world.game_world.domain.value_object import WorldId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts import PassageStates, PersonBody, SpotAtmospheres, Whereabouts
from ai_rpg_world.game_world.domain.world_progress import GroupDecision, Weather, WorldClock, WorldEnding, WorldStage
from ai_rpg_world.game_world.domain.world_records import LatestActions, MissedNotices, ScenarioProgress, WorldFlags


@final
@dataclass(frozen=True)
class OpenWorldCommand:
    world_id: WorldId
    design: WorldDesign


@final
class OpenWorld:
    def __init__(self, store: WorldStore) -> None:
        self._store = store

    def __call__(self, command: OpenWorldCommand) -> None:
        self._store.start_world(_aggregates_at_start(command.world_id, command.design))


def _aggregates_at_start(world: WorldId, design: WorldDesign) -> tuple[AggregateWithMemento, ...]:
    nouns = design.nouns
    initial = design.initial_world()
    clock = WorldClock.start(world)
    now = clock.now()
    serial_counter = ItemSerialCounter.start(world)
    whereabouts = Whereabouts.start(world)
    people: list[AggregateWithMemento] = []
    for person in initial.people:
        whereabouts.place(PersonBody(person.person), person.spawn_spot)
        inventory, items = _inventory_at_start(person, serial_counter, now)
        people += [PersonVitals.start(person.person, person.hp), inventory, *items, MissedNotices.start(person.person)]
    spots = nouns.all_spots()
    return (
        clock,
        WorldEnding.start(world),
        ScenarioProgress.start(world),
        LatestActions.start(world),
        PeopleRegister.from_characters(world, nouns.all_characters()),
        WorldFlags.start(world),
        whereabouts,
        PassageStates.start(world, nouns.all_passages()),
        SpotAtmospheres.start(world, spots),
        PersonOutcomes.start(world, tuple(person.person for person in initial.people)),
        GroupMembership.start(world, {person.person: person.groups for person in initial.people}),
        serial_counter,
        *Weather.at_start(world, design.weather),
        *WorldStage.at_start(world, initial.stage, now),
        *people,
        *(ObjectState.from_declaration(declared, now) for declared in nouns.all_objects()),
        *(GroundItems.start(declared.spot_id) for declared in spots),
        *(SpotSearchProgress.start(declared.spot_id) for declared in spots),
        *(GroupDecision.not_started(decision) for decision in nouns.all_group_decisions()),
    )


def _inventory_at_start(
    person: StartingPerson, serial_counter: ItemSerialCounter, now: WorldTick
) -> tuple[PersonInventory, tuple[Item, ...]]:
    inventory = PersonInventory.start(person.person, person.pack_capacity)
    items = tuple(serial_counter.make_numbered_item(spec, now) for spec in person.items)
    for item in items:
        inventory.receive(item.item_id, item.spec_id)
    for spec in person.held:
        inventory.hold_packed_at_start(spec.item_spec_id, spec.hands_needed)
    return inventory, items
