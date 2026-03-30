"""SQLite-backed manual interaction port for scene objects."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Union

from ai_rpg_world.application.ui.contracts.dtos import InteractSceneObjectResultDto
from ai_rpg_world.application.ui.contracts.interfaces import IGameSceneEventBroker
from ai_rpg_world.application.ui.handlers.ui_event_handler import UiEventHandler
from ai_rpg_world.application.ui.services.game_scene_projection import GameSceneProjection
from ai_rpg_world.application.ui.services.game_scene_projection_bootstrap_service import (
    GameSceneBootstrapConfig,
    GameSceneProjectionBootstrapService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.events.event_handler_composition import (
    EventHandlerComposition,
)
from ai_rpg_world.infrastructure.events.event_handler_profile import EventHandlerProfile
from ai_rpg_world.infrastructure.events.ui_event_handler_registry import (
    UiEventHandlerRegistry,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_transactional_scope_factory import (
    create_sqlite_scope_with_event_publisher,
)
from ai_rpg_world.application.world.world_state_sqlite_wiring import (
    attach_world_state_sqlite_repositories,
)
from ai_rpg_world.domain.world.exception.map_exception import ObjectNotFoundException


class SqliteManualInteractionPort:
    def __init__(
        self,
        *,
        database: Union[str, Path],
        current_tick_provider,
        projection: GameSceneProjection,
        broker: IGameSceneEventBroker,
        bootstrap_config: GameSceneBootstrapConfig | None = None,
    ) -> None:
        self._database = str(Path(database).expanduser().resolve())
        self._current_tick_provider = current_tick_provider
        self._projection = projection
        self._broker = broker
        self._bootstrap_config = bootstrap_config or GameSceneBootstrapConfig()

    def interact(self, *, actor_id: int, target_object_id: int) -> InteractSceneObjectResultDto:
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
            EventHandlerComposition(ui_registry=ui_registry).register_for_profile(
                event_publisher,
                EventHandlerProfile.FULL,
            )
            player_status = world_state.player_state.player_statuses.find_by_id(actor_id)
            if player_status is None:
                raise ValueError(f"Player {actor_id} not found")
            if player_status.current_spot_id is None:
                raise ValueError(f"Player {actor_id} is not placed on any spot")
            spot_id = int(player_status.current_spot_id)
            physical_map = world_state.world_runtime.physical_maps.find_by_id(spot_id)
            if physical_map is None:
                raise ValueError(f"Physical map not found for spot {spot_id}")

            current_tick = WorldTick(self._current_tick_provider.get_current_tick().value)
            actor = physical_map.get_actor(WorldObjectId(actor_id))
            target = physical_map.get_object(WorldObjectId(target_object_id))
            if actor is None:
                raise ObjectNotFoundException(f"Actor {actor_id} not found")
            if target is None:
                raise ObjectNotFoundException(f"Target {target_object_id} not found")
            distance = actor.coordinate.chebyshev_distance_to(target.coordinate)
            if distance == 1:
                actor.turn(actor.coordinate.direction_to(target.coordinate))
            with scope:
                physical_map.interact_with(
                    WorldObjectId(actor_id),
                    WorldObjectId(target_object_id),
                    current_tick,
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
            self._projection.update_object_state(
                spot_id=spot_id,
                object_id=target_object_id,
                interaction_data=dict(target.interaction_data),
                sprite_key=(
                    "object_chest_open"
                    if bool(target.interaction_data.get("is_open"))
                    else "object_chest_closed"
                ),
            )
            return InteractSceneObjectResultDto(
                success=True,
                actor_id=actor_id,
                target_object_id=target_object_id,
                spot_id=spot_id,
                interaction_type=(
                    target.interaction_type.value if target.interaction_type is not None else "interact"
                ),
                message="インタラクションを実行しました。",
                object_state=dict(target.interaction_data),
            )
        finally:
            connection.close()
