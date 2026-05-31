"""SpotGraphDayNightStageService の挙動検証。

純粋計算は DayNightCycleDef.time_of_day_at にテストされているため、
本テストでは stage が tick で TimeOfDay を更新する経路、フェーズ変化
callback、provider の最新値取得を中心に検証する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.world_graph.spot_graph_day_night_stage_service import (
    SpotGraphDayNightStageService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.value_object.day_night_cycle_def import (
    DayNightCycleDef,
)
from ai_rpg_world.domain.world_graph.value_object.day_night_phase_def import (
    DayNightPhaseDef,
)


def _make_4phase_cycle(ticks_per_day: int = 12) -> DayNightCycleDef:
    """朝/昼/夕暮れ/夜の 4 フェーズで構築する。

    survival_island.json の actual ratios (0.0 / 0.25 / 0.5 / 0.66) と合わせる。
    night.start_ratio を 0.66 にすることで、本シナリオデータ上での挙動を
    テストできる。テスト fixture と生産データの乖離を防ぐための同期。
    """
    return DayNightCycleDef(
        ticks_per_day=ticks_per_day,
        starting_tick_in_day=0,
        phases=(
            DayNightPhaseDef(
                name="morning", start_ratio=0.0,
                display_text="朝", ambient_light=0.9, is_dark=False,
            ),
            DayNightPhaseDef(
                name="noon", start_ratio=0.25,
                display_text="昼", ambient_light=1.0, is_dark=False,
            ),
            DayNightPhaseDef(
                name="evening", start_ratio=0.5,
                display_text="夕暮れ", ambient_light=0.5, is_dark=False,
            ),
            DayNightPhaseDef(
                name="night", start_ratio=0.66,
                display_text="夜", ambient_light=0.1, is_dark=True,
            ),
        ),
    )


class TestSpotGraphDayNightStageService:
    """tick による現在時刻の更新とフェーズ変化通知。"""

    def test_初期状態は_starting_tick_の_TimeOfDay(self) -> None:
        """構築直後の current_time_of_day は starting_tick から計算される。"""
        cycle = _make_4phase_cycle()
        stage = SpotGraphDayNightStageService(cycle=cycle)
        tod = stage.current_time_of_day()
        assert tod.phase_name == "morning"

    def test_tick_進行で_TimeOfDay_が更新される(self) -> None:
        """run(tick) が走ると provider の返す TimeOfDay が新 tick のものになる。"""
        cycle = _make_4phase_cycle(ticks_per_day=12)
        stage = SpotGraphDayNightStageService(cycle=cycle)
        stage.run(WorldTick(6))  # 0.5 → evening
        assert stage.current_time_of_day().phase_name == "evening"
        stage.run(WorldTick(9))  # 0.75 → night
        assert stage.current_time_of_day().phase_name == "night"

    def test_フェーズ変化時に_callback_が_old_と_new_を渡して呼ばれる(self) -> None:
        """phase_changed_callback がフェーズ遷移時にのみ呼ばれる。"""
        cycle = _make_4phase_cycle(ticks_per_day=12)
        captured = []

        def cb(old, new):
            captured.append((old.phase_name, new.phase_name))

        stage = SpotGraphDayNightStageService(
            cycle=cycle, phase_changed_callback=cb,
        )
        # 同じフェーズ内 (morning) → 通知なし
        stage.run(WorldTick(1))
        assert captured == []
        # morning → noon
        stage.run(WorldTick(3))
        assert captured == [("morning", "noon")]
        # noon → evening
        stage.run(WorldTick(6))
        assert captured == [("morning", "noon"), ("noon", "evening")]

    def test_set_phase_changed_callback_で後付け注入できる(self) -> None:
        """二段構築 (escape_game_runtime 経路) のために set でも注入可能。"""
        cycle = _make_4phase_cycle(ticks_per_day=12)
        stage = SpotGraphDayNightStageService(cycle=cycle)
        captured = []
        stage.set_phase_changed_callback(
            lambda o, n: captured.append((o.phase_name, n.phase_name))
        )
        stage.run(WorldTick(3))
        assert captured == [("morning", "noon")]

    def test_callback_None_でも_run_は壊れない(self) -> None:
        """callback 無しの最小構成で例外を投げず動く。"""
        cycle = _make_4phase_cycle(ticks_per_day=12)
        stage = SpotGraphDayNightStageService(cycle=cycle)
        # 例外なし
        stage.run(WorldTick(3))
        stage.run(WorldTick(6))
        assert stage.current_time_of_day().phase_name == "evening"
