"""FastAPI application factory for scene snapshot/stream and manual control APIs."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Sequence

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, ValidationError

from ai_rpg_world.application.common.exceptions import ApplicationException
from ai_rpg_world.application.ui.contracts.commands import (
    InteractSceneObjectCommand,
    MoveManualActorCommand,
    PauseSimulationCommand,
    ResumeSimulationCommand,
    SetSimulationSpeedCommand,
)
from ai_rpg_world.application.ui.exceptions import (
    GameSceneNotFoundException,
    ManualControlForbiddenException,
    SimulationSpeedValidationException,
)
from ai_rpg_world.domain.world.exception.map_exception import MapDomainException
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
from ai_rpg_world.presentation.game_control_api import GameControlApi
from ai_rpg_world.presentation.game_scene_api import GameSceneApi


class SpeedRequest(BaseModel):
    speed_multiplier: float = Field(..., gt=0)


class MoveRequest(BaseModel):
    direction: str


class InteractRequest(BaseModel):
    target_object_id: int = Field(..., gt=0)


class PollRequest(BaseModel):
    action: str = "poll"
    last_seen_scene_version: int = -1


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _to_jsonable(val) for key, val in asdict(value).items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(val) for key, val in value.items()}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def _build_scene_events_message(
    *,
    scene_api: GameSceneApi,
    scene_id: str,
    last_seen_scene_version: int,
) -> dict[str, Any]:
    events = scene_api.get_scene_events(
        scene_id=scene_id,
        last_seen_scene_version=last_seen_scene_version,
    )
    latest_scene_version = max(
        (event.scene_version for event in events),
        default=last_seen_scene_version,
    )
    return {
        "type": "scene_events",
        "scene_id": scene_id,
        "events": _to_jsonable(events),
        "latest_scene_version": latest_scene_version,
    }


def _parse_last_seen_scene_version(raw_value: str | None) -> int:
    if raw_value is None:
        return -1
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValidationError.from_exception_data(
            title="SceneStreamCursor",
            line_errors=[
                {
                    "type": "int_parsing",
                    "loc": ("last_seen_scene_version",),
                    "input": raw_value,
                }
            ],
        ) from exc


def create_web_app(
    *,
    scene_api: GameSceneApi,
    control_api: GameControlApi,
    lifespan: Any = None,
    cors_allowed_origins: Sequence[str] = (),
) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    if cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(cors_allowed_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.exception_handler(GameSceneNotFoundException)
    async def _handle_scene_not_found(_, exc: GameSceneNotFoundException):
        return JSONResponse(status_code=404, content={"detail": exc.message})

    @app.exception_handler(ManualControlForbiddenException)
    async def _handle_manual_control_forbidden(_, exc: ManualControlForbiddenException):
        return JSONResponse(status_code=403, content={"detail": exc.message})

    @app.exception_handler(SimulationSpeedValidationException)
    async def _handle_speed_validation(_, exc: SimulationSpeedValidationException):
        return JSONResponse(status_code=400, content={"detail": exc.message})

    @app.exception_handler(ApplicationException)
    async def _handle_application_exception(_, exc: ApplicationException):
        return JSONResponse(status_code=400, content={"detail": exc.message})

    @app.exception_handler(MapDomainException)
    async def _handle_map_domain_exception(_, exc: MapDomainException):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/api/scenes/{spot_id}/snapshot")
    async def get_scene_snapshot(spot_id: int):
        snapshot = scene_api.get_scene_snapshot(spot_id)
        return JSONResponse(content=_to_jsonable(snapshot))

    @app.get("/api/world/overview")
    async def get_world_overview():
        overview = scene_api.get_world_overview()
        return JSONResponse(content=_to_jsonable(overview))

    @app.post("/api/control/pause")
    async def pause_simulation():
        control_api.pause(PauseSimulationCommand())
        return Response(status_code=204)

    @app.post("/api/control/resume")
    async def resume_simulation():
        control_api.resume(ResumeSimulationCommand())
        return Response(status_code=204)

    @app.post("/api/control/speed")
    async def set_simulation_speed(request: SpeedRequest):
        control_api.set_speed(
            SetSimulationSpeedCommand(speed_multiplier=float(request.speed_multiplier))
        )
        return Response(status_code=204)

    @app.post("/api/actors/{actor_id}/move")
    async def move_actor(actor_id: int, request: MoveRequest):
        try:
            direction = DirectionEnum[request.direction.upper()]
        except KeyError as exc:
            return JSONResponse(
                status_code=400,
                content={"detail": f"Unknown direction: {request.direction}"},
            )
        result = control_api.move_manual_actor(
            MoveManualActorCommand(
                player_id=actor_id,
                direction=direction,
            )
        )
        return JSONResponse(content=_to_jsonable(result))

    @app.post("/api/actors/{actor_id}/interact")
    async def interact_actor(actor_id: int, request: InteractRequest):
        result = control_api.interact_scene_object(
            InteractSceneObjectCommand(
                player_id=actor_id,
                target_object_id=int(request.target_object_id),
            )
        )
        return JSONResponse(content=_to_jsonable(result))

    @app.websocket("/api/scenes/{scene_id}/stream")
    async def scene_stream(websocket: WebSocket, scene_id: str):
        await websocket.accept()
        try:
            initial_last_seen = _parse_last_seen_scene_version(
                websocket.query_params.get("last_seen_scene_version")
            )
            await websocket.send_json(
                _build_scene_events_message(
                    scene_api=scene_api,
                    scene_id=scene_id,
                    last_seen_scene_version=initial_last_seen,
                )
            )
            while True:
                try:
                    payload = PollRequest(**await websocket.receive_json())
                except ValidationError as exc:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "detail": "Invalid stream request payload.",
                            "errors": exc.errors(),
                        }
                    )
                    continue
                if payload.action == "poll":
                    await websocket.send_json(
                        _build_scene_events_message(
                            scene_api=scene_api,
                            scene_id=scene_id,
                            last_seen_scene_version=payload.last_seen_scene_version,
                        )
                    )
                elif payload.action == "ping":
                    await websocket.send_json({"type": "pong"})
                else:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "detail": f"Unsupported action: {payload.action}",
                        }
                    )
        except ValidationError as exc:
            await websocket.send_json(
                {
                    "type": "error",
                    "detail": "Invalid stream cursor.",
                    "errors": exc.errors(),
                }
            )
            await websocket.close(code=1008)
        except WebSocketDisconnect:
            return

    return app
