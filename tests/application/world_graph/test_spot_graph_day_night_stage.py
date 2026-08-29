"""SpotGraphDayNightStageService の挙動検証。

純粋計算は DayNightCycleDef.time_of_day_at にテストされているため、
本テストでは stage の純粋な更新規則とproviderの最新値取得を検証する。
公開runの確定境界はtest_weather_day_night_command_scope.pyで保証する。
"""

from __future__ import annotations

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

    survival_island_v2.json の actual ratios (0.0 / 0.25 / 0.5 / 0.66) と合わせる。
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
    """tickによる現在時刻の更新とフェーズ遷移値を保証する。"""

    def test_initial_state_starting_tick_time_day(self) -> None:
        """構築直後の current_time_of_day は starting_tick から計算される。"""
        cycle = _make_4phase_cycle()
        stage = SpotGraphDayNightStageService(cycle=cycle)
        tod = stage.current_time_of_day()
        assert tod.phase_name == "morning"

    def test_advance_updates_current_time_of_day(self) -> None:
        """_advanceはproviderの返すTimeOfDayを新tickの値へ更新する。"""
        cycle = _make_4phase_cycle(ticks_per_day=12)
        stage = SpotGraphDayNightStageService(cycle=cycle)
        stage._advance(WorldTick(6))  # 0.5 → evening
        assert stage.current_time_of_day().phase_name == "evening"
        stage._advance(WorldTick(9))  # 0.75 → night
        assert stage.current_time_of_day().phase_name == "night"

    def test_advance_returns_transition_only_when_phase_changes(self) -> None:
        """_advanceはフェーズが変わったtickだけ開始前後の値を返す。"""
        cycle = _make_4phase_cycle(ticks_per_day=12)
        stage = SpotGraphDayNightStageService(cycle=cycle)

        assert stage._advance(WorldTick(1)) is None
        morning_to_noon = stage._advance(WorldTick(3))
        noon_to_evening = stage._advance(WorldTick(6))

        assert morning_to_noon is not None
        assert tuple(value.phase_name for value in morning_to_noon) == (
            "morning",
            "noon",
        )
        assert noon_to_evening is not None
        assert tuple(value.phase_name for value in noon_to_evening) == (
            "noon",
            "evening",
        )
