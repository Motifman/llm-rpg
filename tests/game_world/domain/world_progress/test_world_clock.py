from __future__ import annotations

from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.person_conditions import IsAtSpotCondition
from ai_rpg_world.game_world.domain.condition.subject import EachPerson
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.declaration.no_announcement import NoAnnouncement
from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    DayNightDeclaration,
    DayPhaseDeclaration,
    DayPhaseName,
    NoDayNight,
    TimeOfDay,
)
from ai_rpg_world.game_world.domain.declaration.time_and_weather.everyone_awake import EveryoneAwake
from ai_rpg_world.game_world.domain.person import PersonVitals
from ai_rpg_world.game_world.domain.value_object import HitPoints, PersonId, Ticks, WorldId, WorldTick
from ai_rpg_world.game_world.domain.whereabouts import PersonBody
from ai_rpg_world.game_world.domain.world_progress import TimeOfDayChangedEvent, WorldClock, WorldTickAdvancedEvent
from tests.game_world.support.memento_for_tests import rebuilt_from_memento
from tests.game_world.support.world_design_for_tests import spot
from tests.game_world.support.world_in_memory import world_in_memory

_WORLD = WorldId("island")


class _NobodyInTheWorld:
    def people(self) -> tuple[PersonId, ...]:
        return ()


_NOBODY: WorldFacts = _NobodyInTheWorld()  # type: ignore[assignment]


_HARU, _GEN = PersonId("haru"), PersonId("gen")
_SQUARE, _TUNNEL = spot("square"), spot("tunnel")
_AT_SQUARE = PeopleSelection(where=IsAtSpotCondition(who=EachPerson(), spot=_SQUARE, failure_text=NoText()))


def _village() -> WorldSession:
    world = world_in_memory(
        world=_WORLD,
        people=(_HARU, _GEN),
        spots=(_SQUARE, _TUNNEL),
        vitals=tuple(PersonVitals.start(person, HitPoints(current=10, maximum=10)) for person in (_HARU, _GEN)),
    )
    world.aggregates().whereabouts().place(PersonBody(_HARU), _SQUARE)
    world.aggregates().whereabouts().place(PersonBody(_GEN), _TUNNEL)
    return world


def _day_night(starts_at: int, day_audience: PeopleSelection | EveryoneAwake = EveryoneAwake()) -> DayNightDeclaration:
    return DayNightDeclaration(
        ticks_per_day=Ticks(24),
        starts_at=TimeOfDay(starts_at),
        phases=(
            DayPhaseDeclaration(
                name=DayPhaseName("昼"),
                begins_at=TimeOfDay(6),
                dark=False,
                announcement=NoAnnouncement(),
                audience=day_audience,
            ),
            DayPhaseDeclaration(
                name=DayPhaseName("夜"),
                begins_at=TimeOfDay(18),
                dark=True,
                announcement=NoAnnouncement(),
                audience=EveryoneAwake(),
            ),
        ),
    )


