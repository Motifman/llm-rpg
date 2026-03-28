"""Tests for TiledSceneImporter."""

import pytest

from ai_rpg_world.application.ui.exceptions import TiledImportException
from ai_rpg_world.application.ui.services.tiled_scene_importer import TiledSceneImporter


def _make_tiled_payload():
    return {
        "width": 4,
        "height": 3,
        "tilewidth": 32,
        "tileheight": 32,
        "properties": [
            {"name": "spot_id", "value": 10},
            {"name": "map_asset_key", "value": "starter_field"},
        ],
        "tilesets": [{"source": "terrain.tsx"}],
        "layers": [
            {
                "type": "tilelayer",
                "name": "ground",
                "data": [1] * 12,
            },
            {
                "type": "tilelayer",
                "name": "collision",
                "data": [0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
            },
            {
                "type": "objectgroup",
                "name": "objects",
                "objects": [
                    {
                        "x": 1,
                        "y": 2,
                        "properties": [
                            {"name": "object_kind", "value": "gateway"},
                            {"name": "gateway_id", "value": 100},
                            {"name": "target_spot_id", "value": 11},
                            {"name": "landing_tile_x", "value": 3},
                            {"name": "landing_tile_y", "value": 4},
                        ],
                    },
                    {
                        "x": 2,
                        "y": 1,
                        "width": 2,
                        "height": 2,
                        "properties": [
                            {"name": "object_kind", "value": "area"},
                            {"name": "area_id", "value": 201},
                            {"name": "name", "value": "Plaza"},
                        ],
                    },
                    {
                        "x": 3,
                        "y": 0,
                        "properties": [
                            {"name": "object_kind", "value": "spawn"},
                            {"name": "spawn_id", "value": "player_spawn_1"},
                            {"name": "spawn_kind", "value": "player"},
                            {"name": "sprite_key", "value": "player_default"},
                        ],
                    },
                ],
            },
        ],
    }


def test_import_map_returns_normalized_bundle():
    importer = TiledSceneImporter()
    bundle = importer.import_map(_make_tiled_payload(), tiled_map_path="maps/starter.json")

    assert bundle.scene_map.spot_id == 10
    assert bundle.scene_map.tileset_keys == ["terrain.tsx"]
    assert bundle.collision_grid.passable_rows[0] == [True, False, True, True]
    assert bundle.gateways[0].target_spot_id == 11
    assert bundle.areas[0].name == "Plaza"
    assert bundle.spawn_points[0].spawn_id == "player_spawn_1"
    assert bundle.render_metadata.map_asset_key == "starter_field"


def test_import_map_rejects_missing_collision_layer():
    importer = TiledSceneImporter()
    payload = _make_tiled_payload()
    payload["layers"] = [layer for layer in payload["layers"] if layer.get("name") != "collision"]

    with pytest.raises(TiledImportException, match="collision tile layer is required"):
        importer.import_map(payload, tiled_map_path="maps/starter.json")


def test_import_map_rejects_missing_spot_id_property():
    importer = TiledSceneImporter()
    payload = _make_tiled_payload()
    payload["properties"] = [{"name": "map_asset_key", "value": "starter_field"}]

    with pytest.raises(TiledImportException, match="spot_id must be int"):
        importer.import_map(payload, tiled_map_path="maps/starter.json")

