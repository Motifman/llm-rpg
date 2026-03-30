import type {
  GameSceneSnapshot,
  MoveResult,
  SceneActor,
  SceneDeltaEvent,
  SceneMonster,
  WorldSceneSummary,
} from "../types";

export function applySceneDeltaEvent(
  snapshot: GameSceneSnapshot,
  event: SceneDeltaEvent,
): GameSceneSnapshot {
  if (event.event_type === "actor_moved") {
    const actorId = Number(event.payload.actor_id);
    const updatedActors = snapshot.actors.map((actor) =>
      actor.actor_id === actorId
        ? {
            ...actor,
            tile_x: Number(event.payload.to_tile_x),
            tile_y: Number(event.payload.to_tile_y),
            facing: String(event.payload.facing ?? actor.facing),
            state: "walking",
            busy_until_tick:
              (event.payload.busy_until_tick as number | null | undefined) ??
              actor.busy_until_tick ??
              null,
          }
        : actor,
    );
    return {
      ...snapshot,
      actors: updatedActors,
      scene_version: event.scene_version,
    };
  }

  if (event.event_type === "actor_removed") {
    const actorId = Number(event.payload.actor_id);
    return {
      ...snapshot,
      actors: snapshot.actors.filter((actor) => actor.actor_id !== actorId),
      scene_version: event.scene_version,
    };
  }

  if (event.event_type === "scene_changed") {
    const actor = buildSceneChangedActor(snapshot, event);
    const remainingActors = snapshot.actors.filter(
      (currentActor) => currentActor.actor_id !== actor.actor_id,
    );
    return {
      ...snapshot,
      actors: [...remainingActors, actor],
      scene_version: event.scene_version,
    };
  }

  if (event.event_type === "weather_changed") {
    return {
      ...snapshot,
      weather: {
        weather_type: String(event.payload.weather_type),
        weather_intensity: Number(event.payload.weather_intensity ?? 0),
        weather_overlay_key:
          (event.payload.weather_overlay_key as string | null | undefined) ?? null,
      },
      scene_version: event.scene_version,
    };
  }

  if (event.event_type === "monster_moved") {
    const monsterId = Number(event.payload.monster_id);
    const existingMonster = snapshot.monsters.find((monster) => monster.monster_id === monsterId);
    const nextMonster: SceneMonster = {
      monster_id: monsterId,
      display_name: String(event.payload.display_name ?? existingMonster?.display_name ?? "Monster"),
      tile_x: Number(event.payload.to_tile_x ?? existingMonster?.tile_x ?? 0),
      tile_y: Number(event.payload.to_tile_y ?? existingMonster?.tile_y ?? 0),
      facing: String(event.payload.facing ?? existingMonster?.facing ?? "down"),
      sprite_key: String(event.payload.sprite_key ?? existingMonster?.sprite_key ?? "monster_blob"),
      state: String(event.payload.state ?? existingMonster?.state ?? "walking"),
    };
    return {
      ...snapshot,
      monsters: [
        ...snapshot.monsters.filter((monster) => monster.monster_id !== monsterId),
        nextMonster,
      ],
      scene_version: event.scene_version,
    };
  }

  if (event.event_type === "simulation_paused" || event.event_type === "simulation_resumed") {
    return {
      ...snapshot,
      simulation: {
        ...snapshot.simulation,
        is_paused: Boolean(event.payload.is_paused),
      },
      scene_version: event.scene_version,
    };
  }

  if (event.event_type === "simulation_speed_changed") {
    return {
      ...snapshot,
      simulation: {
        ...snapshot.simulation,
        speed_multiplier: Number(event.payload.speed_multiplier ?? 1),
      },
      scene_version: event.scene_version,
    };
  }

  if (event.event_type === "tick_advanced") {
    const currentTick = Number(event.payload.current_tick ?? snapshot.simulation.current_tick);
    return {
      ...snapshot,
      simulation: {
        ...snapshot.simulation,
        current_tick: currentTick,
      },
      actors: snapshot.actors.map((actor) => ({
        ...actor,
        state:
          actor.busy_until_tick != null && actor.busy_until_tick > currentTick
            ? actor.state
            : "idle",
        busy_until_tick:
          actor.busy_until_tick != null && actor.busy_until_tick > currentTick
            ? actor.busy_until_tick
            : null,
      })),
      monsters: snapshot.monsters.map((monster) => ({
        ...monster,
        state: monster.state === "walking" ? "idle" : monster.state,
      })),
      scene_version: event.scene_version,
    };
  }

  if (event.event_type === "log_appended") {
    return {
      ...snapshot,
      ui_logs: [
        ...snapshot.ui_logs,
        {
          level: String(event.payload.level ?? "info"),
          message: String(event.payload.message ?? ""),
          related_actor_id:
            (event.payload.related_actor_id as number | null | undefined) ?? null,
        },
      ],
      scene_version: event.scene_version,
    };
  }

  return {
    ...snapshot,
    scene_version: Math.max(snapshot.scene_version, event.scene_version),
  };
}

