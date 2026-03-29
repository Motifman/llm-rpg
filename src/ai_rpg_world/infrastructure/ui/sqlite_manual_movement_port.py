"""SQLite-backed manual movement port for web-driven tile stepping."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Union

from ai_rpg_world.application.ui.contracts.interfaces import IGameSceneEventBroker
from ai_rpg_world.application.ui.handlers.ui_event_handler import UiEventHandler
from ai_rpg_world.application.ui.services.game_scene_projection_bootstrap_service import (
    GameSceneBootstrapConfig,
    GameSceneProjectionBootstrapService,
)
from ai_rpg_world.application.ui.services.game_scene_projection import GameSceneProjection
from ai_rpg_world.application.world.movement_wiring import (
    create_movement_application_service,
)
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.service.global_pathfinding_service import (
    GlobalPathfindingService,
)
from ai_rpg_world.domain.world.service.movement_config_service import (
    DefaultMovementConfigService,
)
from ai_rpg_world.infrastructure.events.event_handler_composition import (
    EventHandlerComposition,
)
from ai_rpg_world.infrastructure.events.event_handler_profile import EventHandlerProfile
from ai_rpg_world.infrastructure.events.ui_event_handler_registry import (
    UiEventHandlerRegistry,
)
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_transactional_scope_factory import (
    create_sqlite_scope_with_event_publisher,
)
from ai_rpg_world.infrastructure.world.pathfinding.astar_pathfinding_strategy import (
    AStarPathfindingStrategy,
)
from ai_rpg_world.application.world.services.gateway_based_connected_spots_provider import (
    GatewayBasedConnectedSpotsProvider,
)
from ai_rpg_world.application.world.contracts.commands import MoveTileCommand
from ai_rpg_world.application.world.handlers.gateway_handler import (
    GatewayTriggeredEventHandler,
)
from ai_rpg_world.application.world.world_state_sqlite_wiring import (
    attach_world_state_sqlite_repositories,
)
from ai_rpg_world.domain.world.service.map_transition_service import (
    MapTransitionService,
)


class SqliteManualMovementPort:
    """Builds a real movement service per request against the SQLite game DB."""

    def __init__(
        self,
        *,
        database: Union[str, Path],
        projection: GameSceneProjection,
        broker: IGameSceneEventBroker,
        time_provider: InMemoryGameTimeProvider,
        bootstrap_config: GameSceneBootstrapConfig | None = None,
    ) -> None:
        self._database = str(Path(database).expanduser().resolve())
        self._projection = projection
        self._broker = broker
        self._time_provider = time_provider
        self._bootstrap_config = bootstrap_config or GameSceneBootstrapConfig()

    def move_tile(self, command: MoveTileCommand):
        connection = sqlite3.connect(self._database)
        connection.row_factory = sqlite3.Row
        try:
            scope, event_publisher = create_sqlite_scope_with_event_publisher(
                connection=connection
            )
            world_state = attach_world_state_sqlite_repositories(
                connection,
                event_sink=scope,
            )

            ui_handler = UiEventHandler(
                self._projection,
                self._broker,
                physical_map_repository=world_state.world_runtime.physical_maps,
            )
            ui_registry = UiEventHandlerRegistry(ui_handler)
            gateway_handler = GatewayTriggeredEventHandler(
                physical_map_repository=world_state.world_runtime.physical_maps,
                player_status_repository=world_state.player_state.player_statuses,
                monster_repository=world_state.world_runtime.monsters,
                map_transition_service=MapTransitionService(),
                unit_of_work=scope,
                event_publisher=event_publisher,
            )
            EventHandlerComposition(
                gateway_handler=gateway_handler,
                ui_registry=ui_registry,
            ).register_for_profile(
                event_publisher,
                EventHandlerProfile.FULL,
            )

            movement_service = create_movement_application_service(
                player_status_repository=world_state.player_state.player_statuses,
                player_profile_repository=world_state.player_state.player_profiles,
                physical_map_repository=world_state.world_runtime.physical_maps,
                spot_repository=world_state.world_structure.spots,
                connected_spots_provider=GatewayBasedConnectedSpotsProvider(
                    world_state.world_runtime.physical_maps
                ),
                global_pathfinding_service=GlobalPathfindingService(
                    PathfindingService(AStarPathfindingStrategy())
                ),
                movement_config_service=DefaultMovementConfigService(),
                time_provider=self._time_provider,
                unit_of_work=scope,
            )
            result = movement_service.move_tile(command)
            bootstrap_service = GameSceneProjectionBootstrapService(
                spot_repository=world_state.world_structure.spots,
                physical_map_repository=world_state.world_runtime.physical_maps,
                player_profile_repository=world_state.player_state.player_profiles,
                config=self._bootstrap_config,
            )
            for snapshot in bootstrap_service.build_initial_snapshots():
                self._projection.synchronize_snapshot(snapshot)
            return result
        finally:
            connection.close()


__all__ = ["SqliteManualMovementPort"]
