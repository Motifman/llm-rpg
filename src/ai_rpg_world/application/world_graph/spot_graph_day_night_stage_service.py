"""tick から TimeOfDay を計算する昼夜サイクルステージサービス。

SpotGraphSimulationApplicationService の tick パイプラインに組み込み、
毎tick で TimeOfDay を再計算する。フェーズが変化したときに observation
event を流すための callback も持つ (runtime が register する pattern)。

Weather (SpotGraphEnvironmentStageService) と独立したサービスにしている
理由は、weather が「ランダム遷移する状態」なのに対し day_night が「tick
の決定論的関数」であり、運用上の検証ポイントが異なるため。
"""

from __future__ import annotations

from typing import Callable, Optional

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.value_object.day_night_cycle_def import (
    DayNightCycleDef,
)
from ai_rpg_world.domain.world_graph.value_object.time_of_day import TimeOfDay


# (old_time_of_day, new_time_of_day) を受け取って観測を流す callback。
# None なら通知なし (silent な phase transition)。
PhaseChangedCallback = Callable[[TimeOfDay, TimeOfDay], None]


class SpotGraphDayNightStageService:
    """毎tick で TimeOfDay を更新し、フェーズ変化を callback で通知する。

    runtime が TimeOfDay にアクセスするには `current_time_of_day()` を呼ぶ。
    weather と同様に「provider」を露出することで他の stage / builder が
    現在時刻を読み取れる。
    """

    def __init__(
        self,
        cycle: DayNightCycleDef,
        *,
        starting_tick: Optional[WorldTick] = None,
        phase_changed_callback: Optional[PhaseChangedCallback] = None,
    ) -> None:
        self._cycle = cycle
        self._phase_changed_callback = phase_changed_callback
        # 初期 TimeOfDay は starting_tick (省略時は tick=0) で計算しておく。
        # runtime が tick driver 経由で呼ぶ前に build_full_prompt されても
        # current_time_of_day が None を返さないようにする。
        initial_tick = starting_tick or WorldTick(0)
        self._current = cycle.time_of_day_at(initial_tick)

    def run(self, current_tick: WorldTick) -> None:
        """tick の TimeOfDay を再計算し、フェーズが変化していたら通知する。"""
        new_time = self._cycle.time_of_day_at(current_tick)
        if new_time.phase_name != self._current.phase_name:
            old = self._current
            self._current = new_time
            if self._phase_changed_callback is not None:
                self._phase_changed_callback(old, new_time)
        else:
            self._current = new_time

    def current_time_of_day(self) -> TimeOfDay:
        """現在の TimeOfDay を返す (cross-service の provider)。"""
        return self._current

    def set_phase_changed_callback(
        self, callback: Optional[PhaseChangedCallback]
    ) -> None:
        """callback を後付けで注入する (二段構築用、weather と同じパターン)。"""
        self._phase_changed_callback = callback
