"""In-memory broker for UI delta events."""

from __future__ import annotations

import threading
from collections import deque
from typing import Deque, List, Optional

from ai_rpg_world.application.ui.contracts.dtos import GameSceneDeltaEventDto
from ai_rpg_world.application.ui.contracts.interfaces import IGameSceneEventBroker


# 長走 (140+ tick × 複数 agent) で _events が無限に肥える地雷を防ぐ。
# consumer (GameSceneStreamService) は scene_version カーソル方式で filter
# するだけで「消費した」signal を返さないため、broker 側で履歴を保持し続
# けると永久に膨らんでいた。
# 5000 件あれば WebSocket クライアントが切れて再接続するまでの差分は十分
# 賄える。それ以上は古い差分を諦めて完全 snapshot で復元する設計とする。
_MAX_EVENTS = 5_000


class InMemoryGameSceneEventBroker(IGameSceneEventBroker):
    def __init__(self) -> None:
        self._events: Deque[GameSceneDeltaEventDto] = deque(maxlen=_MAX_EVENTS)
        self._lock = threading.Lock()

    def publish(self, event: GameSceneDeltaEventDto) -> None:
        if not isinstance(event, GameSceneDeltaEventDto):
            raise TypeError("event must be GameSceneDeltaEventDto")
        with self._lock:
            self._events.append(event)

    def get_published_events(
        self, *, scene_id: Optional[str] = None
    ) -> List[GameSceneDeltaEventDto]:
        with self._lock:
            if scene_id is None:
                return list(self._events)
            return [event for event in self._events if event.scene_id == scene_id]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
