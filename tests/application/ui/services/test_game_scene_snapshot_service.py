"""Tests for GameSceneSnapshotService."""

from ai_rpg_world.application.ui.contracts.dtos import (
    GameSceneSnapshotDto,
    SceneActorDto,
    SceneCameraDto,
    SceneMapDto,
    SceneWeatherDto,
    SimulationStateDto,
)
from ai_rpg_world.application.ui.services.game_scene_projection import GameSceneProjection
from ai_rpg_world.application.ui.services.game_scene_snapshot_service import (
    GameSceneSnapshotService,
)
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_spot_repository import (
    InMemorySpotRepository,
)


def _make_snapshot(spot_id: int, spot_name: str) -> GameSceneSnapshotDto:
    return GameSceneSnapshotDto(
        scene_id=f"spot-{spot_id}",
        spot_id=spot_id,
        spot_name=spot_name,
        map=SceneMapDto(
            map_asset_key=f"spot_{spot_id}",
            tiled_map_path=f"maps/{spot_id}.json",
            tile_width=32,
            tile_height=32,
            map_width_tiles=10,
            map_height_tiles=10,
            collision_layer_name="collision",
            tileset_keys=["terrain.tsx"],
        ),
        camera=SceneCameraDto(
            mode="fixed",
            tracked_actor_id=None,
            viewport_width=640,
            viewport_height=480,
        ),
        simulation=SimulationStateDto(is_paused=False, speed_multiplier=1.0),
        actors=[
            SceneActorDto(
                actor_id=1,
                player_id=1,
                display_name="Hero",
                actor_kind="player",
                tile_x=1,
                tile_y=2,
                facing="down",
                sprite_key="player_default",
            )
        ],
        weather=SceneWeatherDto(
            weather_type="RAIN",
            weather_intensity=0.5,
            weather_overlay_key="rain_light",
        ),
        scene_version=3,
        server_time_ms=10,
    )


def test_get_scene_snapshot_prefers_spot_repository_name():
    projection = GameSceneProjection()
    projection.upsert_snapshot(_make_snapshot(1, "Old Name"))
    data_store = InMemoryDataStore()
    spot_repo = InMemorySpotRepository(data_store)
    spot_repo.save(
        Spot(
            spot_id=SpotId(1),
            name="Town",
            description="desc",
            category=SpotCategoryEnum.TOWN,
        )
    )
    service = GameSceneSnapshotService(projection, spot_repository=spot_repo)

    snapshot = service.get_scene_snapshot(1)

    assert snapshot.spot_name == "Town"


def test_get_world_overview_returns_sorted_scene_summaries():
    projection = GameSceneProjection()
    projection.upsert_snapshot(_make_snapshot(2, "Field"))
    projection.upsert_snapshot(_make_snapshot(1, "Town"))
    service = GameSceneSnapshotService(projection)

    overview = service.get_world_overview()

    assert [item.spot_id for item in overview] == [1, 2]
    assert overview[0].actor_count == 1
    assert overview[0].weather_type == "RAIN"

