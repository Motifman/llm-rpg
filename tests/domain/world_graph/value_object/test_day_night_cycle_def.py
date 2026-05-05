"""DayNightCycleDef / DayNightPhaseDef / TimeOfDay の単体テスト。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    DayNightCycleValidationException,
    DayNightPhaseValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.day_night_cycle_def import (
    DayNightCycleDef,
)
from ai_rpg_world.domain.world_graph.value_object.day_night_phase_def import (
    DayNightPhaseDef,
)
from ai_rpg_world.domain.world_graph.value_object.time_of_day import TimeOfDay


def _make_phases() -> tuple[DayNightPhaseDef, ...]:
    return (
        DayNightPhaseDef(name="dawn", start_ratio=0.0, display_text="夜明け",
                         ambient_light=0.4, is_dark=False),
        DayNightPhaseDef(name="morning", start_ratio=0.1, display_text="朝",
                         ambient_light=0.9, is_dark=False),
        DayNightPhaseDef(name="noon", start_ratio=0.25, display_text="昼",
                         ambient_light=1.0, is_dark=False),
        DayNightPhaseDef(name="evening", start_ratio=0.65, display_text="夕暮れ",
                         ambient_light=0.5, is_dark=False),
        DayNightPhaseDef(name="night", start_ratio=0.8, display_text="夜",
                         ambient_light=0.1, is_dark=True),
    )


class TestDayNightPhaseDefValidation:
    """DayNightPhaseDef のバリデーション挙動。"""

    def test_empty_name_is_rejected(self) -> None:
        """フェーズ名が空文字列の場合は ValidationException を投げる。"""
        with pytest.raises(DayNightPhaseValidationException, match="name"):
            DayNightPhaseDef(name="", start_ratio=0.0, display_text="X",
                             ambient_light=0.5, is_dark=False)

    @pytest.mark.parametrize("ratio", [-0.01, 1.0, 1.5])
    def test_start_ratio_out_of_range_rejected(self, ratio: float) -> None:
        """start_ratio が [0.0, 1.0) の範囲外なら ValidationException を投げる。"""
        with pytest.raises(DayNightPhaseValidationException, match="start_ratio"):
            DayNightPhaseDef(name="x", start_ratio=ratio, display_text="X",
                             ambient_light=0.5, is_dark=False)

    @pytest.mark.parametrize("light", [-0.1, 1.01])
    def test_ambient_light_out_of_range_rejected(self, light: float) -> None:
        """ambient_light が [0.0, 1.0] の範囲外なら ValidationException を投げる。"""
        with pytest.raises(DayNightPhaseValidationException, match="ambient_light"):
            DayNightPhaseDef(name="x", start_ratio=0.0, display_text="X",
                             ambient_light=light, is_dark=False)


class TestDayNightCycleDefValidation:
    """DayNightCycleDef のバリデーション挙動。"""

    def test_ticks_per_day_must_be_positive(self) -> None:
        """ticks_per_day が 0 以下なら ValidationException を投げる。"""
        with pytest.raises(DayNightCycleValidationException, match="ticks_per_day"):
            DayNightCycleDef(ticks_per_day=0, starting_tick_in_day=0,
                             phases=_make_phases())

    def test_starting_tick_in_day_within_range(self) -> None:
        """starting_tick_in_day が ticks_per_day 以上なら ValidationException を投げる。"""
        with pytest.raises(DayNightCycleValidationException, match="starting_tick_in_day"):
            DayNightCycleDef(ticks_per_day=240, starting_tick_in_day=240,
                             phases=_make_phases())

    def test_phases_must_not_be_empty(self) -> None:
        """phases が空タプルなら ValidationException を投げる。"""
        with pytest.raises(DayNightCycleValidationException, match="phases"):
            DayNightCycleDef(ticks_per_day=240, starting_tick_in_day=0, phases=())

    def test_first_phase_must_start_at_zero(self) -> None:
        """先頭フェーズの start_ratio が 0.0 でなければ ValidationException を投げる。"""
        phases = (
            DayNightPhaseDef(name="dawn", start_ratio=0.1, display_text="夜明け",
                             ambient_light=0.4, is_dark=False),
        )
        with pytest.raises(DayNightCycleValidationException, match="start_ratio must be 0.0"):
            DayNightCycleDef(ticks_per_day=240, starting_tick_in_day=0, phases=phases)

    def test_phases_must_be_sorted_strictly_ascending(self) -> None:
        """phases が start_ratio の昇順に並んでいなければ ValidationException を投げる。"""
        phases = (
            DayNightPhaseDef(name="a", start_ratio=0.0, display_text="A",
                             ambient_light=0.5, is_dark=False),
            DayNightPhaseDef(name="b", start_ratio=0.0, display_text="B",
                             ambient_light=0.5, is_dark=False),
        )
        with pytest.raises(DayNightCycleValidationException, match="sorted"):
            DayNightCycleDef(ticks_per_day=240, starting_tick_in_day=0, phases=phases)

    def test_duplicate_phase_names_rejected(self) -> None:
        """フェーズ名が重複している場合は ValidationException を投げる。"""
        phases = (
            DayNightPhaseDef(name="a", start_ratio=0.0, display_text="A",
                             ambient_light=0.5, is_dark=False),
            DayNightPhaseDef(name="a", start_ratio=0.5, display_text="A2",
                             ambient_light=0.5, is_dark=False),
        )
        with pytest.raises(DayNightCycleValidationException, match="Duplicate phase name"):
            DayNightCycleDef(ticks_per_day=240, starting_tick_in_day=0, phases=phases)


class TestTimeOfDayCalculation:
    """time_of_day_at による TimeOfDay 計算の正しさを検証する。"""

    @pytest.fixture
    def cycle(self) -> DayNightCycleDef:
        return DayNightCycleDef(
            ticks_per_day=240,
            starting_tick_in_day=0,
            phases=_make_phases(),
        )

    def test_tick_zero_is_first_phase(self, cycle: DayNightCycleDef) -> None:
        """tick=0 では最初のフェーズ（dawn）に属し、ratio は 0.0 になる。"""
        tod = cycle.time_of_day_at(WorldTick(0))
        assert tod.phase_name == "dawn"
        assert tod.ratio == 0.0
        assert tod.is_dark is False

    def test_phase_changes_at_boundary(self, cycle: DayNightCycleDef) -> None:
        """境界 tick の直前と直後でフェーズが切り替わる。"""
        # ticks_per_day=240, morning start_ratio=0.1 → tick 24 から
        tod_before = cycle.time_of_day_at(WorldTick(23))
        tod_at = cycle.time_of_day_at(WorldTick(24))
        assert tod_before.phase_name == "dawn"
        assert tod_at.phase_name == "morning"

    def test_night_is_dark(self, cycle: DayNightCycleDef) -> None:
        """夜フェーズの tick では is_dark=True が返る。"""
        # night start_ratio=0.8 → tick 192
        tod = cycle.time_of_day_at(WorldTick(200))
        assert tod.phase_name == "night"
        assert tod.is_dark is True

    def test_wraps_around_after_full_day(self, cycle: DayNightCycleDef) -> None:
        """1日経過後の tick は同じ ratio・フェーズに戻る。"""
        tod_day1 = cycle.time_of_day_at(WorldTick(0))
        tod_day2 = cycle.time_of_day_at(WorldTick(240))
        assert tod_day1.phase_name == tod_day2.phase_name
        assert tod_day1.ratio == tod_day2.ratio

    def test_starting_tick_offset_applied(self) -> None:
        """starting_tick_in_day 分だけ初期位置がオフセットされる。"""
        # starting_tick_in_day=120 (=0.5) → tick 0 でも正午（noon）相当
        cycle = DayNightCycleDef(
            ticks_per_day=240,
            starting_tick_in_day=120,
            phases=_make_phases(),
        )
        tod = cycle.time_of_day_at(WorldTick(0))
        # ratio 0.5 → noon (start_ratio 0.25) と evening (0.65) の間 → noon
        assert tod.phase_name == "noon"
        assert tod.ratio == pytest.approx(0.5)

    def test_returns_time_of_day_instance(self, cycle: DayNightCycleDef) -> None:
        """戻り値が TimeOfDay 値オブジェクトのインスタンスであることを保証する。"""
        tod = cycle.time_of_day_at(WorldTick(0))
        assert isinstance(tod, TimeOfDay)
