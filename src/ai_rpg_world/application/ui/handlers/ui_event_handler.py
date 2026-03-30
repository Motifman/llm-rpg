"""Domain-event to UI-delta bridge."""

from __future__ import annotations

import logging
from typing import Any, Optional

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.ui.contracts.interfaces import IGameSceneEventBroker
from ai_rpg_world.application.ui.services.game_scene_projection import GameSceneProjection
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.player.event.status_events import PlayerLocationChangedEvent
from ai_rpg_world.domain.world.event.map_events import (
    GatewayTriggeredEvent,
    SpotWeatherChangedEvent,
    WorldObjectInteractedEvent,
    WorldObjectMovedEvent,
)
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository


class UiEventHandler(EventHandler[Any]):
    """Converts selected domain events into scene projection updates and delta events."""

    def __init__(
        self,
        projection: GameSceneProjection,
        broker: IGameSceneEventBroker,
        *,
        physical_map_repository: Optional[PhysicalMapRepository] = None,
    ) -> None:
        self._projection = projection
        self._broker = broker
        self._physical_map_repository = physical_map_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(self, event: Any) -> None:
        try:
            self._handle_impl(event)
        except ApplicationException:
            raise
        except Exception as exc:
            self._logger.exception(
                "Unexpected error in UiEventHandler",
                extra={"event_type": type(event).__name__},
            )
            raise SystemErrorException(
                f"UI event handling failed: {exc}",
                original_exception=exc,
            ) from exc

    def _handle_impl(self, event: Any) -> None:
        delta = None
        if isinstance(event, PlayerLocationChangedEvent):
            if event.old_spot_id is not None and int(event.old_spot_id) != int(event.new_spot_id):
                return
            delta = self._projection.apply_actor_moved(
                spot_id=int(event.new_spot_id),
                actor_id=int(event.aggregate_id),
                to_tile_x=event.new_coordinate.x,
                to_tile_y=event.new_coordinate.y,
                facing=self._derive_facing(event.old_coordinate, event.new_coordinate),
                actor_kind="player",
                display_name=f"Player {int(event.aggregate_id)}",
                sprite_key="player_default",
            )
        elif isinstance(event, WorldObjectMovedEvent):
            if self._physical_map_repository is None:
                return
            spot_id = self._physical_map_repository.find_spot_id_by_object_id(event.object_id)
            if spot_id is None:
                return
            physical_map = self._physical_map_repository.find_by_id(spot_id)
            moved_object = (
                physical_map.get_object(event.object_id) if physical_map is not None else None
            )
            if moved_object is None:
                return
            if moved_object.object_type.value == "NPC":
                delta = self._projection.apply_monster_moved(
                    spot_id=int(spot_id),
                    monster_id=int(event.object_id),
                    to_tile_x=event.to_coordinate.x,
                    to_tile_y=event.to_coordinate.y,
                    facing=self._derive_facing(event.from_coordinate, event.to_coordinate),
                    display_name="Slime",
                    sprite_key="monster_blob",
                )
            else:
                delta = self._projection.apply_actor_moved(
                    spot_id=int(spot_id),
                    actor_id=int(event.object_id),
                    to_tile_x=event.to_coordinate.x,
                    to_tile_y=event.to_coordinate.y,
                    facing=self._derive_facing(event.from_coordinate, event.to_coordinate),
                    actor_kind="world_object",
                    display_name=f"Object {int(event.object_id)}",
                    sprite_key="unknown_actor",
                )
        elif isinstance(event, WorldObjectInteractedEvent):
            if self._physical_map_repository is None:
                return
            spot_id = self._physical_map_repository.find_spot_id_by_object_id(event.target_id)
            if spot_id is None:
                return
            delta = self._projection.append_log(
                spot_id=int(spot_id),
                level="info",
                message=self._format_interaction_message(event),
                related_actor_id=int(event.actor_id),
            )
        elif isinstance(event, GatewayTriggeredEvent):
            deltas = self._projection.apply_scene_changed(
                actor_id=int(event.player_id_value or int(event.object_id)),
                from_spot_id=int(event.spot_id),
                to_spot_id=int(event.target_spot_id),
                landing_tile_x=event.landing_coordinate.x,
                landing_tile_y=event.landing_coordinate.y,
                auto_follow_switched=False,
            )
            for item in deltas:
                self._broker.publish(item)
            return
        elif isinstance(event, SpotWeatherChangedEvent):
            delta = self._projection.apply_weather_changed(
                spot_id=int(event.spot_id),
                weather_type=event.new_weather_state.weather_type.value,
                weather_intensity=float(event.new_weather_state.intensity),
                weather_overlay_key=self._resolve_weather_overlay_key(
                    event.new_weather_state.weather_type.value
                ),
            )

        if delta is not None:
            self._broker.publish(delta)

    @staticmethod
    def _derive_facing(old_coordinate: Any, new_coordinate: Any) -> str:
        if old_coordinate is None:
            return "down"
        dx = new_coordinate.x - old_coordinate.x
        dy = new_coordinate.y - old_coordinate.y
        if abs(dx) >= abs(dy):
            if dx > 0:
                return "right"
            if dx < 0:
                return "left"
        if dy > 0:
            return "down"
        if dy < 0:
            return "up"
        return "down"

    @staticmethod
    def _resolve_weather_overlay_key(weather_type: str) -> Optional[str]:
        mapping = {
            "RAIN": "rain_light",
            "HEAVY_RAIN": "rain_heavy",
            "FOG": "fog_morning",
            "SNOW": "snow_light",
            "BLIZZARD": "snow_blizzard",
            "STORM": "storm_dark",
        }
        return mapping.get(weather_type)

    @staticmethod
    def _format_interaction_message(event: WorldObjectInteractedEvent) -> str:
        if event.interaction_type.value == "open_chest":
            return "宝箱を開けました。" if bool((event.data or {}).get("is_open")) else "宝箱を閉じました。"
        return f"{event.interaction_type.value} を実行しました。"