export function applyManualMoveResult(
  snapshot: GameSceneSnapshot,
  result: MoveResult,
): GameSceneSnapshot {
  const actorId = result.player_id;
  if (result.from_spot_id === snapshot.spot_id && result.to_spot_id === snapshot.spot_id) {
    return {
      ...snapshot,
      actors: snapshot.actors.map((actor) =>
        actor.actor_id === actorId
          ? {
              ...actor,
              tile_x: result.to_coordinate.x,
              tile_y: result.to_coordinate.y,
              state: "walking",
              busy_until_tick: result.busy_until_tick,
            }
          : actor,
      ),
    };
  }

  if (result.from_spot_id !== snapshot.spot_id) {
    return snapshot;
  }
  return {
    ...snapshot,
    actors: snapshot.actors.filter((actor) => actor.actor_id !== actorId),
  };
}

export function updateOverviewForSceneEvent(
  overview: WorldSceneSummary[],
  event: SceneDeltaEvent,
): WorldSceneSummary[] {
  if (event.event_type === "weather_changed") {
    return overview.map((scene) =>
      scene.spot_id === event.spot_id
        ? {
            ...scene,
            weather_type: String(event.payload.weather_type ?? scene.weather_type),
            scene_version: Math.max(scene.scene_version, event.scene_version),
          }
        : scene,
    );
  }

  if (event.event_type === "actor_removed") {
    const targetSpotId = Number(event.payload.target_spot_id ?? NaN);
    return overview.map((scene) => {
      if (scene.spot_id === event.spot_id) {
        return {
          ...scene,
          actor_count: Math.max(0, scene.actor_count - 1),
          scene_version: Math.max(scene.scene_version, event.scene_version),
        };
      }
      if (!Number.isNaN(targetSpotId) && scene.spot_id === targetSpotId) {
        return {
          ...scene,
          actor_count: scene.actor_count + 1,
        };
      }
      return scene;
    });
  }

  if (event.event_type === "scene_changed") {
    return overview.map((scene) =>
      scene.spot_id === event.spot_id
        ? {
            ...scene,
            scene_version: Math.max(scene.scene_version, event.scene_version),
          }
        : scene,
    );
  }

  if (event.event_type === "actor_moved") {
    return overview.map((scene) =>
      scene.spot_id === event.spot_id
        ? {
            ...scene,
            scene_version: Math.max(scene.scene_version, event.scene_version),
          }
        : scene,
    );
  }

  return overview;
}

export function shouldAutoSwitchScene(
  event: SceneDeltaEvent,
  options: {
    trackedActorId: number | null;
    cameraMode: "fixed" | "follow";
  },
): number | null {
  const { trackedActorId, cameraMode } = options;
  if (cameraMode !== "follow" || trackedActorId == null) {
    return null;
  }
  const actorId = Number(event.payload.actor_id ?? NaN);
  if (actorId !== trackedActorId) {
    return null;
  }
  const nextSpotId = Number(event.payload.target_spot_id ?? event.payload.to_spot_id ?? NaN);
  return Number.isNaN(nextSpotId) ? null : nextSpotId;
}

function buildSceneChangedActor(
  snapshot: GameSceneSnapshot,
  event: SceneDeltaEvent,
): SceneActor {
  const actorId = Number(event.payload.actor_id);
  const existing = snapshot.actors.find((actor) => actor.actor_id === actorId);
  return {
    actor_id: actorId,
    player_id: coerceNumberOrNull(event.payload.player_id, existing?.player_id ?? actorId),
    display_name: String(event.payload.display_name ?? existing?.display_name ?? `Actor ${actorId}`),
    actor_kind: String(event.payload.actor_kind ?? existing?.actor_kind ?? "player"),
    tile_x: Number(event.payload.landing_tile_x ?? existing?.tile_x ?? 0),
    tile_y: Number(event.payload.landing_tile_y ?? existing?.tile_y ?? 0),
    facing: String(event.payload.facing ?? existing?.facing ?? "down"),
    sprite_key: String(event.payload.sprite_key ?? existing?.sprite_key ?? "unknown_actor"),
    is_manual_controlled: Boolean(
      event.payload.is_manual_controlled ?? existing?.is_manual_controlled ?? false,
    ),
    is_llm_controlled: Boolean(
      event.payload.is_llm_controlled ?? existing?.is_llm_controlled ?? true,
    ),
    state: String(event.payload.state ?? existing?.state ?? "idle"),
    busy_until_tick:
      coerceNumberOrNull(event.payload.busy_until_tick, existing?.busy_until_tick ?? null) ?? null,
  };
}

function coerceNumberOrNull(
  value: unknown,
  fallback: number | null,
): number | null {
  if (value == null) {
    return fallback;
  }
  const numericValue = Number(value);
  return Number.isNaN(numericValue) ? fallback : numericValue;
}
