from __future__ import annotations

from ai_rpg_world.game_world.application.world_store import AggregateWithMemento, WorldSession
from ai_rpg_world.game_world.domain.condition.random_source import RandomSource
from ai_rpg_world.game_world.domain.declaration.character import CharacterDeclaration
from ai_rpg_world.game_world.domain.declaration.character.character_declaration import UsesWorldDefault
from ai_rpg_world.game_world.domain.declaration.declared_nouns import DeclaredNouns
from ai_rpg_world.game_world.domain.declaration.object_and_item import ItemSpecDeclaration, ObjectDeclaration
from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration, WorldStageDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.spot import PassageDeclaration, SpotDeclaration, SpotSectionDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather import DayNightDeclaration, NoDayNight, NoWeather
from ai_rpg_world.game_world.domain.declaration.time_and_weather.changes_every import NoChange
from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_declaration import WeatherDeclaration
from ai_rpg_world.game_world.domain.declaration.verb.ending_declaration import EndingDeclaration
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.objects_and_items import (
    GroundItems,
    Item,
    ObjectState,
    PersonInventory,
    SpotSearchProgress,
)
from ai_rpg_world.game_world.domain.people import PeopleRegister
from ai_rpg_world.game_world.domain.person import GroupMembership, PersonOutcomes, PersonVitals
from ai_rpg_world.game_world.domain.rules.action_kind import ActionKind
from ai_rpg_world.game_world.domain.rules.world_rules import WorldRules
from ai_rpg_world.game_world.domain.value_object import DescriptionText, PersonId, WorldId
from ai_rpg_world.game_world.domain.whereabouts import PassageStates, SpotAtmospheres, Whereabouts
from ai_rpg_world.game_world.domain.world_progress import GroupDecision, Weather, WorldClock, WorldEnding, WorldStage
from ai_rpg_world.game_world.domain.world_records import LatestActions, MissedNotices, ScenarioProgress, WorldFlags
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.support.verb_parts_for_tests import AlwaysHolds
from tests.game_world.support.world_design_for_tests import (
    built_in_action_perceptions,
    introduction,
    refusal_texts,
    spot,
)
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests


class FractionsInOrder(RandomSource):
    def __init__(self, fractions: tuple[float, ...]) -> None:
        for fraction in fractions:
            if not 0.0 <= fraction < 1.0:
                raise ValueError(f"a fraction must be in [0, 1), got {fraction}")
        self._left = list(fractions)

    def next_fraction(self) -> float:
        if not self._left:
            raise LookupError("every fraction the test gave has been drawn")
        return self._left.pop(0)


def world_in_memory(
    *,
    world: WorldId,
    rules: WorldRules | None = None,
    people: tuple[PersonId, ...] = (),
    characters: tuple[CharacterDeclaration, ...] = (),
    spots: tuple[SpotDeclaration, ...] = (),
    passages: tuple[PassageDeclaration, ...] = (),
    objects: tuple[ObjectDeclaration, ...] = (),
    item_specs: tuple[ItemSpecDeclaration, ...] = (),
    group_decisions: tuple[GroupDecisionDeclaration, ...] = (),
    sections: tuple[SpotSectionDeclaration, ...] = (),
    vitals: tuple[PersonVitals, ...] = (),
    inventories: tuple[PersonInventory, ...] = (),
    items: tuple[Item, ...] = (),
    object_states: tuple[ObjectState, ...] = (),
    world_stage: WorldStage | NoWorldStages = NoWorldStages(),
    stage_declarations: tuple[WorldStageDeclaration, ...] = (),
    day_night: DayNightDeclaration | NoDayNight = NoDayNight(),
    weather: Weather | NoWeather = NoWeather(),
    fractions: tuple[float, ...] = (),
) -> WorldSession:
    spots, characters = _with_everyone_declared(people, characters, spots)
    nouns = DeclaredNouns(
        flags=(),
        spots=spots,
        passages=passages,
        objects=objects,
        item_specs=item_specs,
        groupings=(),
        groups=(),
        characters=characters,
        world_stages=stage_declarations,
        group_decisions=group_decisions,
        sections=sections,
        outcomes=(),
    )
    store = SqliteWorldStore.create(
        ":memory:",
        world_id=world,
        scenario="world_in_memory",
        scenario_hash="world_in_memory",
        design=_design(nouns, rules, day_night, weather, world_stage, stage_declarations),
        random=FractionsInOrder(fractions),
    )
    everyone = tuple(character.person_id for character in characters)
    store.start_world(
        _aggregates_at_start(world, nouns, everyone, vitals, inventories, items, object_states, world_stage, weather)
    )
    return store.session()


