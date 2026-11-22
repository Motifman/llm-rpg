from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TypeVar

import pytest

from ai_rpg_world.eventing import DomainEvent
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.committed_events_distributor import CommittedEventsDistributor
from ai_rpg_world.game_world.application.deliver_perception import DeliverPerception, DeliverPerceptionCommand
from ai_rpg_world.game_world.application.observation_exit import ObservationExit
from ai_rpg_world.game_world.application.open_world import OpenWorld, OpenWorldCommand
from ai_rpg_world.game_world.application.pass_world_time import PassWorldTime, PassWorldTimeCommand
from ai_rpg_world.game_world.application.person.decide_death_outcome import DecideDeathOutcome
from ai_rpg_world.game_world.application.person.handlers.decide_death_outcome_handler import (
    DecideDeathOutcomeHandler,
)
from ai_rpg_world.game_world.application.person.handlers.place_departed_person_handler import (
    PlaceDepartedPersonHandler,
)
from ai_rpg_world.game_world.application.person.place_departed_person import PlaceDepartedPerson
from ai_rpg_world.game_world.application.stimulus_translator import StimulusTranslator
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.declaration.character import CharacterDeclaration
from ai_rpg_world.game_world.domain.declaration.no_announcement import NoAnnouncement
from ai_rpg_world.game_world.domain.declaration.object_and_item import ItemSpecDeclaration
from ai_rpg_world.game_world.domain.declaration.object_and_item.item_spec_declaration import Lasts
from ai_rpg_world.game_world.domain.declaration.progress import OutcomeDeclaration
from ai_rpg_world.game_world.domain.declaration.spot import PassageDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    ChangesEvery,
    DayNightDeclaration,
    DayPhaseDeclaration,
    DayPhaseName,
    NoChange,
    NoDayNight,
    NoWeather,
    TimeOfDay,
    WeatherDeclaration,
    WeatherState,
)
from ai_rpg_world.game_world.domain.declaration.time_and_weather.everyone_awake import EveryoneAwake
from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_transitions import WeatherTransitions
from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_type import WeatherType
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.exception.world_contents_exception import AggregateNotInWorldException
from ai_rpg_world.game_world.domain.objects_and_items import ItemGivenUpEvent, ItemRanOutEvent
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.objects_and_items.where_item_was import CarriedBy, LyingAt
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.perception.perception_cause import TimePassed
from ai_rpg_world.game_world.domain.person.life_state import Alive, Down, LifeState, WorldHappening
from ai_rpg_world.game_world.domain.person.person_outcomes import DeclaredOutcome
from ai_rpg_world.game_world.domain.person.person_vitals_events import (
    HungerLevelChangedEvent,
    PersonDamagedEvent,
    PersonDiedEvent,
)
from ai_rpg_world.game_world.domain.rules.death_rule import DeathRule
from ai_rpg_world.game_world.domain.rules.world_rules import WorldRules
from ai_rpg_world.game_world.domain.value_object import (
    Damage,
    DescriptionText,
    DisplayName,
    HungerAmount,
    OutcomeId,
    PersonId,
    SpotId,
    Ticks,
    WorldId,
    WorldTick,
)
from ai_rpg_world.game_world.domain.whereabouts import (
    AtSpot,
    DepartedPerson,
    Location,
    OccupantEnteredSpotEvent,
    OpenArea,
    PersonBody,
    Route,
    TravelBlockedEvent,
)
from ai_rpg_world.game_world.domain.world_progress.world_clock import TimeOfDayChangedEvent
from ai_rpg_world.game_world.infrastructure.world.sqlite_world_store import SqliteWorldStore
from tests.game_world.domain.whereabouts._builders import CLOSED, door
from tests.game_world.support.perception_reports import PerceptionReportsReceived
from tests.game_world.support.world_design_for_tests import (
    character,
    clock_wording,
    compose_world,
    half_hour_ticks_from_midnight,
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
_AKI = PersonId("aki")
_RESCUED = OutcomeDeclaration(
    outcome_id=OutcomeId("rescued"),
    name=DisplayName("救出"),
    announcement=TextWithUnassignedPeople("{each_person}は昇降機で外へ出た。"),
)
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
        day_night: DayNightDeclaration | NoDayNight = NoDayNight(),
        fractions: tuple[float, ...] = (),
    ) -> None:
        design: WorldDesign = compose_world(
            nouns(
                spots=(spot("plaza"), spot("mine")),
                passages=passages,
                item_specs=item_specs,
                characters=characters,
                outcomes=(_RESCUED,),
            ),
            world_rules=rules,
            weather=weather,
            day_night=day_night,
        )
        self.design = design
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
        self.distributor = CommittedEventsDistributor()
        self.distributor.register_receiver(self)
        self.scope = CommandScope(self.store, self.distributor)

    def wire_handlers_of_person_died(self) -> None:
        self.distributor.register_handler(PersonDiedEvent, DecideDeathOutcomeHandler(DecideDeathOutcome(self.scope)))
        self.distributor.register_handler(PersonDiedEvent, PlaceDepartedPersonHandler(PlaceDepartedPerson(self.scope)))

    def leave_by_rescue(self, person: PersonId) -> None:
        def leave(session: WorldSession) -> None:
            session.aggregates().outcomes().decide(person, DeclaredOutcome(_RESCUED), session.facts().now())
            session.aggregates().whereabouts().remove(PersonBody(person))

        self.scope.run(leave)

    def knock_down(self, person: PersonId) -> None:
        self.scope.run(
            lambda session: (
                session.aggregates().vitals(person).take_damage(Damage(9999), session.facts().now(), WorldHappening())
            )
        )

    def vitals_of(self, person: PersonId) -> tuple[LifeState, HungerAmount]:
        return self.read(
            lambda session: (session.facts().vitals(person).life_state(), session.facts().vitals(person).hunger())
        )

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

    def test_arrival_is_stamped_with_the_tick_after_the_clock_advanced(self) -> None:
        """1 tick の通路を歩き出した人が 1 回目で着くと、OccupantEnteredSpotEvent の at は時計を進めた後の 1 になる。"""
        road = passage("road", ("plaza", "mine"), travel_ticks=1)
        world = _World(characters=(character("haru", "plaza"),), passages=(road,))
        world.scope.run(
            lambda session: session.aggregates().whereabouts().start_travel(PersonBody(_HARU), Route(_PLAZA, (road,)))
        )

        world.pass_ticks(1)

        entered = world.events_of(OccupantEnteredSpotEvent)
        assert [(event.spot, event.at) for event in entered] == [(_MINE, WorldTick(1))]

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


