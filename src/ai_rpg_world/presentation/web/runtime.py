"""Composition root for the FastAPI visualization app backed by SQLite."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

from fastapi import FastAPI

from ai_rpg_world.application.ui.services.game_scene_projection import GameSceneProjection
from ai_rpg_world.application.ui.services.game_scene_projection_bootstrap_service import (
    GameSceneBootstrapConfig,
    GameSceneProjectionBootstrapService,
    SceneRenderCatalogEntry,
)
from ai_rpg_world.application.ui.services.game_scene_snapshot_service import (
    GameSceneSnapshotService,
)
from ai_rpg_world.application.ui.services.game_scene_stream_service import (
    GameSceneStreamService,
)
from ai_rpg_world.application.ui.services.manual_actor_control_service import (
    ManualActorControlService,
)
from ai_rpg_world.application.ui.services.manual_object_interaction_service import (
    ManualObjectInteractionService,
)
from ai_rpg_world.application.ui.services.simulation_control_service import (
    SimulationControlService,
)
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.infrastructure.di.container import SqliteGameDependencyInjectionContainer
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)
from ai_rpg_world.infrastructure.ui.in_memory_game_scene_event_broker import (
    InMemoryGameSceneEventBroker,
)
from ai_rpg_world.infrastructure.ui.in_process_simulation_runtime_control_port import (
    InProcessSimulationRuntimeControlPort,
)
from ai_rpg_world.infrastructure.ui.sqlite_demo_autonomous_world_port import (
    SqliteDemoAutonomousWorldPort,
)
from ai_rpg_world.infrastructure.ui.sqlite_manual_interaction_port import (
    SqliteManualInteractionPort,
)
from ai_rpg_world.infrastructure.ui.sqlite_manual_movement_port import (
    SqliteManualMovementPort,
)
from ai_rpg_world.presentation.game_control_api import GameControlApi
from ai_rpg_world.presentation.game_scene_api import GameSceneApi
from ai_rpg_world.presentation.web.app import create_web_app


@dataclass(frozen=True)
class SqliteWebAppConfig:
    database_path: Path
    manual_player_ids: tuple[int, ...] = ()
    cors_allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    scene_catalog: Mapping[int, SceneRenderCatalogEntry] = field(default_factory=dict)
    viewport_width: int = 960
    viewport_height: int = 540
    initial_tick: int = 0
    tick_interval_ms: int = 60


class SqliteWebRuntime:
    """Live runtime package for the web visualization backend."""

    def __init__(
        self,
        *,
        config: SqliteWebAppConfig,
        app: FastAPI,
        container: SqliteGameDependencyInjectionContainer,
        projection: GameSceneProjection,
        broker: InMemoryGameSceneEventBroker,
        time_provider: InMemoryGameTimeProvider,
        simulation_runtime_control: InProcessSimulationRuntimeControlPort,
    ) -> None:
        self.config = config
        self.app = app
        self.container = container
        self.projection = projection
        self.broker = broker
        self.time_provider = time_provider
        self.simulation_runtime_control = simulation_runtime_control

    def close(self) -> None:
        self.simulation_runtime_control.stop()
        self.container.close()


def create_sqlite_web_runtime(config: SqliteWebAppConfig) -> SqliteWebRuntime:
    container = SqliteGameDependencyInjectionContainer(config.database_path)
    world_state = container.get_world_state_repositories()

    projection = GameSceneProjection()
    bootstrap_service = GameSceneProjectionBootstrapService(
        spot_repository=world_state.world_structure.spots,
        physical_map_repository=world_state.world_runtime.physical_maps,
        player_profile_repository=world_state.player_state.player_profiles,
        config=GameSceneBootstrapConfig(
            scene_catalog=config.scene_catalog,
            viewport_width=config.viewport_width,
            viewport_height=config.viewport_height,
            initial_tick=config.initial_tick,
            manual_player_ids=frozenset(config.manual_player_ids),
        ),
    )
    for snapshot in bootstrap_service.build_initial_snapshots():
        projection.upsert_snapshot(snapshot)

    broker = InMemoryGameSceneEventBroker()
    time_provider = InMemoryGameTimeProvider(initial_tick=config.initial_tick)

    movement_port = SqliteManualMovementPort(
        database=config.database_path,
        projection=projection,
        broker=broker,
        time_provider=time_provider,
        bootstrap_config=GameSceneBootstrapConfig(
            scene_catalog=config.scene_catalog,
            viewport_width=config.viewport_width,
            viewport_height=config.viewport_height,
            initial_tick=config.initial_tick,
            manual_player_ids=frozenset(config.manual_player_ids),
        ),
    )
    interaction_port = SqliteManualInteractionPort(
        database=config.database_path,
        current_tick_provider=time_provider,
        projection=projection,
        broker=broker,
        bootstrap_config=GameSceneBootstrapConfig(
            scene_catalog=config.scene_catalog,
            viewport_width=config.viewport_width,
            viewport_height=config.viewport_height,
            initial_tick=config.initial_tick,
            manual_player_ids=frozenset(config.manual_player_ids),
        ),
    )
    demo_automation_port = SqliteDemoAutonomousWorldPort(
        database=config.database_path,
        projection=projection,
        broker=broker,
        bootstrap_config=GameSceneBootstrapConfig(
            scene_catalog=config.scene_catalog,
            viewport_width=config.viewport_width,
            viewport_height=config.viewport_height,
            initial_tick=config.initial_tick,
            manual_player_ids=frozenset(config.manual_player_ids),
        ),
        patrol_route=(
            Coordinate(7, 7, 0),
            Coordinate(7, 6, 0),
            Coordinate(6, 6, 0),
            Coordinate(6, 7, 0),
        ),
        move_every_ticks=10,
    )
    simulation_runtime_control = InProcessSimulationRuntimeControlPort(
        time_provider=time_provider,
        projection=projection,
        broker=broker,
        tick_interval_ms=config.tick_interval_ms,
        tick_advanced_callback=demo_automation_port.advance_tick,
    )
    simulation_control = SimulationControlService(
        projection,
        broker,
        runtime_control=simulation_runtime_control,
    )
    manual_control = ManualActorControlService(
        movement_port,
        projection,
        manual_player_ids=config.manual_player_ids,
    )
    object_interaction = ManualObjectInteractionService(
        interaction_port,
        manual_player_ids=config.manual_player_ids,
    )
    scene_api = GameSceneApi(
        GameSceneSnapshotService(projection),
        GameSceneStreamService(broker),
    )
    control_api = GameControlApi(simulation_control, manual_control, object_interaction)
    runtime_holder: dict[str, SqliteWebRuntime] = {}

    @asynccontextmanager
    async def _lifespan(_: FastAPI):
        try:
            runtime_holder["runtime"].simulation_runtime_control.start()
            yield
        finally:
            runtime_holder["runtime"].close()

    app = create_web_app(
        scene_api=scene_api,
        control_api=control_api,
        lifespan=_lifespan,
        cors_allowed_origins=config.cors_allowed_origins,
    )

    runtime = SqliteWebRuntime(
        config=config,
        app=app,
        container=container,
        projection=projection,
        broker=broker,
        time_provider=time_provider,
        simulation_runtime_control=simulation_runtime_control,
    )
    runtime_holder["runtime"] = runtime
    app.state.sqlite_web_runtime = runtime

    return runtime


def create_sqlite_web_app(config: SqliteWebAppConfig) -> FastAPI:
    return create_sqlite_web_runtime(config).app


def create_sqlite_web_app_from_env() -> FastAPI:
    database_path = Path(
        os.getenv("AI_RPG_WORLD_GAME_DB", "./var/game/ai_rpg_world.db")
    ).expanduser()
    manual_player_ids = tuple(
        int(raw)
        for raw in os.getenv("AI_RPG_WORLD_MANUAL_PLAYER_IDS", "").split(",")
        if raw.strip()
    )
    cors_allowed_origins = tuple(
        raw.strip()
        for raw in os.getenv(
            "AI_RPG_WORLD_CORS_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173",
        ).split(",")
        if raw.strip()
    )
    return create_sqlite_web_app(
        SqliteWebAppConfig(
            database_path=database_path,
            manual_player_ids=manual_player_ids,
            cors_allowed_origins=cors_allowed_origins,
            tick_interval_ms=int(os.getenv("AI_RPG_WORLD_TICK_INTERVAL_MS", "60")),
        )
    )


__all__ = [
    "SqliteWebAppConfig",
    "SqliteWebRuntime",
    "create_sqlite_web_app",
    "create_sqlite_web_app_from_env",
    "create_sqlite_web_runtime",
]
