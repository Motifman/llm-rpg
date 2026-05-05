"""昼夜サイクルのステージサービス。

シミュレーションループから tick ごとに呼ばれ、フェーズが切り替わったら
DayPhaseChangedEvent を publisher 経由で発行する。

設計上のポイント:
- DayNightCycleDef は不変。tick だけを受け取って TimeOfDay を都度計算する。
- 直近に観測したフェーズ名を内部状態として保持し、変化を検知する。
- 「現在のフェーズを問い合わせる」用途は外部に provider 関数として公開する
  （AmbientSound 等が後段で消費する想定）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    DayPhaseChangedEvent,
)
from ai_rpg_world.domain.world_graph.value_object.day_night_cycle_def import (
    DayNightCycleDef,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.time_of_day import TimeOfDay


EventEmitter = Callable[[DayPhaseChangedEvent], None]


class SpotGraphDayNightStageService:
    """tick 進行に応じて昼夜フェーズの遷移を検知し、イベントを発火する。

    Attributes:
        cycle: 昼夜サイクル定義（不変）。
        spot_graph_id: イベントの aggregate_id に使う ID。
        emit: イベント発行関数（publisher.publish 等を bind）。
        _last_phase_name: 直前に観測したフェーズ名。None なら未初期化。
    """

    def __init__(
        self,
        *,
        cycle: DayNightCycleDef,
        spot_graph_id: SpotGraphId,
        emit: EventEmitter,
    ) -> None:
        self._cycle = cycle
        self._spot_graph_id = spot_graph_id
        self._emit = emit
        self._last_phase_name: Optional[str] = None

    def current_time_of_day(self, current_tick: WorldTick) -> TimeOfDay:
        """現在の TimeOfDay を返す（外部provider用途）。"""
        return self._cycle.time_of_day_at(current_tick)

    def run(self, current_tick: WorldTick) -> None:
        tod = self._cycle.time_of_day_at(current_tick)
        if self._last_phase_name is None:
            # 初回呼び出しは「変化なし」として扱う（開始時のフェーズを記録のみ）
            self._last_phase_name = tod.phase_name
            return
        if tod.phase_name == self._last_phase_name:
            return

        prev_name = self._last_phase_name
        self._last_phase_name = tod.phase_name
        self._emit(
            DayPhaseChangedEvent.create(
                aggregate_id=self._spot_graph_id,
                aggregate_type="SpotGraph",
                from_phase_name=prev_name,
                to_phase_name=tod.phase_name,
                to_phase_display_text=tod.display_text,
                ambient_light=tod.ambient_light,
                is_dark=tod.is_dark,
            )
        )


@dataclass
class DayNightCycleProvider:
    """現在の TimeOfDay を外部から問い合わせるための薄い provider。

    SpotGraphDayNightStageService.current_time_of_day を tick取得関数と
    bind して返すラッパー。AmbientSound や prompt builder が消費する想定。
    """

    cycle: DayNightCycleDef
    tick_provider: Callable[[], WorldTick]

    def get(self) -> TimeOfDay:
        return self.cycle.time_of_day_at(self.tick_provider())
