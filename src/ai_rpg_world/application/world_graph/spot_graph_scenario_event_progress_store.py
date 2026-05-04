from __future__ import annotations

from typing import FrozenSet


class InMemorySpotGraphScenarioEventProgressStore:
    """発火済みシナリオイベント ID とスケジュールを保持するインメモリストア。"""

    def __init__(self) -> None:
        self._fired_event_ids: set[str] = set()
        self._scheduled: dict[str, int] = {}  # event_id -> fire_at_tick

    def is_fired(self, event_id: str) -> bool:
        return event_id in self._fired_event_ids

    def mark_fired(self, event_id: str) -> None:
        self._fired_event_ids.add(event_id)

    def as_frozen_set(self) -> FrozenSet[str]:
        return frozenset(self._fired_event_ids)

    def schedule(self, event_id: str, fire_at_tick: int) -> None:
        """イベントを指定tickで発火するようスケジュールする。"""
        self._scheduled[event_id] = fire_at_tick

    def due_event_ids(self, current_tick: int) -> list[str]:
        """current_tick 以降に発火すべきスケジュール済みイベントIDを返す。"""
        return [eid for eid, t in self._scheduled.items() if current_tick >= t]

    def unschedule(self, event_id: str) -> None:
        """スケジュールを解除する。"""
        self._scheduled.pop(event_id, None)

    def is_scheduled(self, event_id: str) -> bool:
        """イベントがスケジュール済みかどうか。"""
        return event_id in self._scheduled

    def all_scheduled_event_ids(self) -> frozenset[str]:
        """スケジュール済みの全イベントIDを返す。"""
        return frozenset(self._scheduled.keys())
