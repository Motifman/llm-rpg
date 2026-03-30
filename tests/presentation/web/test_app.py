"""Tests for FastAPI web adapters."""

from fastapi.testclient import TestClient

from ai_rpg_world.application.ui.contracts.dtos import (
    GameSceneDeltaEventDto,
    GameSceneSnapshotDto,
    SceneActorDto,
    SceneCameraDto,
    SceneObjectDto,
    SceneMapDto,
    SimulationStateDto,
)
from ai_rpg_world.application.ui.services.game_scene_projection import GameSceneProjection
from ai_rpg_world.application.ui.services.game_scene_snapshot_service import (
    GameSceneSnapshotService,
)
from ai_rpg_world.application.ui.services.game_scene_stream_service import (
    GameSceneStreamService,
)
from ai_rpg_world.application.ui.services.manual_actor_control_service import (
    ManualActorControlService,
)
from ai_rpg_world.application.ui.services.manual_object_interaction_service import (
    ManualObjectInteractionService,
)
from ai_rpg_world.application.ui.services.simulation_control_service import (
    SimulationControlService,
)
from ai_rpg_world.infrastructure.ui.in_memory_game_scene_event_broker import (
    InMemoryGameSceneEventBroker,
)
from ai_rpg_world.presentation.game_control_api import GameControlApi
from ai_rpg_world.presentation.game_scene_api import GameSceneApi
from ai_rpg_world.presentation.web.app import create_web_app


class _StubMovementPort:
    def __init__(self) -> None:
        self.calls = []

    def move_tile(self, command):
        self.calls.append(command)
        return {"success": True, "message": "moved"}


class _StubInteractionPort:
    def __init__(self) -> None:
        self.calls = []

    def interact(self, *, actor_id: int, target_object_id: int):
        self.calls.append((actor_id, target_object_id))
        return {
            "success": True,
            "actor_id": actor_id,
            "target_object_id": target_object_id,
            "spot_id": 1,
            "interaction_type": "chest",
            "message": "opened",
            "object_state": {"is_open": True},
        }


def _make_snapshot(spot_id: int = 1) -> GameSceneSnapshotDto:
    return GameSceneSnapshotDto(
        scene_id=f"spot-{spot_id}",
        spot_id=spot_id,
        spot_name=f"Spot {spot_id}",
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
                tile_y=1,
                facing="down",
                sprite_key="player_default",
            )
        ],
        monsters=[],
        objects=[
            SceneObjectDto(
                object_id=2001,
                display_name="宝箱",
                object_kind="chest",
                tile_x=2,
                tile_y=2,
                sprite_key="object_chest_closed",
                is_blocking=True,
                interaction_type="chest",
            )
        ],
        scene_version=0,
        server_time_ms=0,
    )


def _create_client() -> tuple[
    TestClient,
    GameSceneProjection,
    InMemoryGameSceneEventBroker,
    _StubMovementPort,
    _StubInteractionPort,
]:
    projection = GameSceneProjection()
    projection.upsert_snapshot(_make_snapshot(1))
    broker = InMemoryGameSceneEventBroker()
    snapshot_service = GameSceneSnapshotService(projection)
    stream_service = GameSceneStreamService(broker)
    movement_port = _StubMovementPort()
    interaction_port = _StubInteractionPort()
    simulation_control = SimulationControlService(projection, broker)
    manual_control = ManualActorControlService(
        movement_port,
        projection,
        manual_player_ids=[1],
    )
    interaction_control = ManualObjectInteractionService(
        interaction_port,
        manual_player_ids=[1],
    )
    scene_api = GameSceneApi(snapshot_service, stream_service)
    control_api = GameControlApi(
        simulation_control,
        manual_control,
        interaction_control,
    )
    app = create_web_app(
        scene_api=scene_api,
        control_api=control_api,
        cors_allowed_origins=("http://127.0.0.1:5173",),
    )
    return TestClient(app), projection, broker, movement_port, interaction_port


def test_get_scene_snapshot_returns_snapshot_json():
    client, _, _, _, _ = _create_client()

    response = client.get("/api/scenes/1/snapshot")

    assert response.status_code == 200
    assert response.json()["scene_id"] == "spot-1"
    assert response.json()["actors"][0]["display_name"] == "Hero"


def test_get_scene_snapshot_returns_404_for_missing_scene():
    client, _, _, _, _ = _create_client()

    response = client.get("/api/scenes/999/snapshot")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_control_endpoints_update_projection_state():
    client, projection, _, _, _ = _create_client()

    pause_response = client.post("/api/control/pause")
    speed_response = client.post("/api/control/speed", json={"speed_multiplier": 2.0})
    resume_response = client.post("/api/control/resume")

    assert pause_response.status_code == 204
    assert speed_response.status_code == 204
    assert resume_response.status_code == 204
    snapshot = projection.get_snapshot(1)
    assert snapshot.simulation.is_paused is False
    assert snapshot.simulation.speed_multiplier == 2.0


