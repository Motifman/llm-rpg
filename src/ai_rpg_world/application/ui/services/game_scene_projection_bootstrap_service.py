"""Bootstrap scene projection snapshots from live repositories."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Mapping, Optional

from ai_rpg_world.application.ui.contracts.dtos import (
    GameSceneSnapshotDto,
    SceneActorDto,
    SceneAreaDto,
    SceneCameraDto,
    SceneGatewayDto,
    SceneLogEntryDto,
    SceneMapDto,
    SceneMonsterDto,
    SceneObjectDto,
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
        self._tiled_metadata_cache: dict[str, dict[str, int] | None] = {}

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
                    monsters=self._build_monster_dtos(physical_map.get_all_objects()),
                    objects=self._build_object_dtos(physical_map.get_all_objects()),
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
        tiled_map_path = (
            catalog_entry.tiled_map_path
            if catalog_entry is not None
            else f"data/maps/spot_{spot_id}.json"
        )
        tiled_metadata = self._load_tiled_metadata(tiled_map_path)
        tile_list = list(tiles)
        if tile_list:
            fallback_map_width_tiles = max(tile.coordinate.x for tile in tile_list) + 1
            fallback_map_height_tiles = max(tile.coordinate.y for tile in tile_list) + 1
        else:
            fallback_map_width_tiles = 0
            fallback_map_height_tiles = 0
        map_width_tiles = (
            tiled_metadata["width"]
            if tiled_metadata is not None
            else fallback_map_width_tiles
        )
        map_height_tiles = (
            tiled_metadata["height"]
            if tiled_metadata is not None
            else fallback_map_height_tiles
        )
        tile_width = (
            tiled_metadata["tilewidth"]
            if tiled_metadata is not None
            else (catalog_entry.tile_width if catalog_entry is not None else 32)
        )
        tile_height = (
            tiled_metadata["tileheight"]
            if tiled_metadata is not None
            else (catalog_entry.tile_height if catalog_entry is not None else 32)
        )
        return SceneMapDto(
            map_asset_key=(
                catalog_entry.map_asset_key if catalog_entry is not None else f"spot_{spot_id}"
            ),
            tiled_map_path=tiled_map_path,
            tile_width=tile_width,
            tile_height=tile_height,
            map_width_tiles=map_width_tiles,
            map_height_tiles=map_height_tiles,
            collision_layer_name=(
                catalog_entry.collision_layer_name
                if catalog_entry is not None
                else "collision"
            ),
            tileset_keys=list(catalog_entry.tileset_keys) if catalog_entry is not None else [],
        )

    def _load_tiled_metadata(self, tiled_map_path: str) -> dict[str, int] | None:
        if tiled_map_path in self._tiled_metadata_cache:
            return self._tiled_metadata_cache[tiled_map_path]
        for candidate in self._candidate_tiled_paths(tiled_map_path):
            if not candidate.exists():
                continue
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            width = payload.get("width")
            height = payload.get("height")
            tilewidth = payload.get("tilewidth")
            tileheight = payload.get("tileheight")
            if not all(isinstance(value, int) for value in (width, height, tilewidth, tileheight)):
                continue
            metadata = {
                "width": width,
                "height": height,
                "tilewidth": tilewidth,
                "tileheight": tileheight,
            }
            self._tiled_metadata_cache[tiled_map_path] = metadata
            return metadata
        self._tiled_metadata_cache[tiled_map_path] = None
        return None

    @staticmethod
    def _candidate_tiled_paths(tiled_map_path: str) -> list[Path]:
        candidate = Path(tiled_map_path)
        repo_root = Path(__file__).resolve().parents[5]
        return [
            candidate,
            Path.cwd() / tiled_map_path,
            repo_root / "frontend" / "public" / tiled_map_path,
        ]

    def _build_actor_dtos(self, objects: Iterable[WorldObject]) -> list[SceneActorDto]:
        actors: list[SceneActorDto] = []
        for obj in objects:
            if not obj.is_actor or obj.object_type != ObjectTypeEnum.PLAYER:
                continue
            player_id = int(obj.player_id) if obj.player_id is not None else None
            actors.append(
                SceneActorDto(
                    actor_id=int(obj.object_id),
                    player_id=player_id,
                    display_name=self._resolve_display_name(obj),
                    actor_kind=self._resolve_actor_kind(obj),
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

    def _build_monster_dtos(self, objects: Iterable[WorldObject]) -> list[SceneMonsterDto]:
        monsters: list[SceneMonsterDto] = []
        for obj in objects:
            if not obj.is_actor or obj.object_type != ObjectTypeEnum.NPC:
                continue
            monsters.append(
                SceneMonsterDto(
                    monster_id=int(obj.object_id),
                    display_name=self._resolve_display_name(obj),
                    tile_x=obj.coordinate.x,
                    tile_y=obj.coordinate.y,
                    facing=(
                        obj.direction.name.lower() if obj.direction is not None else "down"
                    ),
                    sprite_key=self._resolve_sprite_key(obj),
                    state="busy" if obj.busy_until is not None else "idle",
                )
            )
        return sorted(monsters, key=lambda monster: monster.monster_id)

    def _build_object_dtos(self, objects: Iterable[WorldObject]) -> list[SceneObjectDto]:
        scene_objects: list[SceneObjectDto] = []
        for obj in objects:
            if obj.is_actor:
                continue
            scene_objects.append(
                SceneObjectDto(
                    object_id=int(obj.object_id),
                    display_name=self._resolve_display_name(obj),
                    object_kind=obj.object_type.value.lower(),
                    tile_x=obj.coordinate.x,
                    tile_y=obj.coordinate.y,
                    sprite_key=self._resolve_object_sprite_key(obj),
                    is_blocking=obj.is_blocking,
                    interaction_type=(
                        obj.interaction_type.value if obj.interaction_type is not None else None
                    ),
                    interaction_data=dict(obj.interaction_data),
                )
            )
        return sorted(scene_objects, key=lambda scene_object: scene_object.object_id)

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
        if obj.object_type == ObjectTypeEnum.NPC:
            return "Slime"
        if obj.object_type == ObjectTypeEnum.CHEST:
            return "宝箱"
        return f"{obj.object_type.value.title()} {int(obj.object_id)}"

    @staticmethod
    def _resolve_actor_kind(obj: WorldObject) -> str:
        if obj.object_type == ObjectTypeEnum.PLAYER:
            return "player"
        if obj.object_type == ObjectTypeEnum.NPC:
            return "monster"
        return obj.object_type.value.lower()

    def _resolve_sprite_key(self, obj: WorldObject) -> str:
        if self._config.actor_sprite_key_resolver is not None:
            return self._config.actor_sprite_key_resolver(obj)
        if obj.object_type == ObjectTypeEnum.PLAYER:
            return "player_default"
        if obj.object_type == ObjectTypeEnum.NPC:
            return "monster_blob"
        return obj.object_type.value.lower()

    @staticmethod
    def _resolve_object_sprite_key(obj: WorldObject) -> str:
        if obj.object_type == ObjectTypeEnum.CHEST:
            return "object_chest_closed"
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
