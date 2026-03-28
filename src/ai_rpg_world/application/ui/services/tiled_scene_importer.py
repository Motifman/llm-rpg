"""Importer from Tiled JSON to backend-owned normalized scene structures."""

from __future__ import annotations

from typing import Any, Dict, List

from ai_rpg_world.application.ui.contracts.dtos import (
    ImportedAreaDto,
    ImportedCollisionGridDto,
    ImportedGatewayDto,
    ImportedRenderMetadataDto,
    ImportedSceneBundleDto,
    ImportedSceneMapDto,
    ImportedSpawnPointDto,
    ScenePointDto,
)
from ai_rpg_world.application.ui.exceptions import TiledImportException


class TiledSceneImporter:
    """Converts Tiled JSON dicts into normalized backend DTOs."""

    def import_map(self, tiled_data: Dict[str, Any], *, tiled_map_path: str) -> ImportedSceneBundleDto:
        if not isinstance(tiled_data, dict):
            raise TiledImportException("tiled_data must be dict")
        self._require_keys(tiled_data, ["width", "height", "tilewidth", "tileheight", "layers"])
        properties = self._property_map(tiled_data.get("properties", []))
        spot_id = self._require_int(properties, "spot_id")
        map_asset_key = self._require_str(properties, "map_asset_key")
        layers = tiled_data["layers"]
        if not isinstance(layers, list):
            raise TiledImportException("layers must be list")

        tile_layers = [layer for layer in layers if layer.get("type") == "tilelayer"]
        object_layers = [layer for layer in layers if layer.get("type") == "objectgroup"]
        collision_layer = next(
            (layer for layer in tile_layers if layer.get("name") == "collision"),
            None,
        )
        if collision_layer is None:
            raise TiledImportException("collision tile layer is required")

        width = self._require_int(tiled_data, "width")
        height = self._require_int(tiled_data, "height")
        tile_width = self._require_int(tiled_data, "tilewidth")
        tile_height = self._require_int(tiled_data, "tileheight")

        scene_map = ImportedSceneMapDto(
            spot_id=spot_id,
            map_width_tiles=width,
            map_height_tiles=height,
            tile_width=tile_width,
            tile_height=tile_height,
            tileset_keys=self._extract_tileset_keys(tiled_data),
            render_layers=[layer.get("name", "") for layer in tile_layers],
        )
        collision_grid = ImportedCollisionGridDto(
            width=width,
            height=height,
            passable_rows=self._parse_collision_rows(collision_layer, width, height),
            terrain_rows=[],
        )
        gateways = self._parse_gateways(object_layers)
        areas = self._parse_areas(object_layers)
        spawn_points = self._parse_spawn_points(object_layers)
        render_metadata = ImportedRenderMetadataDto(
            map_asset_key=map_asset_key,
            tiled_map_path=tiled_map_path,
            upper_layers=["upper"] if any(layer.get("name") == "upper" for layer in tile_layers) else [],
            shadow_layers=["shadow"] if any(layer.get("name") == "shadow" for layer in tile_layers) else [],
            overlay_anchor_points=[],
        )
        return ImportedSceneBundleDto(
            scene_map=scene_map,
            collision_grid=collision_grid,
            gateways=gateways,
            areas=areas,
            spawn_points=spawn_points,
            render_metadata=render_metadata,
        )

    @staticmethod
    def _require_keys(data: Dict[str, Any], keys: List[str]) -> None:
        for key in keys:
            if key not in data:
                raise TiledImportException(f"missing required key: {key}")

    @staticmethod
    def _require_int(data: Dict[str, Any], key: str) -> int:
        value = data.get(key)
        if not isinstance(value, int):
            raise TiledImportException(f"{key} must be int")
        return value

    @staticmethod
    def _require_str(data: Dict[str, Any], key: str) -> str:
        value = data.get(key)
        if not isinstance(value, str) or not value:
            raise TiledImportException(f"{key} must be non-empty str")
        return value

    @staticmethod
    def _property_map(properties: Any) -> Dict[str, Any]:
        if properties is None:
            return {}
        if not isinstance(properties, list):
            raise TiledImportException("properties must be list")
        result: Dict[str, Any] = {}
        for prop in properties:
            if not isinstance(prop, dict):
                raise TiledImportException("property entries must be dict")
            name = prop.get("name")
            if not isinstance(name, str) or not name:
                raise TiledImportException("property name must be non-empty str")
            result[name] = prop.get("value")
        return result

    def _parse_collision_rows(
        self, layer: Dict[str, Any], width: int, height: int
    ) -> List[List[bool]]:
        data = layer.get("data")
        if not isinstance(data, list):
            raise TiledImportException("collision layer data must be list")
        if len(data) != width * height:
            raise TiledImportException("collision layer size mismatch")
        rows: List[List[bool]] = []
        for y in range(height):
            row: List[bool] = []
            for x in range(width):
                idx = y * width + x
                value = data[idx]
                if not isinstance(value, int):
                    raise TiledImportException("collision layer cells must be int")
                row.append(value == 0)
            rows.append(row)
        return rows

    def _parse_gateways(self, object_layers: List[Dict[str, Any]]) -> List[ImportedGatewayDto]:
        result: List[ImportedGatewayDto] = []
        for obj in self._iter_objects(object_layers, "gateway"):
            props = self._property_map(obj.get("properties", []))
            result.append(
                ImportedGatewayDto(
                    gateway_id=self._require_int(props, "gateway_id"),
                    tile_x=self._tile_x(obj),
                    tile_y=self._tile_y(obj),
                    target_spot_id=self._require_int(props, "target_spot_id"),
                    landing_tile_x=self._require_int(props, "landing_tile_x"),
                    landing_tile_y=self._require_int(props, "landing_tile_y"),
                )
            )
        return result

    def _parse_areas(self, object_layers: List[Dict[str, Any]]) -> List[ImportedAreaDto]:
        result: List[ImportedAreaDto] = []
        for obj in self._iter_objects(object_layers, "area"):
            props = self._property_map(obj.get("properties", []))
            result.append(
                ImportedAreaDto(
                    area_id=self._require_int(props, "area_id"),
                    name=self._require_str(props, "name"),
                    shape_kind=self._shape_kind(obj),
                    points=self._shape_points(obj),
                )
            )
        return result

    def _parse_spawn_points(
        self, object_layers: List[Dict[str, Any]]
    ) -> List[ImportedSpawnPointDto]:
        result: List[ImportedSpawnPointDto] = []
        for obj in self._iter_objects(object_layers, "spawn"):
            props = self._property_map(obj.get("properties", []))
            result.append(
                ImportedSpawnPointDto(
                    spawn_id=self._require_str(props, "spawn_id"),
                    spawn_kind=self._require_str(props, "spawn_kind"),
                    tile_x=self._tile_x(obj),
                    tile_y=self._tile_y(obj),
                    sprite_key=props.get("sprite_key"),
                    metadata=props,
                )
            )
        return result

    def _iter_objects(
        self, object_layers: List[Dict[str, Any]], expected_kind: str
    ) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for layer in object_layers:
            objects = layer.get("objects", [])
            if not isinstance(objects, list):
                raise TiledImportException("object layer objects must be list")
            for obj in objects:
                if not isinstance(obj, dict):
                    raise TiledImportException("object must be dict")
                props = self._property_map(obj.get("properties", []))
                if props.get("object_kind") == expected_kind:
                    result.append(obj)
        return result

    @staticmethod
    def _tile_x(obj: Dict[str, Any]) -> int:
        x = obj.get("x")
        if not isinstance(x, (int, float)):
            raise TiledImportException("object x must be number")
        return int(x)

    @staticmethod
    def _tile_y(obj: Dict[str, Any]) -> int:
        y = obj.get("y")
        if not isinstance(y, (int, float)):
            raise TiledImportException("object y must be number")
        return int(y)

    @staticmethod
    def _shape_kind(obj: Dict[str, Any]) -> str:
        if "polygon" in obj:
            return "polygon"
        return "rectangle"

    def _shape_points(self, obj: Dict[str, Any]) -> List[ScenePointDto]:
        if "polygon" in obj:
            polygon = obj["polygon"]
            if not isinstance(polygon, list):
                raise TiledImportException("polygon must be list")
            return [
                ScenePointDto(x=int(point["x"]), y=int(point["y"]))
                for point in polygon
            ]
        x = self._tile_x(obj)
        y = self._tile_y(obj)
        width = int(obj.get("width", 0))
        height = int(obj.get("height", 0))
        return [
            ScenePointDto(x=x, y=y),
            ScenePointDto(x=x + width, y=y),
            ScenePointDto(x=x + width, y=y + height),
            ScenePointDto(x=x, y=y + height),
        ]

    @staticmethod
    def _extract_tileset_keys(tiled_data: Dict[str, Any]) -> List[str]:
        tilesets = tiled_data.get("tilesets", [])
        if not isinstance(tilesets, list):
            raise TiledImportException("tilesets must be list")
        result: List[str] = []
        for tileset in tilesets:
            if not isinstance(tileset, dict):
                raise TiledImportException("tileset entries must be dict")
            source = tileset.get("source")
            if isinstance(source, str) and source:
                result.append(source)
            else:
                name = tileset.get("name")
                if isinstance(name, str) and name:
                    result.append(name)
        return result

