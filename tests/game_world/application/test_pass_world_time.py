from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TypeVar

import pytest

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.pass_world_time import PassWorldTime, PassWorldTimeCommand
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.declaration.character import CharacterDeclaration
from ai_rpg_world.game_world.domain.declaration.object_and_item import ItemSpecDeclaration
from ai_rpg_world.game_world.domain.declaration.object_and_item.item_spec_declaration import Lasts
from ai_rpg_world.game_world.domain.declaration.spot import PassageDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    ChangesEvery,
    NoChange,
    NoWeather,
    WeatherDeclaration,
    WeatherState,
)
from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_transitions import WeatherTransitions
from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_type import WeatherType
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.exception.world_contents_exception import AggregateNotInWorldException
from ai_rpg_world.game_world.domain.objects_and_items import ItemGivenUpEvent, ItemRanOutEvent
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.objects_and_items.where_item_was import CarriedBy, LyingAt
from ai_rpg_world.game_world.domain.person.person_vitals_events import PersonDiedEvent
from ai_rpg_world.game_world.domain.rules.death_rule import DeathRule
from ai_rpg_world.game_world.domain.rules.world_rules import WorldRules
from ai_rpg_world.game_world.domain.value_object import (
    Damage,
    DescriptionText,
    HungerAmount,
    PersonId,
    SpotId,
    Ticks,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts import AtSpot, Location, OpenArea, PersonBody, Route, TravelBlockedEvent
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.domain.whereabouts._builders import CLOSED, door
from tests.game_world.support.world_design_for_tests import (
    character,
    compose_world,
    item_spec,
    nouns,
    passage,
    spot,
)
from tests.game_world.support.world_in_memory import FractionsInOrder
from tests.game_world.support.world_rules_for_tests import world_rules_for_tests

_WORLD = WorldId("world")
_HARU = PersonId("haru")
_PLAZA = SpotId("plaza")
_MINE = SpotId("mine")
_LAMP = replace(item_spec("lamp"), lasts=Lasts(Ticks(5), DescriptionText("ランプの油が切れた")))
_ROPE = item_spec("rope")
_Read = TypeVar("_Read")
_Event = TypeVar("_Event", bound=DomainEvent)


class _World:
    def __init__(
        self,
        *,
        characters: tuple[CharacterDeclaration, ...] = (),
        passages: tuple[PassageDeclaration, ...] = (),
        item_specs: tuple[ItemSpecDeclaration, ...] = (),
        rules: WorldRules | None = None,
        weather: WeatherDeclaration | NoWeather = NoWeather(),
        fractions: tuple[float, ...] = (),
    ) -> None:
        design: WorldDesign = compose_world(
            nouns(
                spots=(spot("plaza"), spot("mine")),
                passages=passages,
                item_specs=item_specs,
                characters=characters,
            ),
            world_rules=rules,
            weather=weather,
        )
        self.store = SqliteWorldStore.create(
            ":memory:",
            world_id=_WORLD,
            scenario="scenario",
            scenario_hash="hash",
            design=design,
            random=FractionsInOrder(fractions),
        )
        OpenWorld(self.store)(OpenWorldCommand(world_id=_WORLD, design=design))
        self.events: list[DomainEvent] = []
        distributor = CommittedEventsDistributor()
        distributor.register_receiver(self)
        self.scope = CommandScope(self.store, distributor)

    def receive(self, events: tuple[DomainEvent, ...]) -> None:
        self.events.extend(events)

    def pass_ticks(self, ticks: int) -> None:
        for _ in range(ticks):
            PassWorldTime(self.scope)(PassWorldTimeCommand())

    def read(self, reading: Callable[[WorldSession], _Read]) -> _Read:
        session = self.store.session()
        try:
            return reading(session)
        finally:
            session.roll_back()

    def carried_by_haru(self) -> tuple[ItemInstanceId, ...]:
        return self.read(lambda session: session.facts().inventory(_HARU).items())

    def events_of(self, kind: type[_Event]) -> list[_Event]:
        return [event for event in self.events if isinstance(event, kind)]


def _haru_carrying(*specs: ItemSpecDeclaration) -> CharacterDeclaration:
    return replace(character("haru", "plaza"), initial_items=tuple(spec.item_spec_id for spec in specs))


def _weather(changes: NoChange | ChangesEvery) -> WeatherDeclaration:
    return WeatherDeclaration(initial=WeatherType.CLEAR, changes=changes, announce_changes=False, obscuring=frozenset())


def _weather_now(world: _World) -> WeatherState:
    def current(session: WorldSession) -> WeatherState:
        weather = session.facts().weather()
        assert not isinstance(weather, NoWeather)
        return weather.current()

    return world.read(current)


def _haru_location(world: _World) -> Location:
    return world.read(lambda session: session.facts().whereabouts().location_of(PersonBody(_HARU)))


def _now(session: WorldSession) -> WorldTick:
    return session.facts().now()


class TestPassWorldTimeClock:
    """PassWorldTime が、1 回で世界の時計を 1 tick 進めることを保証する。"""

    def test_one_pass_advances_the_clock_by_one_tick(self) -> None:
        """時刻 0 の世界で 1 回呼ぶと、時刻は 1 になる。"""
        world = _World()

        world.pass_ticks(1)

        assert world.read(_now) == WorldTick(1)


class TestPassWorldTimeTravels:
    """PassWorldTime が、移動中の人を Whereabouts.advance_travels のとおりに進めることを保証する。"""

    def test_traveller_arrives_after_the_ticks_of_the_passage(self) -> None:
        """広場から坑道まで 2 tick かかる通路を歩き出した人は、2 tick 進めると坑道に着く。"""
        road = passage("road", ("plaza", "mine"), travel_ticks=2)
        world = _World(characters=(character("haru", "plaza"),), passages=(road,))
        world.scope.run(
            lambda session: session.aggregates().whereabouts().start_travel(PersonBody(_HARU), Route(_PLAZA, (road,)))
        )

        world.pass_ticks(2)

        assert _haru_location(world) == AtSpot(_MINE, OpenArea())

    def test_traveller_on_a_closed_passage_is_stopped_where_they_departed(self) -> None:
        """歩いている途中で通路が閉じると、時間を進めたときに出発した場所へ戻され、TravelBlockedEvent が出る。"""
        gate = door("gate", "plaza", "mine", initial=CLOSED, ticks=3)
        world = _World(characters=(character("haru", "plaza"),), passages=(gate,))
        world.scope.run(
            lambda session: session.aggregates().whereabouts().start_travel(PersonBody(_HARU), Route(_PLAZA, (gate,)))
        )

        world.pass_ticks(1)

        assert _haru_location(world) == AtSpot(_PLAZA, OpenArea())
        assert len(world.events_of(TravelBlockedEvent)) == 1


class TestPassWorldTimeVitals:
    """PassWorldTime が、全員の体の時間を、時計が進んだあとの時刻で進めることを保証する。"""

    def test_starving_person_dies_once_the_grace_after_falling_has_passed(self) -> None:
        """空腹の限界 1 で飢えると倒れる世界で、倒れてから 1 tick の猶予を過ぎる 2 tick 目に死に、PersonDiedEvent が出る。"""
        base = world_rules_for_tests()
        rules = replace(
            base,
            hunger=replace(
                base.hunger, per_tick=HungerAmount(1), limit=HungerAmount(1), starvation_damage=Damage(9999)
            ),
            death=DeathRule(grace=Ticks(1)),
        )
        world = _World(characters=(character("haru", "plaza"),), rules=rules)

        world.pass_ticks(2)

        died = world.events_of(PersonDiedEvent)
        assert [(event.person, event.died_at) for event in died] == [(_HARU, WorldTick(2))]


class TestPassWorldTimeItems:
    """PassWorldTime が、持つ時間が過ぎた品物を、持ち主の荷か置かれた地面から外して世界から出すことを保証する。"""

    def test_carried_item_past_its_time_leaves_the_pack_and_runs_out(self) -> None:
        """油が 5 tick 持つランプを持った人がいて、5 tick 進めると、ランプは荷から外れ、ItemRanOutEvent が持ち主の名で出る。"""
        world = _World(characters=(_haru_carrying(_LAMP),), item_specs=(_LAMP,))
        (lamp,) = world.carried_by_haru()

        world.pass_ticks(5)

        assert world.carried_by_haru() == ()
        ran_out = world.events_of(ItemRanOutEvent)
        assert [(event.item, event.where, event.at) for event in ran_out] == [(lamp, CarriedBy(_HARU), WorldTick(5))]

    def test_held_item_past_its_time_leaves_the_hands(self) -> None:
        """手に持ったランプも、5 tick 進めると手から外れ、ItemGivenUpEvent が was_held=True で出る。"""
        held_lamp = replace(_haru_carrying(_LAMP), initial_held=(_LAMP.item_spec_id,))
        world = _World(characters=(held_lamp,), item_specs=(_LAMP,))
        (lamp,) = world.carried_by_haru()

        world.pass_ticks(5)

        assert world.carried_by_haru() == ()
        given_up = world.events_of(ItemGivenUpEvent)
        assert [(event.item, event.was_held) for event in given_up] == [(lamp, True)]

    def test_item_that_ran_out_is_gone_from_the_world(self) -> None:
        """切れたランプは世界から出て、次の範囲では引けない (AggregateNotInWorldException)。"""
        world = _World(characters=(_haru_carrying(_LAMP),), item_specs=(_LAMP,))
        (lamp,) = world.carried_by_haru()

        world.pass_ticks(5)

        with pytest.raises(AggregateNotInWorldException):
            world.read(lambda session: session.facts().item(lamp))

    def test_item_on_the_ground_past_its_time_leaves_the_ground(self) -> None:
        """地面に置いたランプも、世界に出てから 5 tick 進めると地面から外れ、ItemRanOutEvent が場所の名で出る。"""
        world = _World(characters=(_haru_carrying(_LAMP),), item_specs=(_LAMP,))
        (lamp,) = world.carried_by_haru()

        def drop(session: WorldSession) -> None:
            session.aggregates().inventory(_HARU).give_up(lamp)
            session.aggregates().ground_items(_PLAZA).place(lamp)

        world.scope.run(drop)

        world.pass_ticks(5)

        assert world.read(lambda session: session.facts().ground_items(_PLAZA).items()) == ()
        ran_out = world.events_of(ItemRanOutEvent)
        assert [(event.item, event.where) for event in ran_out] == [(lamp, LyingAt(_PLAZA))]

    def test_item_with_time_left_stays_where_it_is(self) -> None:
        """5 tick 持つランプは、4 tick 進めただけでは荷に残り、ItemRanOutEvent も出ない。"""
        world = _World(characters=(_haru_carrying(_LAMP),), item_specs=(_LAMP,))
        (lamp,) = world.carried_by_haru()

        world.pass_ticks(4)

        assert world.carried_by_haru() == (lamp,)
        assert world.events_of(ItemRanOutEvent) == []

    def test_item_that_lasts_indefinitely_stays(self) -> None:
        """持つ時間の無い縄は、ランプが切れる tick を過ぎても荷に残る。"""
        world = _World(characters=(_haru_carrying(_ROPE, _LAMP),), item_specs=(_ROPE, _LAMP))
        rope, _lamp = world.carried_by_haru()

        world.pass_ticks(6)

        assert world.carried_by_haru() == (rope,)

    def test_item_time_is_counted_at_the_tick_after_the_clock_advanced(self) -> None:
        """1 tick 持つ品物は、1 回目で切れる。時計を進める前の時刻で数えると、1 回目では切れない。"""
        candle = replace(item_spec("candle"), lasts=Lasts(Ticks(1), DescriptionText("蝋燭が燃え尽きた")))
        world = _World(characters=(_haru_carrying(candle),), item_specs=(candle,))

        world.pass_ticks(1)

        assert world.carried_by_haru() == ()


class TestPassWorldTimeWeather:
    """PassWorldTime が、天候を宣言の移り変わりに従って変えることを保証する。

    ChangesEvery(ticks=N) の世界では、時計が進んだあとの時刻が N の倍数 (tick 0 から数えて N, 2N, ...) のときだけ
    facts.random() から 1 回引いて次の天候を選ぶ。NoChange の世界と、天候を宣言しない世界では引かない。
    """

    def test_world_without_weather_can_pass_time(self) -> None:
        """天候を宣言しない世界でも、時間を進められる。"""
        world = _World(weather=NoWeather())

        world.pass_ticks(3)

        assert world.read(_now) == WorldTick(3)

    def test_weather_that_never_changes_draws_nothing(self) -> None:
        """NoChange の天候は、時間を進めても乱数を引かず、初めの晴れのまま。"""
        world = _World(weather=_weather(NoChange()), fractions=())

        world.pass_ticks(4)

        assert _weather_now(world) == WeatherState(WeatherType.CLEAR)

    def test_weather_changes_only_at_multiples_of_its_ticks(self) -> None:
        """3 tick ごとに変わる天候は、1, 2 tick 目には引かず、3 tick 目に 1 回引いた値 (0.8 は晴れの次の曇り) で変わる。"""
        world = _World(weather=_weather(ChangesEvery(Ticks(3), WeatherTransitions.default())), fractions=(0.8,))

        world.pass_ticks(2)
        before = _weather_now(world)
        world.pass_ticks(1)

        assert before == WeatherState(WeatherType.CLEAR)
        assert _weather_now(world) == WeatherState(WeatherType.CLOUDY)