def _with_everyone_declared(
    people: tuple[PersonId, ...], characters: tuple[CharacterDeclaration, ...], spots: tuple[SpotDeclaration, ...]
) -> tuple[tuple[SpotDeclaration, ...], tuple[CharacterDeclaration, ...]]:
    declared = {character.person_id: character for character in characters}
    if any(person not in declared for person in people) and not spots:
        spots = (spot("somewhere"),)
    in_given_order = tuple(declared.get(person) or _character_at(person, spots[0]) for person in people)
    return spots, in_given_order + tuple(character for character in characters if character.person_id not in people)


def _character_at(person: PersonId, spawn: SpotDeclaration) -> CharacterDeclaration:
    return CharacterDeclaration(
        person_id=person,
        appearance=DescriptionText(f"{person.value} の見た目"),
        spawn_spot=spawn.spot_id,
        initial_items=(),
        initial_held=(),
        initial_groups=(),
        knows_at_start=(),
        max_hp=UsesWorldDefault(),
        pack_capacity=UsesWorldDefault(),
    )


def _design(
    nouns: DeclaredNouns,
    rules: WorldRules | None,
    day_night: DayNightDeclaration | NoDayNight,
    weather: Weather | NoWeather,
    world_stage: WorldStage | NoWorldStages,
    stage_declarations: tuple[WorldStageDeclaration, ...],
) -> WorldDesign:
    return WorldDesign(
        nouns=nouns,
        object_interactions=(),
        item_interactions=(),
        item_uses=(),
        section_accesses=(),
        passage_traversals=(),
        world_stage_effects=(),
        object_looks=(),
        group_decision_rules=(),
        happenings=(),
        reactions=(),
        discoverables=(),
        joint_actions=(),
        person_interactions=(),
        ending=EndingDeclaration(ends_when=AlwaysHolds()),
        world_rules=rules if rules is not None else world_rules_for_tests(),
        refusal_texts=refusal_texts(),
        built_in_action_perceptions=built_in_action_perceptions(without=(ActionKind.TEND,)),
        weather=(
            NoWeather()
            if isinstance(weather, NoWeather)
            else WeatherDeclaration(
                initial=weather.current().type, changes=NoChange(), announce_changes=False, obscuring=frozenset()
            )
        ),
        day_night=day_night,
        initial_stage=(
            NoWorldStages()
            if isinstance(world_stage, NoWorldStages)
            else next(stage for stage in stage_declarations if stage.stage_id == world_stage.current())
        ),
        introduction=introduction(),
        warnings=(),
    )


def _aggregates_at_start(
    world: WorldId,
    nouns: DeclaredNouns,
    everyone: tuple[PersonId, ...],
    vitals: tuple[PersonVitals, ...],
    inventories: tuple[PersonInventory, ...],
    items: tuple[Item, ...],
    object_states: tuple[ObjectState, ...],
    world_stage: WorldStage | NoWorldStages,
    weather: Weather | NoWeather,
) -> tuple[AggregateWithMemento, ...]:
    spots = nouns.all_spots()
    return (
        WorldClock.start(world),
        WorldEnding.start(world),
        ScenarioProgress.start(world),
        LatestActions.start(world),
        PeopleRegister.from_characters(world, nouns.all_characters()),
        WorldFlags.start(world),
        Whereabouts.start(world),
        PassageStates.start(world, nouns.all_passages()),
        SpotAtmospheres.start(world, spots),
        PersonOutcomes.start(world, everyone),
        GroupMembership.start(world, {}),
        *(() if isinstance(world_stage, NoWorldStages) else (world_stage,)),
        *(() if isinstance(weather, NoWeather) else (weather,)),
        *vitals,
        *inventories,
        *items,
        *object_states,
        *(MissedNotices.start(person) for person in everyone),
        *(GroundItems.start(declared.spot_id) for declared in spots),
        *(SpotSearchProgress.start(declared.spot_id) for declared in spots),
        *(GroupDecision.not_started(decision) for decision in nouns.all_group_decisions()),
    )
