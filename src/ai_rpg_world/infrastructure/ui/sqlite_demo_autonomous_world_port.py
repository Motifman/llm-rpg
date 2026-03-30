"""SQLite-backed deterministic demo monster automation."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Iterable, Union

from ai_rpg_world.application.ui.handlers.ui_event_handler import UiEventHandler
from ai_rpg_world.application.ui.services.game_scene_projection import GameSceneProjection
from ai_rpg_world.application.ui.services.game_scene_projection_bootstrap_service import (
    GameSceneBootstrapConfig,
    GameSceneProjectionBootstrapService,
)
from ai_rpg_world.application.world.world_state_sqlite_wiring import (
    attach_world_state_sqlite_repositories,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.events.event_handler_composition import (
    EventHandlerComposition,
)
from ai_rpg_world.infrastructure.events.event_handler_profile import EventHandlerProfile
from ai_rpg_world.infrastructure.events.ui_event_handler_registry import (
    UiEventHandlerRegistry,
)
from ai_rpg_world.infrastructure.ui.in_memory_game_scene_event_broker import (
    InMemoryGameSceneEventBroker,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_transactional_scope_factory import (
    create_sqlite_scope_with_event_publisher,
)


class SqliteDemoAutonomousWorldPort:
    def __init__(
        self,
        *,
        database: Union[str, Path],
        projection: GameSceneProjection,
        broker: InMemoryGameSceneEventBroker,
        bootstrap_config: GameSceneBootstrapConfig,
        patrol_route: Iterable[Coordinate],
        monster_object_id: int = 20_001,
        move_every_ticks: int = 8,
    ) -> None:
        self._database = str(Path(database).expanduser().resolve())
        self._projection = projection
        self._broker = broker
        self._bootstrap_config = bootstrap_config
        self._patrol_route = list(patrol_route)
        self._monster_object_id = monster_object_id
        self._move_every_ticks = move_every_ticks
        self._route_index = 0
        self._logger = logging.getLogger(self.__class__.__name__)

    def advance_tick(self, current_tick: int) -> None:
        if not self._patrol_route or current_tick % self._move_every_ticks != 0:
            return

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
            physical_map = world_state.world_runtime.physical_maps.find_by_id(SpotId(1))
            if physical_map is None:
                return
            monster = physical_map.get_object(WorldObjectId(self._monster_object_id))
            if monster.is_busy(WorldTick(current_tick)):
                return

            self._route_index = (self._route_index + 1) % len(self._patrol_route)
            next_coordinate = self._patrol_route[self._route_index]
            ui_handler = UiEventHandler(
                self._projection,
                self._broker,
                physical_map_repository=world_state.world_runtime.physical_maps,
            )
            ui_registry = UiEventHandlerRegistry(ui_handler)
            EventHandlerComposition(ui_registry=ui_registry).register_for_profile(
                event_publisher,
                EventHandlerProfile.FULL,
            )
            with scope:
                physical_map.move_object(
                    WorldObjectId(self._monster_object_id),
                    next_coordinate,
                    WorldTick(current_tick),
                    monster.capability,
                )
                world_state.world_runtime.physical_maps.save(physical_map)
            bootstrap_service = GameSceneProjectionBootstrapService(
                spot_repository=world_state.world_structure.spots,
                physical_map_repository=world_state.world_runtime.physical_maps,
                player_profile_repository=world_state.player_state.player_profiles,
                config=self._bootstrap_config,
            )
            for snapshot in bootstrap_service.build_initial_snapshots():
                self._projection.synchronize_snapshot(snapshot)
        except Exception:
            self._logger.exception(
                "Demo monster automation tick failed",
                extra={"current_tick": current_tick},
            )
            return
        finally:
            connection.close()
