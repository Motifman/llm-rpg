from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.declaration.no_announcement import NoAnnouncement
from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    DayNightDeclaration,
    DayPhaseChange,
    DayPhaseDeclaration,
    DayPhaseName,
    NoDayNight,
    TimeOfDay,
)
from ai_rpg_world.game_world.domain.exception.condition_exception import NotDeclaredInThisWorldException
from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.exception.time_and_weather_exception import (
    DayPhaseNameDuplicatedException,
    DayPhasesNotAscendingException,
    NoDayPhasesDeclaredException,
    TimeOfDayBeyondDayException,
)
from ai_rpg_world.game_world.domain.exception.world_design_exception import BlankDeclaredNameException
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import Ticks, WorldTick


def _phase(name: str, begins_at: int, *, dark: bool = False) -> DayPhaseDeclaration:
    return DayPhaseDeclaration(
        name=DayPhaseName(name), begins_at=TimeOfDay(begins_at), dark=dark, announcement=NoAnnouncement()
    )


def _day(*phases: DayPhaseDeclaration, ticks_per_day: int = 24, starts_at: int = 0) -> DayNightDeclaration:
    return DayNightDeclaration(ticks_per_day=Ticks(ticks_per_day), starts_at=TimeOfDay(starts_at), phases=phases)


class TestTimeOfDay:
    """TimeOfDay が 1 日の中の tick の位置として、負の値を断ることを保証する。"""

    def test_rejects_negative_tick_of_day(self) -> None:
        """tick_of_day に -1 を渡すと ValueOutOfRangeException を投げる。"""
        with pytest.raises(ValueOutOfRangeException):
            TimeOfDay(-1)


class TestDayPhaseName:
    """DayPhaseName が条件から指される宣言の名前として、空の名前を断ることを保証する。"""

    def test_rejects_blank_name(self) -> None:
        """空白だけの名前は BlankDeclaredNameException で断る。"""
        with pytest.raises(BlankDeclaredNameException):
            DayPhaseName("  ")


class TestDayPhaseAnnouncement:
    """DayPhaseDeclaration.announcement が、段階に入ったときの知らせを人を割り当てる前の文で持つことを保証する。"""

    def test_keeps_announcement_text_unassigned(self) -> None:
        """announcement に文を渡すと、人のプレースホルダーを割り当てないまま持つ。"""
        phase = DayPhaseDeclaration(
            name=DayPhaseName("夜"),
            begins_at=TimeOfDay(20),
            dark=True,
            announcement=TextWithUnassignedPeople("日が沈んだ。"),
        )

        assert phase.announcement == TextWithUnassignedPeople("日が沈んだ。")


class TestDayNightDeclarationValidation:
    """DayNightDeclaration が、1 日を切れ目なく覆えない段階の並びを作るときに断ることを保証する。"""

    def test_rejects_zero_ticks_per_day(self) -> None:
        """ticks_per_day が 0 の昼夜は ValueOutOfRangeException で断る。"""
        with pytest.raises(ValueOutOfRangeException):
            _day(_phase("昼", 0), ticks_per_day=0)

    def test_rejects_no_phases(self) -> None:
        """段階が 1 つも無い昼夜は NoDayPhasesDeclaredException で断る。"""
        with pytest.raises(NoDayPhasesDeclaredException):
            _day()

    def test_rejects_phases_not_in_ascending_order(self) -> None:
        """begins_at が前の段階以下の段階があると DayPhasesNotAscendingException で断る。"""
        with pytest.raises(DayPhasesNotAscendingException):
            _day(_phase("昼", 10), _phase("朝", 6))

    def test_rejects_phases_beginning_at_same_time(self) -> None:
        """2 つの段階が同じ begins_at で始まると DayPhasesNotAscendingException で断る。"""
        with pytest.raises(DayPhasesNotAscendingException):
            _day(_phase("朝", 6), _phase("昼", 6))

    def test_rejects_phase_beginning_beyond_the_day(self) -> None:
        """begins_at が ticks_per_day 以上の段階は TimeOfDayBeyondDayException で断る。"""
        with pytest.raises(TimeOfDayBeyondDayException):
            _day(_phase("朝", 6), _phase("夜", 24))

    def test_rejects_starts_at_beyond_the_day(self) -> None:
        """starts_at が ticks_per_day 以上なら TimeOfDayBeyondDayException で断る。"""
        with pytest.raises(TimeOfDayBeyondDayException):
            _day(_phase("昼", 0), starts_at=24)

    def test_rejects_duplicated_phase_names(self) -> None:
        """同じ名前の段階が 2 つあると、名前から段階を引けないので DayPhaseNameDuplicatedException で断る。"""
        with pytest.raises(DayPhaseNameDuplicatedException):
            _day(_phase("夜", 0), _phase("昼", 6), _phase("夜", 20))