def _starving_rules(departed_persons_act: bool = False) -> WorldRules:
    base = world_rules_for_tests()
    return replace(
        base,
        hunger=replace(base.hunger, per_tick=HungerAmount(1), limit=HungerAmount(1), starvation_damage=Damage(9999)),
        death=DeathRule(grace=Ticks(1)),
        departed_persons_act=departed_persons_act,
    )


def _aki_and_haru(*, rules: WorldRules) -> _World:
    return _World(characters=(character("aki", "mine"), character("haru", "plaza")), rules=rules)


class TestPassWorldTimeStopsTheBodyOfPersonWhoLeft:
    """PassWorldTime が、作者の結末が決まって世界から外れた人の体の時間を進めず、世界に残る人の体の時間だけを進めることを保証する。

    どの世界も、1 tick で空腹が限界 1 に達して飢えで倒れ、倒れてから 1 tick で死ぬ値にしてある。
    """

    def test_person_who_left_while_down_does_not_die(self) -> None:
        """気を失ったまま救出の結末で外れたアキは、倒れてから死ぬまでの猶予 1 tick を過ぎる 3 tick を進めても、倒れたままで PersonDiedEvent は出ない。"""
        world = _aki_and_haru(rules=_starving_rules())
        world.knock_down(_AKI)
        world.leave_by_rescue(_AKI)

        world.pass_ticks(3)

        assert isinstance(world.vitals_of(_AKI)[0], Down)
        assert [event.person for event in world.events_of(PersonDiedEvent)] == [_HARU]

    def test_person_who_left_awake_grows_no_hungrier(self) -> None:
        """起きたまま外れたアキは、3 tick 進めても空腹は 0 のままで、空腹の段階も変わらず、飢えの痛手も受けない。"""
        world = _aki_and_haru(rules=_starving_rules())
        world.leave_by_rescue(_AKI)

        world.pass_ticks(3)

        assert world.vitals_of(_AKI) == (Alive(), HungerAmount(0))
        assert [event.person for event in world.events_of(HungerLevelChangedEvent) if event.person == _AKI] == []
        assert [event.person for event in world.events_of(PersonDamagedEvent) if event.person == _AKI] == []

    def test_person_who_left_is_neither_given_death_nor_placed_as_departed(self) -> None:
        """去った人が動く世界で、死の反応 (DecideDeathOutcomeHandler・PlaceDepartedPersonHandler) を配線しても、気を失ったまま外れたアキについてはどちらも動かず、断られた反応も無く、アキの結末は救出のまま。"""
        world = _aki_and_haru(rules=_starving_rules(departed_persons_act=True))
        world.wire_handlers_of_person_died()
        world.knock_down(_AKI)
        world.leave_by_rescue(_AKI)

        world.pass_ticks(3)

        assert world.distributor.refused_handlers == {}
        assert world.read(lambda session: session.facts().outcomes().outcome_of(_AKI)) == DeclaredOutcome(_RESCUED)
        occupants = world.read(lambda session: session.facts().whereabouts().occupants_at(spot("mine")))
        assert DepartedPerson(_AKI) not in occupants and PersonBody(_AKI) not in occupants

    def test_person_still_in_the_world_keeps_starving_and_dies(self) -> None:
        """アキが外れても、広場に残るハルは 1 tick 目に飢えで倒れ、2 tick 目に死ぬ。"""
        world = _aki_and_haru(rules=_starving_rules())
        world.leave_by_rescue(_AKI)

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


