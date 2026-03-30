"""Projection that maintains UI-facing scene state and emits delta envelopes."""

from __future__ import annotations

import copy
import threading
import time
import uuid
from typing import Optional

from ai_rpg_world.application.ui.contracts.dtos import (
    GameSceneDeltaEventDto,
    GameSceneSnapshotDto,
    SceneActorDto,
    SceneLogEntryDto,
    SceneMonsterDto,
    SceneObjectDto,
    SceneWeatherDto,
)
from ai_rpg_world.application.ui.exceptions import GameSceneNotFoundException


class GameSceneProjection:
    """In-memory projection of game scenes for frontend snapshot/delta consumption."""

    def __init__(self) -> None:
        self._snapshots: dict[int, GameSceneSnapshotDto] = {}
        self._lock = threading.RLock()

    def upsert_snapshot(self, snapshot: GameSceneSnapshotDto) -> None:
        with self._lock:
            self._snapshots[snapshot.spot_id] = copy.deepcopy(snapshot)

    def synchronize_snapshot(self, snapshot: GameSceneSnapshotDto) -> None:
        with self._lock:
            existing = self._snapshots.get(snapshot.spot_id)
            if existing is None:
                self._snapshots[snapshot.spot_id] = copy.deepcopy(snapshot)
                return
            existing.scene_id = snapshot.scene_id
            existing.spot_name = snapshot.spot_name
            existing.map = copy.deepcopy(snapshot.map)
            existing.camera = copy.deepcopy(snapshot.camera)
            existing.actors = copy.deepcopy(snapshot.actors)
            existing.monsters = copy.deepcopy(snapshot.monsters)
            existing.objects = copy.deepcopy(snapshot.objects)
            existing.weather = copy.deepcopy(snapshot.weather)
            existing.gateways = copy.deepcopy(snapshot.gateways)
            existing.areas = copy.deepcopy(snapshot.areas)

    def get_snapshot(self, spot_id: int) -> GameSceneSnapshotDto:
        with self._lock:
            snapshot = self._snapshots.get(spot_id)
            if snapshot is None:
                raise GameSceneNotFoundException(spot_id)
            return copy.deepcopy(snapshot)

    def list_snapshots(self) -> list[GameSceneSnapshotDto]:
        with self._lock:
            return [copy.deepcopy(snapshot) for _, snapshot in sorted(self._snapshots.items())]

    def apply_actor_moved(
        self,
        *,
        spot_id: int,
        actor_id: int,
        to_tile_x: int,
        to_tile_y: int,
        facing: str,
        actor_kind: str,
        display_name: str,
        sprite_key: str,
        move_duration_ms: int = 180,
        move_mode: str = "step",
        busy_until_tick: Optional[int] = None,
    ) -> GameSceneDeltaEventDto:
        with self._lock:
            snapshot = self._require_snapshot_mutable(spot_id)
            actor = next((a for a in snapshot.actors if a.actor_id == actor_id), None)
            if actor is None:
                actor = SceneActorDto(
                    actor_id=actor_id,
                    player_id=actor_id if actor_kind == "player" else None,
                    display_name=display_name,
                    actor_kind=actor_kind,
                    tile_x=to_tile_x,
                    tile_y=to_tile_y,
                    facing=facing,
                    sprite_key=sprite_key,
                    is_manual_controlled=False,
                    is_llm_controlled=(actor_kind == "player"),
                    state="walking",
                    busy_until_tick=busy_until_tick,
                )
                snapshot.actors.append(actor)
                from_x = to_tile_x
                from_y = to_tile_y
            else:
                from_x = actor.tile_x
                from_y = actor.tile_y
                actor.tile_x = to_tile_x
                actor.tile_y = to_tile_y
                actor.facing = facing
                actor.state = "walking"
                actor.busy_until_tick = busy_until_tick

            snapshot.scene_version += 1
            return self._make_delta(
                snapshot=snapshot,
                event_type="actor_moved",
                payload={
                    "actor_id": actor_id,
                    "from_tile_x": from_x,
                    "from_tile_y": from_y,
                    "to_tile_x": to_tile_x,
                    "to_tile_y": to_tile_y,
                    "facing": facing,
                    "move_duration_ms": move_duration_ms,
                    "move_mode": move_mode,
                    "busy_until_tick": busy_until_tick,
                },
            )

    def apply_weather_changed(
        self,
        *,
        spot_id: int,
        weather_type: str,
        weather_intensity: float,
        weather_overlay_key: Optional[str],
        transition_ms: int = 300,
    ) -> GameSceneDeltaEventDto:
        with self._lock:
            snapshot = self._require_snapshot_mutable(spot_id)
            snapshot.weather = SceneWeatherDto(
                weather_type=weather_type,
                weather_intensity=weather_intensity,
                weather_overlay_key=weather_overlay_key,
            )
            snapshot.scene_version += 1
            return self._make_delta(
                snapshot=snapshot,
                event_type="weather_changed",
                payload={
                    "weather_type": weather_type,
                    "weather_intensity": weather_intensity,
                    "weather_overlay_key": weather_overlay_key,
                    "transition_ms": transition_ms,
                },
            )

    def apply_monster_moved(
        self,
        *,
        spot_id: int,
        monster_id: int,
        to_tile_x: int,
        to_tile_y: int,
        facing: str,
        display_name: str,
        sprite_key: str,
        state: str = "walking",
    ) -> GameSceneDeltaEventDto:
        with self._lock:
            snapshot = self._require_snapshot_mutable(spot_id)
            monster = next((m for m in snapshot.monsters if m.monster_id == monster_id), None)
            if monster is None:
                monster = SceneMonsterDto(
                    monster_id=monster_id,
                    display_name=display_name,
                    tile_x=to_tile_x,
                    tile_y=to_tile_y,
                    facing=facing,
                    sprite_key=sprite_key,
                    state=state,
                )
                snapshot.monsters.append(monster)
                from_x = to_tile_x
                from_y = to_tile_y
            else:
                from_x = monster.tile_x
                from_y = monster.tile_y
                monster.tile_x = to_tile_x
                monster.tile_y = to_tile_y
                monster.facing = facing
                monster.state = state
            snapshot.scene_version += 1
            return self._make_delta(
                snapshot=snapshot,
                event_type="monster_moved",
                payload={
                    "monster_id": monster_id,
                    "from_tile_x": from_x,
                    "from_tile_y": from_y,
                    "to_tile_x": to_tile_x,
                    "to_tile_y": to_tile_y,
                    "display_name": display_name,
                    "facing": facing,
                    "sprite_key": sprite_key,
                    "state": state,
                },
            )

    def update_object_state(
        self,
        *,
        spot_id: int,
        object_id: int,
        interaction_data: dict[str, object],
        sprite_key: str | None = None,
    ) -> None:
        with self._lock:
            snapshot = self._require_snapshot_mutable(spot_id)
            scene_object = next(
                (obj for obj in snapshot.objects if obj.object_id == object_id),
                None,
            )
            if scene_object is None:
                scene_object = SceneObjectDto(
                    object_id=object_id,
                    display_name=f"Object {object_id}",
                    object_kind="object",
                    tile_x=0,
                    tile_y=0,
                    sprite_key=sprite_key or "object_unknown",
                    interaction_data=dict(interaction_data),
                )
                snapshot.objects.append(scene_object)
            else:
                scene_object.interaction_data = dict(interaction_data)
                if sprite_key is not None:
                    scene_object.sprite_key = sprite_key

    def apply_scene_changed(
        self,
        *,
        actor_id: int,
        from_spot_id: int,
        to_spot_id: int,
        landing_tile_x: int,
        landing_tile_y: int,
        auto_follow_switched: bool,
    ) -> tuple[GameSceneDeltaEventDto, GameSceneDeltaEventDto]:
        with self._lock:
            source = self._require_snapshot_mutable(from_spot_id)
            target = self._require_snapshot_mutable(to_spot_id)
            actor = next((a for a in source.actors if a.actor_id == actor_id), None)
            if actor is None:
                for snapshot in self._snapshots.values():
                    actor = next((a for a in snapshot.actors if a.actor_id == actor_id), None)
                    if actor is not None:
                        break
            source_actor_payload = {
                "actor_id": actor_id,
                "target_spot_id": to_spot_id,
                "landing_tile_x": landing_tile_x,
                "landing_tile_y": landing_tile_y,
                "removal_reason": "scene_transition",
                "auto_follow_switched": auto_follow_switched,
            }
            for snapshot in self._snapshots.values():
                snapshot.actors = [a for a in snapshot.actors if a.actor_id != actor_id]
            if actor is not None:
                actor.tile_x = landing_tile_x
                actor.tile_y = landing_tile_y
                target.actors.append(actor)
            source.scene_version += 1
            target.scene_version += 1
            source_delta = self._make_delta(
                snapshot=source,
                event_type="actor_removed",
                payload=source_actor_payload,
            )
            target_delta = self._make_delta(
                snapshot=target,
                event_type="scene_changed",
                payload={
                    "actor_id": actor_id,
                    "player_id": actor.player_id if actor is not None else None,
                    "display_name": actor.display_name if actor is not None else f"Actor {actor_id}",
                    "actor_kind": actor.actor_kind if actor is not None else "player",
                    "sprite_key": actor.sprite_key if actor is not None else "unknown_actor",
                    "facing": actor.facing if actor is not None else "down",
                    "is_manual_controlled": actor.is_manual_controlled if actor is not None else False,
                    "is_llm_controlled": actor.is_llm_controlled if actor is not None else True,
                    "state": actor.state if actor is not None else "idle",
                    "busy_until_tick": actor.busy_until_tick if actor is not None else None,
                    "from_spot_id": from_spot_id,
                    "to_spot_id": to_spot_id,
                    "landing_tile_x": landing_tile_x,
                    "landing_tile_y": landing_tile_y,
                    "auto_follow_switched": auto_follow_switched,
                },
            )
            return source_delta, target_delta

    def append_log(
        self,
        *,
        spot_id: int,
        level: str,
        message: str,
        related_actor_id: Optional[int] = None,
    ) -> GameSceneDeltaEventDto:
        with self._lock:
            snapshot = self._require_snapshot_mutable(spot_id)
            snapshot.ui_logs.append(
                SceneLogEntryDto(
                    level=level,
                    message=message,
                    related_actor_id=related_actor_id,
                )
            )
            snapshot.scene_version += 1
            return self._make_delta(
                snapshot=snapshot,
                event_type="log_appended",
                payload={
                    "level": level,
                    "message": message,
                    "related_actor_id": related_actor_id,
                },
            )

    def set_simulation_paused(
        self,
        *,
        spot_id: int,
        is_paused: bool,
    ) -> GameSceneDeltaEventDto:
        with self._lock:
            snapshot = self._require_snapshot_mutable(spot_id)
            snapshot.simulation.is_paused = is_paused
            snapshot.scene_version += 1
            return self._make_delta(
                snapshot=snapshot,
                event_type="simulation_paused" if is_paused else "simulation_resumed",
                payload={"is_paused": is_paused},
            )

    def set_simulation_speed(
        self,
        *,
        spot_id: int,
        speed_multiplier: float,
    ) -> GameSceneDeltaEventDto:
        with self._lock:
            snapshot = self._require_snapshot_mutable(spot_id)
            snapshot.simulation.speed_multiplier = float(speed_multiplier)
            snapshot.scene_version += 1
            return self._make_delta(
                snapshot=snapshot,
                event_type="simulation_speed_changed",
                payload={"speed_multiplier": float(speed_multiplier)},
            )

    def advance_simulation_tick(
        self,
        *,
        spot_id: int,
        current_tick: int,
        server_time_ms: int,
    ) -> None:
        with self._lock:
            snapshot = self._require_snapshot_mutable(spot_id)
            snapshot.simulation.current_tick = current_tick
            snapshot.server_time_ms = server_time_ms
            for actor in snapshot.actors:
                if actor.busy_until_tick is not None and actor.busy_until_tick <= current_tick:
                    actor.busy_until_tick = None
                    actor.state = "idle"
                elif actor.state == "walking":
                    actor.state = "idle"

    def set_actor_control_flags(
        self,
        *,
        actor_id: int,
        is_manual_controlled: bool,
        is_llm_controlled: bool,
    ) -> None:
        with self._lock:
            for snapshot in self._snapshots.values():
                for actor in snapshot.actors:
                    if actor.actor_id == actor_id:
                        actor.is_manual_controlled = is_manual_controlled
                        actor.is_llm_controlled = is_llm_controlled

    def _require_snapshot_mutable(self, spot_id: int) -> GameSceneSnapshotDto:
        with self._lock:
            snapshot = self._snapshots.get(spot_id)
            if snapshot is None:
                raise GameSceneNotFoundException(spot_id)
            return snapshot

    @staticmethod
    def _make_delta(
        *,
        snapshot: GameSceneSnapshotDto,
        event_type: str,
        payload: dict,
    ) -> GameSceneDeltaEventDto:
        return GameSceneDeltaEventDto(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            scene_id=snapshot.scene_id,
            spot_id=snapshot.spot_id,
            scene_version=snapshot.scene_version,
            emitted_at_ms=int(time.time() * 1000),
            payload=payload,
        )