def test_move_actor_returns_400_for_unknown_direction():
    client, _, _, _, _ = _create_client()

    response = client.post("/api/actors/1/move", json={"direction": "bad"})

    assert response.status_code == 400
    assert "Unknown direction" in response.json()["detail"]


def test_move_actor_returns_403_when_manual_control_is_forbidden():
    client, _, _, _, _ = _create_client()

    response = client.post("/api/actors/2/move", json={"direction": "north"})

    assert response.status_code == 403
    assert "not allowed" in response.json()["detail"]


def test_move_actor_delegates_to_manual_control():
    client, _, _, movement_port, _ = _create_client()

    response = client.post("/api/actors/1/move", json={"direction": "east"})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert movement_port.calls[0].player_id == 1


def test_world_overview_returns_scene_summaries():
    client, _, _, _, _ = _create_client()

    response = client.get("/api/world/overview")

    assert response.status_code == 200
    assert response.json()[0]["spot_id"] == 1
    assert response.json()[0]["actor_count"] == 1


def test_world_overview_includes_cors_header_for_allowed_origin():
    client, _, _, _, _ = _create_client()

    response = client.get(
        "/api/world/overview",
        headers={"Origin": "http://127.0.0.1:5173"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_world_overview_preflight_returns_cors_headers():
    client, _, _, _, _ = _create_client()

    response = client.options(
        "/api/world/overview",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "content-type" in response.headers["access-control-allow-headers"].lower()


def test_websocket_stream_sends_initial_backlog_and_poll_updates():
    client, _, broker, _, _ = _create_client()
    broker.publish(
        GameSceneDeltaEventDto(
            event_id="evt-1",
            event_type="actor_moved",
            scene_id="spot-1",
            spot_id=1,
            scene_version=1,
            emitted_at_ms=1,
            payload={"actor_id": 1},
        )
    )
    broker.publish(
        GameSceneDeltaEventDto(
            event_id="evt-2",
            event_type="weather_changed",
            scene_id="spot-1",
            spot_id=1,
            scene_version=2,
            emitted_at_ms=2,
            payload={"weather_type": "RAIN"},
        )
    )

    with client.websocket_connect("/api/scenes/spot-1/stream?last_seen_scene_version=0") as websocket:
        initial = websocket.receive_json()
        assert initial["type"] == "scene_events"
        assert [event["event_id"] for event in initial["events"]] == ["evt-1", "evt-2"]

        websocket.send_json({"action": "poll", "last_seen_scene_version": 1})
        polled = websocket.receive_json()
        assert [event["event_id"] for event in polled["events"]] == ["evt-2"]


def test_websocket_stream_returns_error_for_unsupported_action():
    client, _, _, _, _ = _create_client()

    with client.websocket_connect("/api/scenes/spot-1/stream") as websocket:
        websocket.receive_json()
        websocket.send_json({"action": "noop", "last_seen_scene_version": 0})
        response = websocket.receive_json()
        assert response["type"] == "error"
        assert "Unsupported action" in response["detail"]


def test_websocket_stream_returns_pong_for_ping():
    client, _, _, _, _ = _create_client()

    with client.websocket_connect("/api/scenes/spot-1/stream") as websocket:
        websocket.receive_json()
        websocket.send_json({"action": "ping"})
        response = websocket.receive_json()
        assert response == {"type": "pong"}


def test_websocket_stream_returns_error_for_invalid_cursor_query():
    client, _, _, _, _ = _create_client()

    with client.websocket_connect(
        "/api/scenes/spot-1/stream?last_seen_scene_version=oops"
    ) as websocket:
        response = websocket.receive_json()
        assert response["type"] == "error"
        assert response["detail"] == "Invalid stream cursor."
        assert response["errors"][0]["loc"] == ["last_seen_scene_version"]


def test_websocket_stream_returns_error_for_invalid_poll_payload():
    client, _, _, _, _ = _create_client()


def test_interact_actor_delegates_to_manual_object_interaction():
    client, _, _, _, interaction_port = _create_client()

    response = client.post("/api/actors/1/interact", json={"target_object_id": 2001})

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert interaction_port.calls == [(1, 2001)]


def test_interact_actor_returns_403_when_manual_control_is_forbidden():
    client, _, _, _, _ = _create_client()

    response = client.post("/api/actors/2/interact", json={"target_object_id": 2001})

    assert response.status_code == 403
    assert "not allowed" in response.json()["detail"]

    with client.websocket_connect("/api/scenes/spot-1/stream") as websocket:
        websocket.receive_json()
        websocket.send_json(
            {"action": "poll", "last_seen_scene_version": "not-a-number"}
        )
        response = websocket.receive_json()
        assert response["type"] == "error"
        assert response["detail"] == "Invalid stream request payload."
        assert response["errors"][0]["loc"] == ["last_seen_scene_version"]