class TestPassWorldTimeStopsTheItemsOfPersonWhoLeft:
    """PassWorldTime が、世界から外れた人の荷の品物の時間を進めず、世界に残る人の品物だけを切らすことを保証する。"""

    def test_lamp_carried_out_of_the_world_never_runs_out(self) -> None:
        """油が 5 tick もつランプを持ったまま救出の結末で外れたハルは、6 tick 進めてもランプを持ったままで、ItemRanOutEvent は出ない。"""
        world = _World(characters=(_haru_carrying(_LAMP),), item_specs=(_LAMP,))
        (lamp,) = world.carried_by_haru()
        world.leave_by_rescue(_HARU)

        world.pass_ticks(6)

        assert world.carried_by_haru() == (lamp,)
        assert world.events_of(ItemRanOutEvent) == []

    def test_lamp_of_person_still_in_the_world_runs_out(self) -> None:
        """ランプを持ったアキが外れても、同じランプを持って広場に残るハルのランプは 5 tick 目に切れる。"""
        aki = replace(character("aki", "mine"), initial_items=(_LAMP.item_spec_id,))
        world = _World(characters=(aki, _haru_carrying(_LAMP)), item_specs=(_LAMP,))
        world.leave_by_rescue(_AKI)

        world.pass_ticks(5)

        ran_out = world.events_of(ItemRanOutEvent)
        assert [(event.where, event.at) for event in ran_out] == [(CarriedBy(_HARU), WorldTick(5))]


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


