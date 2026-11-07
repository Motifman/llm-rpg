from __future__ import annotations

from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    DayNightDeclaration,
    DayPhaseDeclaration,
    DayPhaseName,
    NoAnnouncement,
    NoDayNight,
    TimeOfDay,
)
from ai_rpg_world.game_world.domain.value_object import Ticks, WorldId, WorldTick
from ai_rpg_world.game_world.domain.world_progress import TimeOfDayChangedEvent, WorldClock, WorldTickAdvancedEvent

_WORLD = WorldId("island")


def _day_night(starts_at: int) -> DayNightDeclaration:
    return DayNightDeclaration(
        ticks_per_day=Ticks(24),
        starts_at=TimeOfDay(starts_at),
        phases=(
            DayPhaseDeclaration(
                name=DayPhaseName("昼"), begins_at=TimeOfDay(6), dark=False, announcement=NoAnnouncement()
            ),
            DayPhaseDeclaration(
                name=DayPhaseName("夜"), begins_at=TimeOfDay(18), dark=True, announcement=NoAnnouncement()
            ),
        ),
    )


class TestWorldClockAdvance:
    """WorldClock.advance が時刻を 1 tick 進め、進んだことと昼夜の段階の変わり目をイベントにためることを保証する。"""

    def test_starts_at_tick_zero(self) -> None:
        """作ったばかりの時計の now は tick 0。"""
        assert WorldClock(_WORLD).now() == WorldTick(0)

    def test_advance_moves_now_by_one_tick(self) -> None:
        """advance を 2 回呼ぶと now は tick 2 になる。"""
        clock = WorldClock(_WORLD)

        clock.advance(NoDayNight())
        clock.advance(NoDayNight())

        assert clock.now() == WorldTick(2)

    def test_advance_records_tick_advanced_event_with_before_and_after(self) -> None:
        """tick 0 からの advance は、世界と、変わる前の tick 0 と後の tick 1 を持つ WorldTickAdvancedEvent をためる。"""
        clock = WorldClock(_WORLD)

        clock.advance(NoDayNight())

        [event] = clock.get_events()
        assert isinstance(event, WorldTickAdvancedEvent)
        assert (event.world_id, event.before, event.after) == (_WORLD, WorldTick(0), WorldTick(1))

    def test_crossing_phase_boundary_records_time_of_day_changed_event(self) -> None:
        """昼が 6 から始まる昼夜で 5 から 6 へ進むと、変わる前の夜と後の昼を持つ TimeOfDayChangedEvent をためる。"""
        clock = WorldClock(_WORLD)
        day_night = _day_night(starts_at=5)

        clock.advance(day_night)

        [tick_event, phase_event] = clock.get_events()
        assert isinstance(tick_event, WorldTickAdvancedEvent)
        assert isinstance(phase_event, TimeOfDayChangedEvent)
        assert (phase_event.world_id, phase_event.before, phase_event.after, phase_event.at) == (
            _WORLD,
            DayPhaseName("夜"),
            DayPhaseName("昼"),
            WorldTick(1),
        )

    def test_advance_within_same_phase_records_no_time_of_day_event(self) -> None:
        """昼のうちに 7 から 8 へ進んでも、TimeOfDayChangedEvent はためない。"""
        clock = WorldClock(_WORLD)

        clock.advance(_day_night(starts_at=7))

        assert [type(event) for event in clock.get_events()] == [WorldTickAdvancedEvent]

    def test_no_day_night_records_no_time_of_day_event(self) -> None:
        """昼夜を宣言しない世界では、何 tick 進めても TimeOfDayChangedEvent をためない。"""
        clock = WorldClock(_WORLD)

        for _ in range(30):
            clock.advance(NoDayNight())

        assert all(isinstance(event, WorldTickAdvancedEvent) for event in clock.get_events())


class TestWorldClockTimeOfDay:
    """WorldClock.time_of_day が、今の tick を昼夜の宣言で 1 日の中の位置に直すことを保証する。"""

    def test_returns_position_in_day_from_starts_at(self) -> None:
        """starts_at が 22 の世界で 3 tick 進めると、1 日の中の 1 になる。"""
        clock = WorldClock(_WORLD)
        day_night = _day_night(starts_at=22)
        for _ in range(3):
            clock.advance(day_night)

        assert clock.time_of_day(day_night) == TimeOfDay(1)


class TestWorldClockIdentity:
    """WorldClock が、自分の世界の WorldId を持つことを保証する。"""

    def test_keeps_world_id(self) -> None:
        """作るときに渡した WorldId を world_id として持つ。"""
        assert WorldClock(_WORLD).world_id == _WORLD
