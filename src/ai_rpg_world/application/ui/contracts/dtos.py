"""DTOs for backend-driven game scene visualization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _ensure_str(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{name} must be non-empty str")


def _ensure_int(value: Any, name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{name} must be int")


def _ensure_bool(value: Any, name: str) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be bool")


def _ensure_float_like(value: Any, name: str) -> None:
    if not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be float-like")


@dataclass
class ScenePointDto:
    x: int
    y: int

    def __post_init__(self) -> None:
        _ensure_int(self.x, "x")
        _ensure_int(self.y, "y")


@dataclass
class SceneMapDto:
    map_asset_key: str
    tiled_map_path: str
    tile_width: int
    tile_height: int
    map_width_tiles: int
    map_height_tiles: int
    collision_layer_name: str
    tileset_keys: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _ensure_str(self.map_asset_key, "map_asset_key")
        _ensure_str(self.tiled_map_path, "tiled_map_path")
        _ensure_int(self.tile_width, "tile_width")
        _ensure_int(self.tile_height, "tile_height")
        _ensure_int(self.map_width_tiles, "map_width_tiles")
        _ensure_int(self.map_height_tiles, "map_height_tiles")
        _ensure_str(self.collision_layer_name, "collision_layer_name")
        if not isinstance(self.tileset_keys, list):
            raise TypeError("tileset_keys must be list")
        for key in self.tileset_keys:
            _ensure_str(key, "tileset_keys[]")


@dataclass
class SceneActorDto:
    actor_id: int
    player_id: Optional[int]
    display_name: str
    actor_kind: str
    tile_x: int
    tile_y: int
    facing: str
    sprite_key: str
    is_manual_controlled: bool = False
    is_llm_controlled: bool = True
    state: str = "idle"
    busy_until_tick: Optional[int] = None

    def __post_init__(self) -> None:
        _ensure_int(self.actor_id, "actor_id")
        if self.player_id is not None:
            _ensure_int(self.player_id, "player_id")
        _ensure_str(self.display_name, "display_name")
        _ensure_str(self.actor_kind, "actor_kind")
        _ensure_int(self.tile_x, "tile_x")
        _ensure_int(self.tile_y, "tile_y")
        _ensure_str(self.facing, "facing")
        _ensure_str(self.sprite_key, "sprite_key")
        _ensure_bool(self.is_manual_controlled, "is_manual_controlled")
        _ensure_bool(self.is_llm_controlled, "is_llm_controlled")
        _ensure_str(self.state, "state")
        if self.busy_until_tick is not None:
            _ensure_int(self.busy_until_tick, "busy_until_tick")


@dataclass
class SceneMonsterDto:
    monster_id: int
    display_name: str
    tile_x: int
    tile_y: int
    facing: str
    sprite_key: str
    state: str = "idle"

    def __post_init__(self) -> None:
        _ensure_int(self.monster_id, "monster_id")
        _ensure_str(self.display_name, "display_name")
        _ensure_int(self.tile_x, "tile_x")
        _ensure_int(self.tile_y, "tile_y")
        _ensure_str(self.facing, "facing")
        _ensure_str(self.sprite_key, "sprite_key")
        _ensure_str(self.state, "state")


@dataclass
class SceneObjectDto:
    object_id: int
    display_name: str
    object_kind: str
    tile_x: int
    tile_y: int
    sprite_key: str
    is_blocking: bool = True
    interaction_type: Optional[str] = None
    interaction_data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _ensure_int(self.object_id, "object_id")
        _ensure_str(self.display_name, "display_name")
        _ensure_str(self.object_kind, "object_kind")
        _ensure_int(self.tile_x, "tile_x")
        _ensure_int(self.tile_y, "tile_y")
        _ensure_str(self.sprite_key, "sprite_key")
        _ensure_bool(self.is_blocking, "is_blocking")
        if self.interaction_type is not None:
            _ensure_str(self.interaction_type, "interaction_type")
        if not isinstance(self.interaction_data, dict):
            raise TypeError("interaction_data must be dict")


@dataclass
class SceneWeatherDto:
    weather_type: str
    weather_intensity: float
    weather_overlay_key: Optional[str] = None

    def __post_init__(self) -> None:
        _ensure_str(self.weather_type, "weather_type")
        _ensure_float_like(self.weather_intensity, "weather_intensity")
        if self.weather_overlay_key is not None:
            _ensure_str(self.weather_overlay_key, "weather_overlay_key")


@dataclass
class SceneGatewayDto:
    gateway_id: int
    tile_x: int
    tile_y: int
    target_spot_id: int
    target_spot_name: str
    landing_tile_x: int
    landing_tile_y: int

    def __post_init__(self) -> None:
        _ensure_int(self.gateway_id, "gateway_id")
        _ensure_int(self.tile_x, "tile_x")
        _ensure_int(self.tile_y, "tile_y")
        _ensure_int(self.target_spot_id, "target_spot_id")
        _ensure_str(self.target_spot_name, "target_spot_name")
        _ensure_int(self.landing_tile_x, "landing_tile_x")
        _ensure_int(self.landing_tile_y, "landing_tile_y")


@dataclass
class SceneAreaDto:
    area_id: int
    name: str
    shape_kind: str
    points: List[ScenePointDto] = field(default_factory=list)

    def __post_init__(self) -> None:
        _ensure_int(self.area_id, "area_id")
        _ensure_str(self.name, "name")
        _ensure_str(self.shape_kind, "shape_kind")
        if not isinstance(self.points, list):
            raise TypeError("points must be list")
        for point in self.points:
            if not isinstance(point, ScenePointDto):
                raise TypeError("points must contain only ScenePointDto")


@dataclass
class SceneCameraDto:
    mode: str
    tracked_actor_id: Optional[int]
    viewport_width: int
    viewport_height: int

    def __post_init__(self) -> None:
        _ensure_str(self.mode, "mode")
        if self.tracked_actor_id is not None:
            _ensure_int(self.tracked_actor_id, "tracked_actor_id")
        _ensure_int(self.viewport_width, "viewport_width")
        _ensure_int(self.viewport_height, "viewport_height")


@dataclass
class SimulationStateDto:
    is_paused: bool
    speed_multiplier: float
    current_tick: int = 0

    def __post_init__(self) -> None:
        _ensure_bool(self.is_paused, "is_paused")
        _ensure_float_like(self.speed_multiplier, "speed_multiplier")
        _ensure_int(self.current_tick, "current_tick")


@dataclass
class SceneLogEntryDto:
    level: str
    message: str
    related_actor_id: Optional[int] = None

    def __post_init__(self) -> None:
        _ensure_str(self.level, "level")
        _ensure_str(self.message, "message")
        if self.related_actor_id is not None:
            _ensure_int(self.related_actor_id, "related_actor_id")


@dataclass
class WorldSceneSummaryDto:
    spot_id: int
    scene_id: str
    spot_name: str
    actor_count: int
    monster_count: int
    weather_type: Optional[str] = None
    scene_version: int = 0

    def __post_init__(self) -> None:
        _ensure_int(self.spot_id, "spot_id")
        _ensure_str(self.scene_id, "scene_id")
        _ensure_str(self.spot_name, "spot_name")
        _ensure_int(self.actor_count, "actor_count")
        _ensure_int(self.monster_count, "monster_count")
        if self.weather_type is not None:
            _ensure_str(self.weather_type, "weather_type")
        _ensure_int(self.scene_version, "scene_version")


@dataclass
class GameSceneSnapshotDto:
    scene_id: str
    spot_id: int
    spot_name: str
    map: SceneMapDto
    camera: SceneCameraDto
    simulation: SimulationStateDto
    actors: List[SceneActorDto] = field(default_factory=list)
    monsters: List[SceneMonsterDto] = field(default_factory=list)
    objects: List[SceneObjectDto] = field(default_factory=list)
    weather: Optional[SceneWeatherDto] = None
    gateways: List[SceneGatewayDto] = field(default_factory=list)
    areas: List[SceneAreaDto] = field(default_factory=list)
    ui_logs: List[SceneLogEntryDto] = field(default_factory=list)
    scene_version: int = 0
    server_time_ms: int = 0

    def __post_init__(self) -> None:
        _ensure_str(self.scene_id, "scene_id")
        _ensure_int(self.spot_id, "spot_id")
        _ensure_str(self.spot_name, "spot_name")
        if not isinstance(self.map, SceneMapDto):
            raise TypeError("map must be SceneMapDto")
        if not isinstance(self.camera, SceneCameraDto):
            raise TypeError("camera must be SceneCameraDto")
        if not isinstance(self.simulation, SimulationStateDto):
            raise TypeError("simulation must be SimulationStateDto")
        for field_name, values, expected_type in (
            ("actors", self.actors, SceneActorDto),
            ("monsters", self.monsters, SceneMonsterDto),
            ("objects", self.objects, SceneObjectDto),
            ("gateways", self.gateways, SceneGatewayDto),
            ("areas", self.areas, SceneAreaDto),
            ("ui_logs", self.ui_logs, SceneLogEntryDto),
        ):
            if not isinstance(values, list):
                raise TypeError(f"{field_name} must be list")
            for value in values:
                if not isinstance(value, expected_type):
                    raise TypeError(
                        f"{field_name} must contain only {expected_type.__name__}"
                    )
        if self.weather is not None and not isinstance(self.weather, SceneWeatherDto):
            raise TypeError("weather must be SceneWeatherDto or None")
        _ensure_int(self.scene_version, "scene_version")
        _ensure_int(self.server_time_ms, "server_time_ms")


@dataclass
class GameSceneDeltaEventDto:
    event_id: str
    event_type: str
    scene_id: str
    spot_id: int
    scene_version: int
    emitted_at_ms: int
    payload: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _ensure_str(self.event_id, "event_id")
        _ensure_str(self.event_type, "event_type")
        _ensure_str(self.scene_id, "scene_id")
        _ensure_int(self.spot_id, "spot_id")
        _ensure_int(self.scene_version, "scene_version")
        _ensure_int(self.emitted_at_ms, "emitted_at_ms")
        if not isinstance(self.payload, dict):
            raise TypeError("payload must be dict")


@dataclass
class ImportedSceneMapDto:
    spot_id: int
    map_width_tiles: int
    map_height_tiles: int
    tile_width: int
    tile_height: int
    tileset_keys: List[str] = field(default_factory=list)
    render_layers: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for name, value in (
            ("spot_id", self.spot_id),
            ("map_width_tiles", self.map_width_tiles),
            ("map_height_tiles", self.map_height_tiles),
            ("tile_width", self.tile_width),
            ("tile_height", self.tile_height),
        ):
            _ensure_int(value, name)
        for field_name, values in (
            ("tileset_keys", self.tileset_keys),
            ("render_layers", self.render_layers),
        ):
            if not isinstance(values, list):
                raise TypeError(f"{field_name} must be list")
            for value in values:
                _ensure_str(value, f"{field_name}[]")


@dataclass
class ImportedCollisionGridDto:
    width: int
    height: int
    passable_rows: List[List[bool]]
    terrain_rows: List[List[Optional[str]]] = field(default_factory=list)

    def __post_init__(self) -> None:
        _ensure_int(self.width, "width")
        _ensure_int(self.height, "height")
        if not isinstance(self.passable_rows, list):
            raise TypeError("passable_rows must be list")
        if len(self.passable_rows) != self.height:
            raise ValueError("passable_rows height mismatch")
        for row in self.passable_rows:
            if not isinstance(row, list):
                raise TypeError("passable_rows must contain lists")
            if len(row) != self.width:
                raise ValueError("passable_rows width mismatch")
            for cell in row:
                _ensure_bool(cell, "passable_rows[]")
        if self.terrain_rows:
            if len(self.terrain_rows) != self.height:
                raise ValueError("terrain_rows height mismatch")
            for row in self.terrain_rows:
                if len(row) != self.width:
                    raise ValueError("terrain_rows width mismatch")
                for value in row:
                    if value is not None:
                        _ensure_str(value, "terrain_rows[]")


@dataclass
class ImportedGatewayDto:
    gateway_id: int
    tile_x: int
    tile_y: int
    target_spot_id: int
    landing_tile_x: int
    landing_tile_y: int

    def __post_init__(self) -> None:
        for name, value in (
            ("gateway_id", self.gateway_id),
            ("tile_x", self.tile_x),
            ("tile_y", self.tile_y),
            ("target_spot_id", self.target_spot_id),
            ("landing_tile_x", self.landing_tile_x),
            ("landing_tile_y", self.landing_tile_y),
        ):
            _ensure_int(value, name)


@dataclass
class ImportedAreaDto:
    area_id: int
    name: str
    shape_kind: str
    points: List[ScenePointDto] = field(default_factory=list)

    def __post_init__(self) -> None:
        _ensure_int(self.area_id, "area_id")
        _ensure_str(self.name, "name")
        _ensure_str(self.shape_kind, "shape_kind")
        if not isinstance(self.points, list):
            raise TypeError("points must be list")
        for point in self.points:
            if not isinstance(point, ScenePointDto):
                raise TypeError("points must contain only ScenePointDto")


@dataclass
class ImportedSpawnPointDto:
    spawn_id: str
    spawn_kind: str
    tile_x: int
    tile_y: int
    sprite_key: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _ensure_str(self.spawn_id, "spawn_id")
        _ensure_str(self.spawn_kind, "spawn_kind")
        _ensure_int(self.tile_x, "tile_x")
        _ensure_int(self.tile_y, "tile_y")
        if self.sprite_key is not None:
            _ensure_str(self.sprite_key, "sprite_key")
        if not isinstance(self.metadata, dict):
            raise TypeError("metadata must be dict")


@dataclass
class ImportedRenderMetadataDto:
    map_asset_key: str
    tiled_map_path: str
    upper_layers: List[str] = field(default_factory=list)
    shadow_layers: List[str] = field(default_factory=list)
    overlay_anchor_points: List[ScenePointDto] = field(default_factory=list)

    def __post_init__(self) -> None:
        _ensure_str(self.map_asset_key, "map_asset_key")
        _ensure_str(self.tiled_map_path, "tiled_map_path")
        for field_name, values in (
            ("upper_layers", self.upper_layers),
            ("shadow_layers", self.shadow_layers),
        ):
            if not isinstance(values, list):
                raise TypeError(f"{field_name} must be list")
            for value in values:
                _ensure_str(value, f"{field_name}[]")
        if not isinstance(self.overlay_anchor_points, list):
            raise TypeError("overlay_anchor_points must be list")
        for point in self.overlay_anchor_points:
            if not isinstance(point, ScenePointDto):
                raise TypeError("overlay_anchor_points must contain only ScenePointDto")


@dataclass
class ImportedSceneBundleDto:
    scene_map: ImportedSceneMapDto
    collision_grid: ImportedCollisionGridDto
    gateways: List[ImportedGatewayDto] = field(default_factory=list)
    areas: List[ImportedAreaDto] = field(default_factory=list)
    spawn_points: List[ImportedSpawnPointDto] = field(default_factory=list)
    render_metadata: Optional[ImportedRenderMetadataDto] = None

    def __post_init__(self) -> None:
        if not isinstance(self.scene_map, ImportedSceneMapDto):
            raise TypeError("scene_map must be ImportedSceneMapDto")
        if not isinstance(self.collision_grid, ImportedCollisionGridDto):
            raise TypeError("collision_grid must be ImportedCollisionGridDto")
        for field_name, values, expected_type in (
            ("gateways", self.gateways, ImportedGatewayDto),
            ("areas", self.areas, ImportedAreaDto),
            ("spawn_points", self.spawn_points, ImportedSpawnPointDto),
        ):
            if not isinstance(values, list):
                raise TypeError(f"{field_name} must be list")
            for value in values:
                if not isinstance(value, expected_type):
                    raise TypeError(
                        f"{field_name} must contain only {expected_type.__name__}"
                    )
        if self.render_metadata is not None and not isinstance(
            self.render_metadata, ImportedRenderMetadataDto
        ):
            raise TypeError("render_metadata must be ImportedRenderMetadataDto or None")


@dataclass(frozen=True)
class InteractSceneObjectResultDto:
    success: bool
    actor_id: int
    target_object_id: int
    spot_id: int
    interaction_type: str
    message: str
    object_state: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _ensure_bool(self.success, "success")
        _ensure_int(self.actor_id, "actor_id")
        _ensure_int(self.target_object_id, "target_object_id")
        _ensure_int(self.spot_id, "spot_id")
        _ensure_str(self.interaction_type, "interaction_type")
        _ensure_str(self.message, "message")
        if not isinstance(self.object_state, dict):
            raise TypeError("object_state must be dict")