_DAWN = TextWithUnassignedPeople("空が白み、朝になった。")
_DAWN_AT_TICK_1 = DayNightDeclaration(
    ticks_per_day=Ticks(4),
    starts_at=TimeOfDay(0),
    phases=(
        DayPhaseDeclaration(
            name=DayPhaseName("night"),
            begins_at=TimeOfDay(0),
            dark=True,
            announcement=NoAnnouncement(),
            audience=EveryoneAwake(),
        ),
        DayPhaseDeclaration(
            name=DayPhaseName("morning"),
            begins_at=TimeOfDay(1),
            dark=False,
            announcement=_DAWN,
            audience=EveryoneAwake(),
        ),
    ),
)
_AKI = PersonId("aki")


class TestPassWorldTimeDayPhase:
    """PassWorldTime が、時間帯の変わり目に、その時点で起きている相手を選んで TimeOfDayChangedEvent に載せることを保証する。"""

    def _dawn_with_aki_fainted(self) -> _World:
        world = _World(characters=(character("haru", "plaza"), character("aki", "plaza")), day_night=_DAWN_AT_TICK_1)
        world.scope.run(
            lambda session: session.aggregates().vitals(_AKI).take_damage(Damage(999), WorldTick(0), WorldHappening())
        )
        world.pass_ticks(1)
        return world

    def test_fainted_person_is_left_out_of_the_morning_audience(self) -> None:
        """朝に入ると、広場で起きているハルだけが TimeOfDayChangedEvent の相手に載り、同じ広場で気を失っているアキは載らない。"""
        world = self._dawn_with_aki_fainted()

        [entered] = world.events_of(TimeOfDayChangedEvent)
        assert (entered.after, entered.audience) == (DayPhaseName("morning"), frozenset({_HARU}))

    def test_fainted_person_does_not_keep_the_morning_for_later(self) -> None:
        """朝の知らせを届けても、気を失っているアキには、起きてから知る知らせとしてたまらない。"""
        world = self._dawn_with_aki_fainted()
        [entered] = world.events_of(TimeOfDayChangedEvent)
        stimuli = StimulusTranslator().stimuli_of(entered, world.design)

        DeliverPerception(
            world.scope,
            ObservationExit(_WORLD, half_hour_ticks_from_midnight(), clock_wording(), _NoOneListening()),
            PerceptionReportsReceived(),
        )(DeliverPerceptionCommand(cause=TimePassed(), from_actions=(), from_states=stimuli))

        assert stimuli
        assert world.read(lambda session: session.facts().missed_notices(_AKI).notices()) == ()

    def test_person_fainting_in_the_tick_of_dawn_does_not_keep_the_morning(self) -> None:
        """朝に入る tick に飢えで倒れたハルは、相手を選んだ時点では起きていて相手に載るが、朝の知らせをためない。"""
        base = world_rules_for_tests()
        starving = replace(
            base,
            hunger=replace(
                base.hunger, per_tick=HungerAmount(1), limit=HungerAmount(1), starvation_damage=Damage(9999)
            ),
        )
        world = _World(characters=(character("haru", "plaza"),), rules=starving, day_night=_DAWN_AT_TICK_1)
        world.pass_ticks(1)
        [entered] = world.events_of(TimeOfDayChangedEvent)
        stimuli = StimulusTranslator().stimuli_of(entered, world.design)

        DeliverPerception(
            world.scope,
            ObservationExit(_WORLD, half_hour_ticks_from_midnight(), clock_wording(), _NoOneListening()),
            PerceptionReportsReceived(),
        )(DeliverPerceptionCommand(cause=TimePassed(), from_actions=(), from_states=stimuli))

        assert entered.audience == frozenset({_HARU})
        assert world.read(lambda session: session.facts().vitals(_HARU).is_down())
        assert world.read(lambda session: session.facts().missed_notices(_HARU).notices()) == ()


class _NoOneListening:
    def receive(self, person: PersonId, observation: object) -> None:
        pass
