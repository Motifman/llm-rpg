"""Bootstrap scene projection snapshots from live repositories."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Optional

from ai_rpg_world.application.ui.contracts.dtos import (
    GameSceneSnapshotDto,
    SceneActorDto,
    SceneAreaDto,
    SceneCameraDto,
    SceneGatewayDto,
    SceneLogEntryDto,
    SceneMapDto,
    ScenePointDto,
    SceneWeatherDto,
    SimulationStateDto,
)
from ai_rpg_world.domain.player.repository.player_profile_repository import (
    PlayerProfileRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.entity.gateway import Gateway
from ai_rpg_world.domain.world.entity.location_area import LocationArea
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)
from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
from ai_rpg_world.domain.world.value_object.area import CircleArea, PointArea, RectArea
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


@dataclass(frozen=True)
class SceneRenderCatalogEntry:
    tiled_map_path: str
    map_asset_key: str
    collision_layer_name: str = "collision"
    tileset_keys: tuple[str, ...] = ()
    tile_width: int = 32
    tile_height: int = 32


@dataclass(frozen=True)
class GameSceneBootstrapConfig:
    scene_catalog: Mapping[int, SceneRenderCatalogEntry] = field(default_factory=dict)
    viewport_width: int = 960
    viewport_height: int = 540
    initial_tick: int = 0
    manual_player_ids: frozenset[int] = field(default_factory=frozenset)
    actor_sprite_key_resolver: Optional[Callable[[WorldObject], str]] = None
    weather_overlay_key_resolver: Optional[Callable[[str], Optional[str]]] = None


class GameSceneProjectionBootstrapService:
    """Builds initial UI snapshots from persisted world state."""

    def __init__(
        self,
        *,
        spot_repository: SpotRepository,
        physical_map_repository: PhysicalMapRepository,
        player_profile_repository: PlayerProfileRepository,
        config: Optional[GameSceneBootstrapConfig] = None,
    ) -> None:
        self._spot_repository = spot_repository
        self._physical_map_repository = physical_map_repository
        self._player_profile_repository = player_profile_repository
        self._config = config or GameSceneBootstrapConfig()

    def build_initial_snapshots(self) -> list[GameSceneSnapshotDto]:
        spot_index = {
            int(spot.spot_id): spot for spot in self._spot_repository.find_all()
        }
        snapshots: list[GameSceneSnapshotDto] = []
        for physical_map in self._physical_map_repository.find_all():
            spot_id = int(physical_map.spot_id)
            spot = spot_index.get(spot_id)
            snapshots.append(
                GameSceneSnapshotDto(
                    scene_id=f"spot-{spot_id}",
                    spot_id=spot_id,
                    spot_name=spot.name if spot is not None else f"Spot {spot_id}",
                    map=self._build_map_dto(spot_id, physical_map.get_all_tiles()),
                    camera=SceneCameraDto(
                        mode="fixed",
                        tracked_actor_id=None,
                        viewport_width=self._config.viewport_width,
                        viewport_height=self._config.viewport_height,
                    ),
                    simulation=SimulationStateDto(
                        is_paused=False,
                        speed_multiplier=1.0,
                        current_tick=self._config.initial_tick,
                    ),
                    actors=self._build_actor_dtos(physical_map.get_all_objects()),
                    weather=SceneWeatherDto(
                        weather_type=physical_map.weather_state.weather_type.value,
                        weather_intensity=float(physical_map.weather_state.intensity),
                        weather_overlay_key=self._resolve_weather_overlay_key(
                            physical_map.weather_state.weather_type.value
                        ),
                    ),
                    gateways=self._build_gateway_dtos(physical_map.get_all_gateways(), spot_index),
                    areas=self._build_area_dtos(physical_map.get_all_location_areas()),
                    ui_logs=[
                        SceneLogEntryDto(
                            level="info",
                            message="Scene initialized from SQLite state.",
                        )
                    ],
                    scene_version=0,
                    server_time_ms=0,
                )
            )
        return sorted(snapshots, key=lambda snapshot: snapshot.spot_id)

    def _build_map_dto(self, spot_id: int, tiles: Iterable) -> SceneMapDto:
        catalog_entry = self._config.scene_catalog.get(spot_id)
        tile_list = list(tiles)
        if tile_list:
            map_width_tiles = max(tile.coordinate.x for tile in tile_list) + 1
            map_height_tiles = max(tile.coordinate.y for tile in tile_list) + 1
        else:
            map_width_tiles = 0
            map_height_tiles = 0
        return SceneMapDto(
            map_asset_key=(
                catalog_entry.map_asset_key if catalog_entry is not None else f"spot_{spot_id}"
            ),
            tiled_map_path=(
                catalog_entry.tiled_map_path
                if catalog_entry is not None
                else f"data/maps/spot_{spot_id}.json"
            ),
            tile_width=catalog_entry.tile_width if catalog_entry is not None else 32,
            tile_height=catalog_entry.tile_height if catalog_entry is not None else 32,
            map_width_tiles=map_width_tiles,
            map_height_tiles=map_height_tiles,
            collision_layer_name=(
                catalog_entry.collision_layer_name
                if catalog_entry is not None
                else "collision"
            ),
            tileset_keys=list(catalog_entry.tileset_keys) if catalog_entry is not None else [],
        )

    def _build_actor_dtos(self, objects: Iterable[WorldObject]) -> list[SceneActorDto]:
        actors: list[SceneActorDto] = []
        for obj in objects:
            if not obj.is_actor:
                continue
            player_id = int(obj.player_id) if obj.player_id is not None else None
            display_name = self._resolve_display_name(obj)
            actor_kind = self._resolve_actor_kind(obj)
            actors.append(
                SceneActorDto(
                    actor_id=int(obj.object_id),
                    player_id=player_id,
                    display_name=display_name,
                    actor_kind=actor_kind,
                    tile_x=obj.coordinate.x,
                    tile_y=obj.coordinate.y,
                    facing=(
                        obj.direction.name.lower() if obj.direction is not None else "down"
                    ),
                    sprite_key=self._resolve_sprite_key(obj),
                    is_manual_controlled=(
                        player_id is not None and player_id in self._config.manual_player_ids
                    ),
                    is_llm_controlled=(
                        player_id is not None and player_id not in self._config.manual_player_ids
                    ),
                    state="busy" if obj.busy_until is not None else "idle",
                    busy_until_tick=(
                        obj.busy_until.value if obj.busy_until is not None else None
                    ),
                )
            )
        return sorted(actors, key=lambda actor: actor.actor_id)

    def _build_gateway_dtos(
        self,
        gateways: Iterable[Gateway],
        spot_index: Mapping[int, object],
    ) -> list[SceneGatewayDto]:
        dtos: list[SceneGatewayDto] = []
        for gateway in gateways:
            reference = gateway.area.get_reference_coordinate()
            target_spot = spot_index.get(int(gateway.target_spot_id))
            dtos.append(
                SceneGatewayDto(
                    gateway_id=int(gateway.gateway_id),
                    tile_x=reference.x,
                    tile_y=reference.y,
                    target_spot_id=int(gateway.target_spot_id),
                    target_spot_name=(
                        target_spot.name
                        if target_spot is not None and hasattr(target_spot, "name")
                        else f"Spot {int(gateway.target_spot_id)}"
                    ),
                    landing_tile_x=gateway.landing_coordinate.x,
                    landing_tile_y=gateway.landing_coordinate.y,
                )
            )
        return sorted(dtos, key=lambda gateway: gateway.gateway_id)

    def _build_area_dtos(self, areas: Iterable[LocationArea]) -> list[SceneAreaDto]:
        dtos: list[SceneAreaDto] = []
        for area in areas:
            shape_kind, points = self._area_to_points(area)
            dtos.append(
                SceneAreaDto(
                    area_id=int(area.location_id),
                    name=area.name,
                    shape_kind=shape_kind,
                    points=points,
                )
            )
        return sorted(dtos, key=lambda area: area.area_id)

    @staticmethod
    def _area_to_points(area: LocationArea) -> tuple[str, list[ScenePointDto]]:
        geometry = area.area
        if isinstance(geometry, PointArea):
            return (
                "point",
                [ScenePointDto(x=geometry.coordinate.x, y=geometry.coordinate.y)],
            )
        if isinstance(geometry, RectArea):
            return (
                "rect",
                [
                    ScenePointDto(x=geometry.min_x, y=geometry.min_y),
                    ScenePointDto(x=geometry.max_x, y=geometry.max_y),
                ],
            )
        if isinstance(geometry, CircleArea):
            return (
                "circle",
                [ScenePointDto(x=geometry.center.x, y=geometry.center.y)],
            )
        reference = geometry.get_reference_coordinate()
        return ("unknown", [ScenePointDto(x=reference.x, y=reference.y)])

    def _resolve_display_name(self, obj: WorldObject) -> str:
        if obj.player_id is not None:
            profile = self._player_profile_repository.find_by_id(PlayerId(int(obj.player_id)))
            if profile is not None:
                return profile.name.value
            return f"Player {int(obj.player_id)}"
        return f"{obj.object_type.value.title()} {int(obj.object_id)}"

    @staticmethod
    def _resolve_actor_kind(obj: WorldObject) -> str:
        if obj.object_type == ObjectTypeEnum.PLAYER:
            return "player"
        if obj.object_type == ObjectTypeEnum.NPC:
            return "npc"
        return obj.object_type.value.lower()

    def _resolve_sprite_key(self, obj: WorldObject) -> str:
        if self._config.actor_sprite_key_resolver is not None:
            return self._config.actor_sprite_key_resolver(obj)
        if obj.object_type == ObjectTypeEnum.PLAYER:
            return "player_default"
        if obj.object_type == ObjectTypeEnum.NPC:
            return "npc_default"
        return obj.object_type.value.lower()

    def _resolve_weather_overlay_key(self, weather_type: str) -> Optional[str]:
        if self._config.weather_overlay_key_resolver is not None:
            return self._config.weather_overlay_key_resolver(weather_type)
        mapping = {
            "RAIN": "rain_light",
            "HEAVY_RAIN": "rain_heavy",
            "FOG": "fog_morning",
            "SNOW": "snow_light",
            "BLIZZARD": "snow_blizzard",
            "STORM": "storm_dark",
        }
        return mapping.get(weather_type)


__all__ = [
    "GameSceneBootstrapConfig",
    "GameSceneProjectionBootstrapService",
    "SceneRenderCatalogEntry",
]
