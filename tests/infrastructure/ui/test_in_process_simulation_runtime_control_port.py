"""Tests for the in-process simulation runtime control port."""

from __future__ import annotations

import threading
import time

import pytest

from ai_rpg_world.application.ui.contracts.dtos import (
    GameSceneSnapshotDto,
    SceneActorDto,
    SceneCameraDto,
    SceneMapDto,
    SimulationStateDto,
)
from ai_rpg_world.application.ui.services.game_scene_projection import GameSceneProjection
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)
from ai_rpg_world.infrastructure.ui.in_memory_game_scene_event_broker import (
    InMemoryGameSceneEventBroker,
)
import ai_rpg_world.infrastructure.ui.in_process_simulation_runtime_control_port as runtime_control_port_module
from ai_rpg_world.infrastructure.ui.in_process_simulation_runtime_control_port import (
    InProcessSimulationRuntimeControlPort,
)


def _make_snapshot(spot_id: int = 1) -> GameSceneSnapshotDto:
    return GameSceneSnapshotDto(
        scene_id=f"spot-{spot_id}",
        spot_id=spot_id,
        spot_name=f"Spot {spot_id}",
        map=SceneMapDto(
            map_asset_key=f"spot_{spot_id}",
            tiled_map_path=f"maps/{spot_id}.json",
            tile_width=32,
            tile_height=32,
            map_width_tiles=4,
            map_height_tiles=4,
            collision_layer_name="collision",
            tileset_keys=["terrain"],
        ),
        camera=SceneCameraDto(
            mode="fixed",
            tracked_actor_id=None,
            viewport_width=640,
            viewport_height=480,
        ),
        simulation=SimulationStateDto(
            is_paused=False,
            speed_multiplier=1.0,
            current_tick=10,
        ),
        actors=[
            SceneActorDto(
                actor_id=1,
                player_id=1,
                display_name="Hero",
                actor_kind="player",
                tile_x=0,
                tile_y=0,
                facing="right",
                sprite_key="player_default",
                state="walking",
                busy_until_tick=12,
            )
        ],
        scene_version=0,
        server_time_ms=0,
    )


def test_runtime_control_port_advances_tick_and_publishes_deltas():
    projection = GameSceneProjection()
    projection.upsert_snapshot(_make_snapshot())
    broker = InMemoryGameSceneEventBroker()
    time_provider = InMemoryGameTimeProvider(initial_tick=10)
    runtime = InProcessSimulationRuntimeControlPort(
        time_provider=time_provider,
        projection=projection,
        broker=broker,
        tick_interval_ms=20,
    )

    runtime.start()
    try:
        time.sleep(0.09)
    finally:
        runtime.stop()

    snapshot = projection.get_snapshot(1)
    assert snapshot.simulation.current_tick >= 13
    assert snapshot.actors[0].state == "idle"
    assert broker.get_published_events() == []


def test_runtime_control_port_pause_and_resume_toggle_tick_progression():
    projection = GameSceneProjection()
    projection.upsert_snapshot(_make_snapshot())
    broker = InMemoryGameSceneEventBroker()
    time_provider = InMemoryGameTimeProvider(initial_tick=10)
    runtime = InProcessSimulationRuntimeControlPort(
        time_provider=time_provider,
        projection=projection,
        broker=broker,
        tick_interval_ms=20,
    )

    runtime.start()
    try:
        time.sleep(0.05)
        runtime.pause()
        paused_tick = time_provider.get_current_tick().value
        time.sleep(0.06)
        assert time_provider.get_current_tick().value == paused_tick
        runtime.resume()
        resumed = False
        for _ in range(10):
            time.sleep(0.03)
            if time_provider.get_current_tick().value > paused_tick:
                resumed = True
                break
        assert resumed is True
    finally:
        runtime.stop()


def test_runtime_control_port_pause_waits_until_loop_observes_paused_state():
    """pause() は進行中 tick の完了後にループが停止を観測してから返る。"""
    projection = GameSceneProjection()
    projection.upsert_snapshot(_make_snapshot())
    broker = InMemoryGameSceneEventBroker()
    time_provider = InMemoryGameTimeProvider(initial_tick=10)
    tick_callback_entered = threading.Event()
    release_tick_callback = threading.Event()
    pause_returned = threading.Event()

    def _block_first_tick(current_tick: int) -> None:
        if current_tick == 11:
            tick_callback_entered.set()
            release_tick_callback.wait(timeout=2.0)

    runtime = InProcessSimulationRuntimeControlPort(
        time_provider=time_provider,
        projection=projection,
        broker=broker,
        tick_interval_ms=10,
        tick_advanced_callback=_block_first_tick,
    )

    runtime.start()
    try:
        assert tick_callback_entered.wait(timeout=1.0)
        pause_thread = threading.Thread(
            target=lambda: (runtime.pause(), pause_returned.set())
        )
        pause_thread.start()

        time.sleep(0.03)
        assert not pause_returned.is_set()

        release_tick_callback.set()
        pause_thread.join(timeout=1.0)
        assert pause_returned.is_set()
        paused_tick = time_provider.get_current_tick().value

        time.sleep(0.05)
        assert time_provider.get_current_tick().value == paused_tick
    finally:
        release_tick_callback.set()
        runtime.stop()


def test_runtime_control_port_pause_times_out_when_tick_loop_is_stuck(monkeypatch):
    """tick 中に固まった場合、pause() は無限待ちせず明示的に失敗する。"""
    monkeypatch.setattr(
        runtime_control_port_module,
        "_PAUSE_OBSERVED_TIMEOUT_SECONDS",
        0.05,
    )
    projection = GameSceneProjection()
    projection.upsert_snapshot(_make_snapshot())
    broker = InMemoryGameSceneEventBroker()
    time_provider = InMemoryGameTimeProvider(initial_tick=10)
    tick_callback_entered = threading.Event()
    release_tick_callback = threading.Event()

    def _block_first_tick(current_tick: int) -> None:
        if current_tick == 11:
            tick_callback_entered.set()
            release_tick_callback.wait(timeout=2.0)

    runtime = InProcessSimulationRuntimeControlPort(
        time_provider=time_provider,
        projection=projection,
        broker=broker,
        tick_interval_ms=10,
        tick_advanced_callback=_block_first_tick,
    )

    runtime.start()
    try:
        assert tick_callback_entered.wait(timeout=1.0)

        with pytest.raises(TimeoutError, match="did not observe pause state"):
            runtime.pause()
    finally:
        release_tick_callback.set()
        runtime.stop()


def test_runtime_control_port_speed_multiplier_changes_tick_rate():
    projection = GameSceneProjection()
    projection.upsert_snapshot(_make_snapshot())
    broker = InMemoryGameSceneEventBroker()
    time_provider = InMemoryGameTimeProvider(initial_tick=10)
    runtime = InProcessSimulationRuntimeControlPort(
        time_provider=time_provider,
        projection=projection,
        broker=broker,
        tick_interval_ms=25,
    )

    runtime.start()
    try:
        time.sleep(0.08)
        base_tick = time_provider.get_current_tick().value
        runtime.set_speed_multiplier(3.0)
        time.sleep(0.08)
        faster_tick = time_provider.get_current_tick().value
    finally:
        runtime.stop()

    assert faster_tick - base_tick >= 4
