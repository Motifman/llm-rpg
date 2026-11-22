from __future__ import annotations

from dataclasses import replace

from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.declaration.no_announcement import NoAnnouncement
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ChoiceName,
    ChoiceStateKind,
    ChoiceValue,
    ItemSpecDeclaration,
    ItemStateKeyDeclaration,
    LastsIndefinitely,
    LitWhen,
)
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    DayNightDeclaration,
    DayPhaseDeclaration,
    NoWeather,
    TimeOfDay,
    WeatherDeclaration,
    WeatherState,
)
from ai_rpg_world.game_world.domain.declaration.time_and_weather.changes_every import NoChange
from ai_rpg_world.game_world.domain.declaration.time_and_weather.day_phase_name import DayPhaseName
from ai_rpg_world.game_world.domain.declaration.time_and_weather.everyone_awake import EveryoneAwake
from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_type import WeatherType
from ai_rpg_world.game_world.domain.lighting import Lighting, LightingConditions
from ai_rpg_world.game_world.domain.objects_and_items import Item, ItemInstanceId, PersonInventory
from ai_rpg_world.game_world.domain.people import NoVisibleName
from ai_rpg_world.game_world.domain.perception import DepartedPerceiver, LivingPerceiver
from ai_rpg_world.game_world.domain.person import Alive, PersonVitals
from ai_rpg_world.game_world.domain.person.life_state import WorldHappening
from ai_rpg_world.game_world.domain.sound import Loudness, NotReached, SoundLevel
from ai_rpg_world.game_world.domain.value_object import (
    Capacity,
    Damage,
    DescriptionText,
    DisplayName,
    HitPoints,
    ItemSpecId,
    PersonId,
    StateKeyId,
    Ticks,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.value_object.hands_needed import HandsNeeded
from ai_rpg_world.game_world.domain.whereabouts import AtSpot, DepartedPerson, OpenArea, PersonBody
from ai_rpg_world.game_world.domain.world_progress import Weather
from tests.game_world.domain.whereabouts._builders import door, path
from tests.game_world.support.world_design_for_tests import character, spot
from tests.game_world.support.world_in_memory import world_in_memory
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

_WORLD = WorldId("perception_world")
_ALICE = PersonId("alice")
_SQUARE = spot("square")
_CELLAR = spot("cellar")

_WICK = ItemStateKeyDeclaration(
    item_spec_id=ItemSpecId("lantern"),
    key=StateKeyId("wick"),
    kind=ChoiceStateKind(choices=(ChoiceName("unlit"), ChoiceName("lit"))),
    initial=ChoiceValue(ChoiceName("lit")),
)
_LIT_LANTERN = ItemSpecDeclaration(
    item_spec_id=ItemSpecId("lantern"),
    name=DisplayName("カンテラ"),
    description=DescriptionText("灯った手提げの明かり"),
    state_keys=(_WICK,),
    lights_up=LitWhen(_WICK.key, ChoiceValue(ChoiceName("lit"))),
    hands_needed=HandsNeeded(1),
    lasts=LastsIndefinitely(),
)

_NIGHT_FROM_THE_START = DayNightDeclaration(
    ticks_per_day=Ticks(4),
    starts_at=TimeOfDay(0),
    phases=(
        DayPhaseDeclaration(
            name=DayPhaseName("夜"),
            display_name=DisplayName("夜"),
            begins_at=TimeOfDay(0),
            dark=True,
            announcement=NoAnnouncement(),
            audience=EveryoneAwake(),
        ),
    ),
)


def _lit_as(lighting: Lighting, *, outdoor: bool = False) -> SpotDeclaration:
    return replace(_SQUARE, atmosphere=replace(_SQUARE.atmosphere, lighting=lighting, outdoor=outdoor))


def _vitals(person: PersonId) -> PersonVitals:
    return PersonVitals.start(person, HitPoints(current=10, maximum=10))


def _placed(world: WorldSession, person: PersonId, at: SpotDeclaration) -> WorldSession:
    world.aggregates().whereabouts().place(PersonBody(person), at)
    return world


def _with_lantern(where_kept: str) -> WorldSession:
    lantern = Item.come_into_world(ItemInstanceId("lantern-1"), _LIT_LANTERN, WorldTick(0))
    world = world_in_memory(
        world=_WORLD,
        people=(_ALICE,),
        spots=(_lit_as(Lighting.PITCH_DARK), _CELLAR),
        item_specs=(_LIT_LANTERN,),
        vitals=(_vitals(_ALICE),),
        inventories=(PersonInventory.start(_ALICE, Capacity(5)),),
        items=(lantern,),
    )
    _placed(world, _ALICE, _lit_as(Lighting.PITCH_DARK))
    inventory = world.aggregates().inventory(_ALICE)
    inventory.receive(lantern.item_id, lantern.spec_id)
    if where_kept == "hand":
        inventory.hold(lantern.item_id, HandsNeeded(1))
    return world


def _conditions(
    declared: Lighting,
    *,
    outdoor: bool = False,
    dark_time_of_day: bool = False,
    weather_obscures: bool = False,
    light_source_present: bool = False,
) -> LightingConditions:
    return LightingConditions(
        declared=declared,
        outdoor=outdoor,
        dark_time_of_day=dark_time_of_day,
        weather_obscures=weather_obscures,
        light_source_present=light_source_present,
    )


class TestLightingConditionsAt:
    """LightingConditions.at が、場所の今の雰囲気・時間帯・天候・その場所の人の手の光源から、明るさの材料を集めることを保証する。"""

    def test_atmosphere_gives_declared_lighting_and_outdoor(self) -> None:
        """時間帯も天候も宣言しない世界の屋外の薄暗い場所は、薄暗い・屋外で、ほかの材料はどれも偽になる。"""
        dusky_outdoors = _lit_as(Lighting.DUSKY, outdoor=True)
        world = world_in_memory(world=_WORLD, spots=(dusky_outdoors,))

        conditions = LightingConditions.at(dusky_outdoors, world.facts())

        assert conditions == _conditions(Lighting.DUSKY, outdoor=True)

    def test_dark_time_of_day_is_read_from_the_current_day_phase(self) -> None:
        """いまの時間帯が暗いと宣言されていれば、dark_time_of_day は真になる。"""
        world = world_in_memory(world=_WORLD, spots=(_SQUARE,), day_night=_NIGHT_FROM_THE_START)

        conditions = LightingConditions.at(_SQUARE, world.facts())

        assert conditions == _conditions(Lighting.BRIGHT, dark_time_of_day=True)

    def test_obscuring_weather_is_read_from_the_current_weather(self) -> None:
        """霧を見通しの悪い天候と宣言した世界でいまが霧なら、weather_obscures は真になる。"""
        world = world_in_memory(
            world=_WORLD,
            spots=(_SQUARE,),
            weather=Weather(_WORLD, WeatherState(WeatherType.FOG)),
            obscuring=frozenset({WeatherType.FOG}),
        )

        conditions = LightingConditions.at(_SQUARE, world.facts())

        assert conditions == _conditions(Lighting.BRIGHT, weather_obscures=True)

    def test_weather_not_declared_obscuring_does_not_obscure(self) -> None:
        """いまが霧でも、霧を見通しの悪い天候と宣言していなければ、weather_obscures は偽になる。"""
        world = world_in_memory(world=_WORLD, spots=(_SQUARE,), weather=Weather(_WORLD, WeatherState(WeatherType.FOG)))

        conditions = LightingConditions.at(_SQUARE, world.facts())

        assert conditions == _conditions(Lighting.BRIGHT)

    def test_lit_light_source_in_hand_is_present(self) -> None:
        """その場所にいる人が灯ったカンテラを手に持っていれば、light_source_present は真になる。"""
        world = _with_lantern("hand")

        conditions = LightingConditions.at(_lit_as(Lighting.PITCH_DARK), world.facts())

        assert conditions == _conditions(Lighting.PITCH_DARK, light_source_present=True)

    def test_lit_light_source_in_the_pack_is_not_present(self) -> None:
        """灯ったカンテラでも、荷の中にあれば light_source_present は偽になる。"""
        world = _with_lantern("pack")

        conditions = LightingConditions.at(_lit_as(Lighting.PITCH_DARK), world.facts())

        assert conditions == _conditions(Lighting.PITCH_DARK)

    def test_departed_person_does_not_bring_the_lantern_left_in_the_body_hand(self) -> None:
        """去った人が広場にいて、その体が灯ったカンテラを手に持ったまま地下室にあるとき、広場の light_source_present は偽になる。"""
        world = _with_lantern("hand")
        world.aggregates().whereabouts().remove(PersonBody(_ALICE))
        world.aggregates().whereabouts().place(PersonBody(_ALICE), _CELLAR)
        world.aggregates().whereabouts().place(DepartedPerson(_ALICE), _lit_as(Lighting.PITCH_DARK))

        conditions = LightingConditions.at(_lit_as(Lighting.PITCH_DARK), world.facts())

        assert conditions == _conditions(Lighting.PITCH_DARK)