class TestWorldClockAdvance:
    """WorldClock.advance が時刻を 1 tick 進め、進んだことと昼夜の段階の変わり目をイベントにためることを保証する。"""

    def test_starts_at_tick_zero(self) -> None:
        """作ったばかりの時計の now は tick 0。"""
        assert WorldClock.start(_WORLD).now() == WorldTick(0)

    def test_advance_moves_now_by_one_tick(self) -> None:
        """advance を 2 回呼ぶと now は tick 2 になる。"""
        clock = WorldClock.start(_WORLD)

        clock.advance(NoDayNight(), _NOBODY)
        clock.advance(NoDayNight(), _NOBODY)

        assert clock.now() == WorldTick(2)

    def test_advance_records_tick_advanced_event_with_before_and_after(self) -> None:
        """tick 0 からの advance は、世界と、変わる前の tick 0 と後の tick 1 を持つ WorldTickAdvancedEvent をためる。"""
        clock = WorldClock.start(_WORLD)

        clock.advance(NoDayNight(), _NOBODY)

        [event] = clock.get_events()
        assert isinstance(event, WorldTickAdvancedEvent)
        assert (event.world_id, event.before, event.after) == (_WORLD, WorldTick(0), WorldTick(1))

    def test_crossing_phase_boundary_records_time_of_day_changed_event(self) -> None:
        """昼が 6 から始まる昼夜で 5 から 6 へ進むと、変わる前の夜と後の昼を持つ TimeOfDayChangedEvent をためる。"""
        clock = WorldClock.start(_WORLD)
        day_night = _day_night(starts_at=5)

        clock.advance(day_night, _NOBODY)

        [tick_event, phase_event] = clock.get_events()
        assert isinstance(tick_event, WorldTickAdvancedEvent)
        assert isinstance(phase_event, TimeOfDayChangedEvent)
        assert (phase_event.world_id, phase_event.before, phase_event.after, phase_event.at) == (
            _WORLD,
            DayPhaseName("夜"),
            DayPhaseName("昼"),
            WorldTick(1),
        )

    def test_time_of_day_changed_event_carries_the_people_the_entered_phase_reaches(self) -> None:
        """広場にハル、坑道にゲンがいて、広場の人に届く昼に入ると、TimeOfDayChangedEvent にハルだけが届く相手として載る。"""
        world = _village()
        day_night = _day_night(starts_at=5, day_audience=_AT_SQUARE)

        world.clock().advance(day_night, world.facts())

        [phase_event] = [event for event in world.clock().get_events() if isinstance(event, TimeOfDayChangedEvent)]
        assert phase_event.audience == frozenset({_HARU})

    def test_advance_within_same_phase_records_no_time_of_day_event(self) -> None:
        """昼のうちに 7 から 8 へ進んでも、TimeOfDayChangedEvent はためない。"""
        clock = WorldClock.start(_WORLD)

        clock.advance(_day_night(starts_at=7), _NOBODY)

        assert [type(event) for event in clock.get_events()] == [WorldTickAdvancedEvent]

    def test_crossing_midnight_within_night_records_no_time_of_day_event(self) -> None:
        """夜が 18 から日をまたいで続く昼夜で 23 から 0 へ進んでも、同じ夜なので TimeOfDayChangedEvent はためない。"""
        clock = WorldClock.start(_WORLD)

        clock.advance(_day_night(starts_at=23), _NOBODY)

        assert [type(event) for event in clock.get_events()] == [WorldTickAdvancedEvent]

    def test_no_day_night_records_no_time_of_day_event(self) -> None:
        """昼夜を宣言しない世界では、何 tick 進めても TimeOfDayChangedEvent をためない。"""
        clock = WorldClock.start(_WORLD)

        for _ in range(30):
            clock.advance(NoDayNight(), _NOBODY)

        assert all(isinstance(event, WorldTickAdvancedEvent) for event in clock.get_events())


class TestWorldClockTimeOfDay:
    """WorldClock.time_of_day が、今の tick を昼夜の宣言で 1 日の中の位置に直すことを保証する。"""

    def test_returns_position_in_day_from_starts_at(self) -> None:
        """starts_at が 22 の世界で 3 tick 進めると、1 日の中の 1 になる。"""
        clock = WorldClock.start(_WORLD)
        day_night = _day_night(starts_at=22)
        for _ in range(3):
            clock.advance(day_night, _NOBODY)

        assert clock.time_of_day(day_night) == TimeOfDay(1)


class TestWorldClockIdentity:
    """WorldClock が、自分の世界の WorldId を持つことを保証する。"""

    def test_keeps_world_id(self) -> None:
        """作るときに渡した WorldId を world_id として持つ。"""
        assert WorldClock.start(_WORLD).world_id == _WORLD


class TestWorldClockMemento:
    """WorldClock を memento から作り直すと、今の tick が元と同じになり、イベントは出ないことを保証する。"""

    def test_rebuilt_clock_is_at_the_same_tick(self) -> None:
        """3 回進めた時計を作り直すと、tick 3 にいる。"""
        clock = WorldClock.start(_WORLD)
        for _ in range(3):
            clock.advance(NoDayNight(), _NOBODY)

        rebuilt = rebuilt_from_memento(clock)

        assert rebuilt.memento() == clock.memento()
        assert rebuilt.now() == WorldTick(3)
        assert rebuilt.world_id == _WORLD

    def test_rebuilding_records_no_event(self) -> None:
        """進めたあとの memento から作り直しても、作り直したものはイベントをためていない。"""
        clock = WorldClock.start(_WORLD)
        clock.advance(NoDayNight(), _NOBODY)

        assert rebuilt_from_memento(clock).get_events() == []
