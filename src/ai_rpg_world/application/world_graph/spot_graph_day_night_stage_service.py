"""tick から TimeOfDay を計算する昼夜サイクルステージサービス。

SpotGraphSimulationApplicationService の tick パイプラインに組み込み、
毎tick で TimeOfDay を再計算する。フェーズが変化したときは確定区間へ
event を収集し、確定後の観測配送へ引き渡す。

Weather (SpotGraphEnvironmentStageService) と独立したサービスにしている
理由は、weather が「ランダム遷移する状態」なのに対し day_night が「tick
の決定論的関数」であり、運用上の検証ポイントが異なるため。
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.value_object.day_night_cycle_def import (
    DayNightCycleDef,
)
from ai_rpg_world.domain.world_graph.value_object.time_of_day import TimeOfDay
from ai_rpg_world.domain.world_graph.event.environment_event import (
    SpotGraphDayNightPhaseChangedEvent,
)

if TYPE_CHECKING:
    from ai_rpg_world.application.common.command_scope_factory import (
        CommandScopeFactoryPort,
    )


class SpotGraphDayNightStageService:
    """毎tick で TimeOfDay を更新し、フェーズ変化を確定後に通知する。

    runtime が TimeOfDay にアクセスするには `current_time_of_day()` を呼ぶ。
    weather と同様に「provider」を露出することで他の stage / builder が
    現在時刻を読み取れる。
    """

    def __init__(
        self,
        cycle: DayNightCycleDef,
        *,
        starting_tick: Optional[WorldTick] = None,
        command_scope_factory: "CommandScopeFactoryPort[object] | None" = None,
    ) -> None:
        self._cycle = cycle
        self._command_scope_factory = command_scope_factory
        # 初期 TimeOfDay は starting_tick (省略時は tick=0) で計算しておく。
        # runtime が tick driver 経由で呼ぶ前に build_full_prompt されても
        # current_time_of_day が None を返さないようにする。
        # NOTE: `starting_tick or WorldTick(0)` の falsy 依存を避けて `is None`
        # で明示する。WorldTick が将来 falsy になる可能性 (例: value=0 を
        # __bool__ で False 扱い) に対する保険。
        initial_tick = WorldTick(0) if starting_tick is None else starting_tick
        self._current = cycle.time_of_day_at(initial_tick)

    def run(self, current_tick: WorldTick) -> None:
        """tick の TimeOfDay を再計算し、フェーズが変化していたら通知する。"""
        factory = self._command_scope_factory
        if factory is None:
            raise RuntimeError("day/night command scope が未配線です")
        with factory.create() as scope:
            transition = self._advance(current_tick)
            if transition is None:
                return
            old_time, new_time = transition
            scope.collect(
                SpotGraphDayNightPhaseChangedEvent.create(
                    aggregate_id=current_tick,
                    aggregate_type="SpotGraphDayNightStage",
                    old_time=old_time,
                    new_time=new_time,
                    occurred_tick=current_tick,
                )
            )

    def _advance(
        self,
        current_tick: WorldTick,
    ) -> tuple[TimeOfDay, TimeOfDay] | None:
        new_time = self._cycle.time_of_day_at(current_tick)
        if new_time.phase_name != self._current.phase_name:
            old = self._current
            self._current = new_time
            return old, new_time
        self._current = new_time
        return None

    def rollback_snapshot(self) -> TimeOfDay:
        """現在の昼夜位置を返す。"""
        return self._current

    def restore_rollback_snapshot(self, snapshot: TimeOfDay) -> None:
        """失敗した遷移を開始前の昼夜位置へ戻す。"""
        self._current = snapshot

    def set_command_scope_factory(
        self,
        factory: "CommandScopeFactoryPort[object]",
    ) -> None:
        """本番stageを昼夜遷移1回の確定境界へ接続する。"""
        self._command_scope_factory = factory

    def current_time_of_day(self) -> TimeOfDay:
        """現在の TimeOfDay を返す (cross-service の provider)。"""
        return self._current
