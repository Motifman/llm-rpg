"""WebSocket handler for real-time game event streaming."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from ai_rpg_world.presentation.spot_graph_game.dependencies import get_runtime_manager


class GameEventBroadcaster:
    """Manages WebSocket connections for a game session and broadcasts events.

    Clients connect via ``/api/sessions/{session_id}/events`` and receive
    JSON messages of type ``GameEventMessage``.
    """

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(session_id, []).append(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        conns = self._connections.get(session_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self._connections.pop(session_id, None)

    async def broadcast(self, session_id: str, message: dict[str, Any]) -> None:
        conns = self._connections.get(session_id, [])
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(session_id, ws)

    def session_has_listeners(self, session_id: str) -> bool:
        return bool(self._connections.get(session_id))


broadcaster = GameEventBroadcaster()


async def game_event_websocket(websocket: WebSocket, session_id: str) -> None:
    """WebSocket endpoint handler.

    Protocol:
    - Server pushes ``{"type": "game_event", ...}`` whenever game state changes
    - Client can send ``{"action": "ping"}`` → server replies ``{"type": "pong"}``
    - Client can send ``{"action": "set_speed", "speed_multiplier": 0.5}``
    """
    await broadcaster.connect(session_id, websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"type": "error", "detail": "Invalid JSON"}
                )
                continue

            action = payload.get("action", "")
            if action == "ping":
                await websocket.send_json({"type": "pong"})
            elif action == "set_speed":
                multiplier = payload.get("speed_multiplier", 1.0)
                manager = get_runtime_manager()
                manager.set_session_speed(session_id, float(multiplier))
                await websocket.send_json(
                    {"type": "speed_changed", "speed_multiplier": multiplier}
                )
            else:
                await websocket.send_json(
                    {"type": "error", "detail": f"Unknown action: {action}"}
                )
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.disconnect(session_id, websocket)
