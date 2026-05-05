"""昼夜サイクル定義（値オブジェクト）。

シナリオデータから受け取るフェーズ列と1日のtick数を保持し、
任意の WorldTick から TimeOfDay を計算する純粋関数を提供する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world_graph.value_object.day_night_phase_def import (
    DayNightPhaseDef,
)
from ai_rpg_world.domain.world_graph.value_object.time_of_day import TimeOfDay


@dataclass(frozen=True)
class DayNightCycleDef:
    """1日の長さとフェーズ列を持つ昼夜サイクル定義。

    Attributes:
        ticks_per_day: 1日に相当する tick 数（>= 1）。
        starting_tick_in_day: 開始時に初日内のどの tick から始めるか [0, ticks_per_day)。
            シナリオを「正午スタート」させたい場合などに用いる。
        phases: フェーズ列。start_ratio 昇順でソート済み・最初のフェーズは
            start_ratio==0.0 であること。フェーズは少なくとも1つ必要。
    """

    ticks_per_day: int
    starting_tick_in_day: int
    phases: Tuple[DayNightPhaseDef, ...]

    def __post_init__(self) -> None:
        if self.ticks_per_day < 1:
            raise ValueError(
                f"DayNightCycleDef.ticks_per_day must be >= 1: {self.ticks_per_day}"
            )
        if not 0 <= self.starting_tick_in_day < self.ticks_per_day:
            raise ValueError(
                "DayNightCycleDef.starting_tick_in_day must be in "
                f"[0, ticks_per_day): {self.starting_tick_in_day}"
            )
        if not self.phases:
            raise ValueError("DayNightCycleDef.phases must not be empty")
        if self.phases[0].start_ratio != 0.0:
            raise ValueError(
                "DayNightCycleDef.phases[0].start_ratio must be 0.0; "
                f"got {self.phases[0].start_ratio}"
            )
        names_seen: set = set()
        prev_ratio = -1.0
        for p in self.phases:
            if p.name in names_seen:
                raise ValueError(f"Duplicate phase name in DayNightCycleDef: {p.name}")
            names_seen.add(p.name)
            if p.start_ratio <= prev_ratio:
                raise ValueError(
                    "DayNightCycleDef.phases must be sorted by start_ratio strictly ascending"
                )
            prev_ratio = p.start_ratio

    def time_of_day_at(self, current_tick: WorldTick) -> TimeOfDay:
        """指定 tick における TimeOfDay を計算する。"""
        offset_tick = (current_tick.value + self.starting_tick_in_day) % self.ticks_per_day
        ratio = offset_tick / self.ticks_per_day
        phase = self._phase_for_ratio(ratio)
        return TimeOfDay(
            ratio=ratio,
            phase_name=phase.name,
            display_text=phase.display_text,
            ambient_light=phase.ambient_light,
            is_dark=phase.is_dark,
        )

    def _phase_for_ratio(self, ratio: float) -> DayNightPhaseDef:
        """ratio が属するフェーズを返す（線形探索。フェーズ数は通常少数）。"""
        chosen = self.phases[0]
        for p in self.phases:
            if p.start_ratio <= ratio:
                chosen = p
            else:
                break
        return chosen