class TestDayNightDeclarationTimeOfDay:
    """DayNightDeclaration.time_of_day_at が、世界の tick を starts_at からの 1 日の中の位置に直すことを保証する。"""

    def test_offsets_world_tick_by_starts_at(self) -> None:
        """starts_at が 6 の世界の tick 3 は、1 日の中の 9 になる。"""
        day = _day(_phase("昼", 0), starts_at=6)

        assert day.time_of_day_at(WorldTick(3)) == TimeOfDay(9)

    def test_wraps_around_the_day(self) -> None:
        """ticks_per_day が 24、starts_at が 20 の世界の tick 5 は、日をまたいで 1 になる。"""
        day = _day(_phase("昼", 0), starts_at=20)

        assert day.time_of_day_at(WorldTick(5)) == TimeOfDay(1)


class TestDayNightDeclarationPhaseAt:
    """DayNightDeclaration.phase_at が、1 日の中の位置を覆う段階を返すことを保証する。"""

    def test_returns_phase_that_began_last(self) -> None:
        """朝 6・昼 10・夜 20 の昼夜で 12 は昼になる。"""
        day = _day(_phase("朝", 6), _phase("昼", 10), _phase("夜", 20, dark=True))

        assert day.phase_at(TimeOfDay(12)).name == DayPhaseName("昼")

    def test_phase_begins_at_its_own_begins_at(self) -> None:
        """段階の begins_at ちょうどの位置は、その段階に入っている。"""
        day = _day(_phase("朝", 6), _phase("昼", 10))

        assert day.phase_at(TimeOfDay(10)).name == DayPhaseName("昼")

    def test_time_before_first_phase_belongs_to_last_phase(self) -> None:
        """朝 6・夜 20 の昼夜で 3 は、前の日から続く夜になる。"""
        day = _day(_phase("朝", 6), _phase("夜", 20, dark=True))

        assert day.phase_at(TimeOfDay(3)).name == DayPhaseName("夜")


class TestDayNightDeclarationPhaseChanges:
    """DayNightDeclaration.phase_changes が、2 つの tick のあいだで段階が変わったときだけ、その変わり目を返すことを保証する。"""

    def test_returns_change_when_phase_differs(self) -> None:
        """朝 6・夜 20 の昼夜で tick 5 から 6 へ進むと、夜から朝への変わり目を 1 つ返す。"""
        day = _day(_phase("朝", 6), _phase("夜", 20, dark=True))

        assert day.phase_changes(WorldTick(5), WorldTick(6)) == (
            DayPhaseChange(before=DayPhaseName("夜"), after=DayPhaseName("朝")),
        )

    def test_returns_nothing_within_same_phase(self) -> None:
        """朝 6・夜 20 の昼夜で tick 7 から 8 へ進むと、同じ朝のままなので変わり目を返さない。"""
        day = _day(_phase("朝", 6), _phase("夜", 20, dark=True))

        assert day.phase_changes(WorldTick(7), WorldTick(8)) == ()


class TestDayNightDeclarationDeclaredPhases:
    """DayNightDeclaration が、昼夜を宣言していることと、宣言した段階の名前を答えることを保証する。"""

    def test_is_declared(self) -> None:
        """昼夜の宣言は、昼夜が宣言されているかを問われると、宣言されていると答える。"""
        assert _day(_phase("昼", 0)).is_declared()

    def test_phase_names_lists_declared_phases(self) -> None:
        """朝・夜を宣言した昼夜は、段階の名前として朝と夜を返す。"""
        day = _day(_phase("朝", 6), _phase("夜", 20, dark=True))

        assert day.phase_names() == frozenset({DayPhaseName("朝"), DayPhaseName("夜")})


class TestNoDayNight:
    """昼夜を宣言しない世界の NoDayNight が、昼夜の宣言と同じ問いに「昼夜は無い」と答えることを保証する。"""

    def test_time_of_day_at_raises_not_declared(self) -> None:
        """1 日の中の位置を問われると、「昼夜を宣言していない」という文面の NotDeclaredInThisWorldException を投げる。"""
        with pytest.raises(NotDeclaredInThisWorldException, match="^this world declares no day and night$"):
            NoDayNight().time_of_day_at(WorldTick(0))

    def test_phase_at_raises_not_declared(self) -> None:
        """段階を問われると、「昼夜を宣言していない」という文面の NotDeclaredInThisWorldException を投げる。"""
        with pytest.raises(NotDeclaredInThisWorldException, match="^this world declares no day and night$"):
            NoDayNight().phase_at(TimeOfDay(0))

    def test_phase_changes_returns_nothing(self) -> None:
        """どの 2 つの tick のあいだの変わり目を問われても、変わり目を返さない。"""
        assert NoDayNight().phase_changes(WorldTick(5), WorldTick(6)) == ()

    def test_is_not_declared_and_has_no_phase_names(self) -> None:
        """昼夜が宣言されているかを問われると宣言されていないと答え、段階の名前は 1 つも返さない。"""
        assert (NoDayNight().is_declared(), NoDayNight().phase_names()) == (False, frozenset())
