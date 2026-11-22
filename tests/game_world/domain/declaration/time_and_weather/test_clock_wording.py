from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.time_and_weather import ClockWording, DayAndClockTime
from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException

_CLOCK = ClockWording(day="Day {day}", late_night="深夜 ", late_night_before_hour=6)


class TestClockWording:
    """ClockWording が、何日目と時:分を、深夜の時間帯に印を付けて書くことを保証する。"""

    @pytest.mark.parametrize(
        ("day", "hour", "minute", "written"),
        [
            (1, 0, 30, "Day 1 深夜 0:30"),
            (1, 5, 59, "Day 1 深夜 5:59"),
            (1, 6, 0, "Day 1 6:00"),
            (2, 13, 5, "Day 2 13:05"),
        ],
        ids=["midnight", "last_minute_of_late_night", "first_minute_after_late_night", "afternoon_of_day_two"],
    )
    def test_writes_the_day_and_the_clock(self, day: int, hour: int, minute: int, written: str) -> None:
        """深夜の境目 6 時の前は「深夜 」を付け、時は 0 を詰めずに、分は 2 桁で書く。"""
        assert _CLOCK.display(DayAndClockTime(day=day, hour=hour, minute=minute)) == written

    @pytest.mark.parametrize("day", ["Day", "Day {day} {month}", "Day {day"], ids=["no_day", "other_name", "unclosed"])
    def test_day_wording_that_cannot_write_the_day_is_refused(self, day: str) -> None:
        """日の書き方に {day} が無いか、{day} 以外の名前や閉じない括弧があると、作るときに ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            ClockWording(day=day, late_night="深夜 ", late_night_before_hour=6)

    def test_day_wording_with_a_format_spec_is_allowed(self) -> None:
        """日の書き方に書式つきの {day:02d} を書くと、2 桁で書く。"""
        clock = ClockWording(day="Day {day:02d}", late_night="深夜 ", late_night_before_hour=6)

        assert clock.display(DayAndClockTime(day=3, hour=7, minute=0)) == "Day 03 7:00"
