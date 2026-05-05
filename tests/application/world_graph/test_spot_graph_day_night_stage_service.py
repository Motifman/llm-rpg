"""SpotGraphDayNightStageService の単体テスト。"""

from __future__ import annotations

from typing import List

from ai_rpg_world.application.world_graph.spot_graph_day_night_stage_service import (
    DayNightCycleProvider,
    SpotGraphDayNightStageService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    DayPhaseChangedEvent,
)
from ai_rpg_world.domain.world_graph.value_object.day_night_cycle_def import (
    DayNightCycleDef,
)
from ai_rpg_world.domain.world_graph.value_object.day_night_phase_def import (
    DayNightPhaseDef,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


def _make_cycle(starting_tick: int = 0) -> DayNightCycleDef:
    return DayNightCycleDef(
        ticks_per_day=10,
        starting_tick_in_day=starting_tick,
        phases=(
            DayNightPhaseDef("day", 0.0, "昼", 1.0, False),
            DayNightPhaseDef("night", 0.5, "夜", 0.1, True),
        ),
    )


class _Recorder:
    def __init__(self) -> None:
        self.events: List[DayPhaseChangedEvent] = []

    def emit(self, ev: DayPhaseChangedEvent) -> None:
        self.events.append(ev)


class TestSpotGraphDayNightStageService:
    """SpotGraphDayNightStageService.run のフェーズ遷移検知挙動。"""

    def test_first_run_does_not_emit_event(self) -> None:
        """初回 run はフェーズ初期化のみ・イベントは発火しない。"""
        rec = _Recorder()
        service = SpotGraphDayNightStageService(
            cycle=_make_cycle(),
            spot_graph_id=SpotGraphId.create(1),
            emit=rec.emit,
        )
        service.run(WorldTick(0))
        assert rec.events == []

    def test_emits_event_on_phase_transition(self) -> None:
        """フェーズ境界を跨ぐと DayPhaseChangedEvent が発火する。"""
        rec = _Recorder()
        service = SpotGraphDayNightStageService(
            cycle=_make_cycle(),
            spot_graph_id=SpotGraphId.create(1),
            emit=rec.emit,
        )
        service.run(WorldTick(0))   # day（初期化）
        service.run(WorldTick(4))   # day 継続
        service.run(WorldTick(5))   # night へ遷移

        assert len(rec.events) == 1
        ev = rec.events[0]
        assert ev.from_phase_name == "day"
        assert ev.to_phase_name == "night"
        assert ev.to_phase_display_text == "夜"
        assert ev.is_dark is True

    def test_no_event_when_phase_unchanged(self) -> None:
        """フェーズが変わらない tick 経過ではイベントを出さない。"""
        rec = _Recorder()
        service = SpotGraphDayNightStageService(
            cycle=_make_cycle(),
            spot_graph_id=SpotGraphId.create(1),
            emit=rec.emit,
        )
        service.run(WorldTick(0))
        service.run(WorldTick(1))
        service.run(WorldTick(2))
        assert rec.events == []

    def test_wraparound_emits_back_to_first_phase(self) -> None:
        """1日が一周して最初のフェーズに戻る時もイベントが発火する。"""
        rec = _Recorder()
        service = SpotGraphDayNightStageService(
            cycle=_make_cycle(),
            spot_graph_id=SpotGraphId.create(1),
            emit=rec.emit,
        )
        service.run(WorldTick(0))    # day（初期化）
        service.run(WorldTick(5))    # → night
        service.run(WorldTick(10))   # → day（次の日）
        assert [e.to_phase_name for e in rec.events] == ["night", "day"]

    def test_current_time_of_day_returns_snapshot(self) -> None:
        """current_time_of_day は副作用なしに現在の TimeOfDay を返す。"""
        rec = _Recorder()
        service = SpotGraphDayNightStageService(
            cycle=_make_cycle(),
            spot_graph_id=SpotGraphId.create(1),
            emit=rec.emit,
        )
        tod = service.current_time_of_day(WorldTick(6))
        assert tod.phase_name == "night"
        assert rec.events == []  # 副作用なし


class TestDayNightCycleProvider:
    """DayNightCycleProvider.get の挙動。"""

    def test_provider_returns_current_time_of_day(self) -> None:
        """tick provider が返す tick から TimeOfDay を計算して返す。"""
        cycle = _make_cycle()
        ticks = iter([WorldTick(0), WorldTick(6)])
        provider = DayNightCycleProvider(
            cycle=cycle,
            tick_provider=lambda: next(ticks),
        )
        assert provider.get().phase_name == "day"
        assert provider.get().phase_name == "night"
