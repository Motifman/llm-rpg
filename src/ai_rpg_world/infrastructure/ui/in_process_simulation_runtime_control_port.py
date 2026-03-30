"""In-process runtime control port that advances shared simulation time."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from ai_rpg_world.application.ui.contracts.interfaces import (
    IGameSceneEventBroker,
    ISimulationRuntimeControlPort,
)
from ai_rpg_world.application.ui.services.game_scene_projection import GameSceneProjection
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)


class InProcessSimulationRuntimeControlPort(ISimulationRuntimeControlPort):
    """Background tick loop used by the web runtime."""

    def __init__(
        self,
        *,
        time_provider: InMemoryGameTimeProvider,
        projection: GameSceneProjection,
        broker: IGameSceneEventBroker,
        tick_interval_ms: int = 60,
        tick_advanced_callback: Optional[Callable[[int], None]] = None,
    ) -> None:
        if tick_interval_ms <= 0:
            raise ValueError("tick_interval_ms must be greater than 0")
        self._time_provider = time_provider
        self._projection = projection
        self._broker = broker
        self._tick_interval_ms = tick_interval_ms
        self._speed_multiplier = 1.0
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._state_changed = threading.Event()
        self._lock = threading.Lock()
        self._tick_advanced_callback = tick_advanced_callback

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._state_changed.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="ai-rpg-world-simulation-loop",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        self._state_changed.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)

    def pause(self) -> None:
        with self._lock:
            self._paused = True
        self._state_changed.set()

    def resume(self) -> None:
        with self._lock:
            self._paused = False
        self._state_changed.set()

    def set_speed_multiplier(self, speed_multiplier: float) -> None:
        with self._lock:
            self._speed_multiplier = float(speed_multiplier)
        self._state_changed.set()

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            with self._lock:
                paused = self._paused
                speed_multiplier = self._speed_multiplier
            if paused:
                self._state_changed.wait(timeout=0.25)
                self._state_changed.clear()
                continue

            wait_seconds = max(self._tick_interval_ms / 1000.0 / speed_multiplier, 0.01)
            interrupted = self._state_changed.wait(timeout=wait_seconds)
            self._state_changed.clear()
            if interrupted or self._stop_event.is_set():
                continue
            self._advance_once()

    def _advance_once(self) -> None:
        current_tick = self._time_provider.advance_tick().value
        server_time_ms = int(time.time() * 1000)
        for snapshot in self._projection.list_snapshots():
            self._projection.advance_simulation_tick(
                spot_id=snapshot.spot_id,
                current_tick=current_tick,
                server_time_ms=server_time_ms,
            )
        if self._tick_advanced_callback is not None:
            self._tick_advanced_callback(current_tick)


__all__ = ["InProcessSimulationRuntimeControlPort"]
