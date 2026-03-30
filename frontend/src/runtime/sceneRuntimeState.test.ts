import { describe, expect, it } from "vitest";

import type { GameSceneSnapshot, MoveResult, SceneDeltaEvent, WorldSceneSummary } from "../types";
import {
  applyManualMoveResult,
  applySceneDeltaEvent,
  shouldAutoSwitchScene,
  updateOverviewForSceneEvent,
} from "./sceneRuntimeState";

function makeSnapshot(overrides: Partial<GameSceneSnapshot> = {}): GameSceneSnapshot {
  return {
    scene_id: "spot-1",
    spot_id: 1,
    spot_name: "Spot 1",
    map: {
      map_asset_key: "spot_1",
      tiled_map_path: "/maps/spot_1.json",
      tile_width: 32,
      tile_height: 32,
      map_width_tiles: 20,
      map_height_tiles: 20,
      collision_layer_name: "collision",
      tileset_keys: ["terrain"],
    },
    camera: {
      mode: "fixed",
      tracked_actor_id: null,
      viewport_width: 960,
      viewport_height: 540,
    },
    simulation: {
      is_paused: false,
      speed_multiplier: 1,
      current_tick: 10,
    },
    actors: [
      {
        actor_id: 1,
        player_id: 1,
        display_name: "Player 1",
        actor_kind: "player",
        tile_x: 2,
        tile_y: 3,
        facing: "down",
        sprite_key: "player_default",
        is_manual_controlled: true,
        is_llm_controlled: false,
        state: "idle",
        busy_until_tick: null,
      },
    ],
    monsters: [],
    objects: [],
    weather: null,
    gateways: [],
    areas: [],
    ui_logs: [],
    scene_version: 3,
    server_time_ms: 1000,
    ...overrides,
  };
}

function makeOverview(): WorldSceneSummary[] {
  return [
    {
      spot_id: 1,
      scene_id: "spot-1",
      spot_name: "Spot 1",
      actor_count: 1,
      monster_count: 0,
      weather_type: null,
      scene_version: 3,
    },
    {
      spot_id: 2,
      scene_id: "spot-2",
      spot_name: "Spot 2",
      actor_count: 0,
      monster_count: 0,
      weather_type: "RAIN",
      scene_version: 2,
    },
  ];
}

describe("applySceneDeltaEvent", () => {
  it("updates actor movement and walking state", () => {
    const event: SceneDeltaEvent = {
      event_id: "evt-1",
      event_type: "actor_moved",
      scene_id: "spot-1",
      spot_id: 1,
      scene_version: 4,
      emitted_at_ms: 2000,
      payload: {
        actor_id: 1,
        to_tile_x: 4,
        to_tile_y: 5,
        facing: "right",
      },
    };

    const snapshot = applySceneDeltaEvent(makeSnapshot(), event);

    expect(snapshot.actors[0]).toMatchObject({
      tile_x: 4,
      tile_y: 5,
      facing: "right",
      state: "walking",
    });
    expect(snapshot.scene_version).toBe(4);
  });

  it("removes departed actor on actor_removed", () => {
    const event: SceneDeltaEvent = {
      event_id: "evt-2",
      event_type: "actor_removed",
      scene_id: "spot-1",
      spot_id: 1,
      scene_version: 5,
      emitted_at_ms: 2000,
      payload: {
        actor_id: 1,
        target_spot_id: 2,
      },
    };

    const snapshot = applySceneDeltaEvent(makeSnapshot(), event);

    expect(snapshot.actors).toEqual([]);
    expect(snapshot.scene_version).toBe(5);
  });

  it("adds arriving actor details on scene_changed", () => {
    const event: SceneDeltaEvent = {
      event_id: "evt-3",
      event_type: "scene_changed",
      scene_id: "spot-2",
      spot_id: 2,
      scene_version: 8,
      emitted_at_ms: 2000,
      payload: {
        actor_id: 9,
        player_id: 9,
        display_name: "Scout",
        actor_kind: "player",
        landing_tile_x: 7,
        landing_tile_y: 8,
        facing: "left",
        sprite_key: "player_scout",
        is_manual_controlled: false,
        is_llm_controlled: true,
        state: "idle",
        to_spot_id: 2,
      },
    };

    const snapshot = applySceneDeltaEvent(
      makeSnapshot({ scene_id: "spot-2", spot_id: 2, actors: [] }),
      event,
    );

    expect(snapshot.actors).toHaveLength(1);
    expect(snapshot.actors[0]).toMatchObject({
      actor_id: 9,
      display_name: "Scout",
      tile_x: 7,
      tile_y: 8,
      facing: "left",
    });
  });

  it("appends logs with defaults when payload is partial", () => {
    const event: SceneDeltaEvent = {
      event_id: "evt-4",
      event_type: "log_appended",
      scene_id: "spot-1",
      spot_id: 1,
      scene_version: 4,
      emitted_at_ms: 2000,
      payload: {
        message: "hello",
      },
    };

    const snapshot = applySceneDeltaEvent(makeSnapshot(), event);

    expect(snapshot.ui_logs[0]).toEqual({
      level: "info",
      message: "hello",
      related_actor_id: null,
    });
  });

  it("advances simulation tick and clears expired busy actors", () => {
    const event: SceneDeltaEvent = {
      event_id: "evt-7",
      event_type: "tick_advanced",
      scene_id: "spot-1",
      spot_id: 1,
      scene_version: 5,
      emitted_at_ms: 2000,
      payload: {
        current_tick: 12,
      },
    };

    const snapshot = applySceneDeltaEvent(
      makeSnapshot({
        actors: [
          {
            ...makeSnapshot().actors[0],
            state: "walking",
            busy_until_tick: 12,
          },
        ],
      }),
      event,
    );

    expect(snapshot.simulation.current_tick).toBe(12);
    expect(snapshot.actors[0].state).toBe("idle");
    expect(snapshot.actors[0].busy_until_tick).toBeNull();
  });
});

describe("overview updates", () => {
  it("moves actor counts between spots when actor_removed targets another scene", () => {
    const updated = updateOverviewForSceneEvent(makeOverview(), {
      event_id: "evt-5",
      event_type: "actor_removed",
      scene_id: "spot-1",
      spot_id: 1,
      scene_version: 4,
      emitted_at_ms: 1,
      payload: {
        actor_id: 1,
        target_spot_id: 2,
      },
    });

    expect(updated[0].actor_count).toBe(0);
    expect(updated[1].actor_count).toBe(1);
  });

  it("updates weather and scene version for weather changes", () => {
    const updated = updateOverviewForSceneEvent(makeOverview(), {
      event_id: "evt-6",
      event_type: "weather_changed",
      scene_id: "spot-1",
      spot_id: 1,
      scene_version: 9,
      emitted_at_ms: 1,
      payload: {
        weather_type: "FOG",
      },
    });

    expect(updated[0].weather_type).toBe("FOG");
    expect(updated[0].scene_version).toBe(9);
  });
});

describe("applyManualMoveResult", () => {
  it("updates the actor immediately for same-scene movement", () => {
    const snapshot = applyManualMoveResult(makeSnapshot(), {
      success: true,
      player_id: 1,
      player_name: "Player 1",
      from_spot_id: 1,
      from_spot_name: "Spot 1",
      to_spot_id: 1,
      to_spot_name: "Spot 1",
      from_coordinate: { x: 2, y: 3, z: 0 },
      to_coordinate: { x: 3, y: 3, z: 0 },
      moved_at: "2026-03-29T00:00:00",
      busy_until_tick: 14,
      message: "moved",
      error_message: null,
    });

    expect(snapshot.actors[0]).toMatchObject({
      tile_x: 3,
      tile_y: 3,
      state: "walking",
      busy_until_tick: 14,
    });
  });
});

describe("scene switching helpers", () => {
  it("auto-switches follow camera when tracked actor departs", () => {
    const nextSpotId = shouldAutoSwitchScene(
      {
        event_id: "evt-7",
        event_type: "actor_removed",
        scene_id: "spot-1",
        spot_id: 1,
        scene_version: 4,
        emitted_at_ms: 1,
        payload: {
          actor_id: 1,
          target_spot_id: 2,
        },
      },
      {
        trackedActorId: 1,
        cameraMode: "follow",
      },
    );

    expect(nextSpotId).toBe(2);
  });

  it("does not auto-switch for fixed camera or unrelated actor", () => {
    const event: SceneDeltaEvent = {
      event_id: "evt-8",
      event_type: "actor_removed",
      scene_id: "spot-1",
      spot_id: 1,
      scene_version: 4,
      emitted_at_ms: 1,
      payload: {
        actor_id: 2,
        target_spot_id: 2,
      },
    };

    expect(
      shouldAutoSwitchScene(event, { trackedActorId: 1, cameraMode: "follow" }),
    ).toBeNull();
    expect(
      shouldAutoSwitchScene(event, { trackedActorId: 2, cameraMode: "fixed" }),
    ).toBeNull();
  });

  it("removes manually moved actor from stale source snapshot after gateway transition", () => {
    const result: MoveResult = {
      success: true,
      player_id: 1,
      player_name: "Player 1",
      from_spot_id: 1,
      from_spot_name: "Spot 1",
      to_spot_id: 2,
      to_spot_name: "Spot 2",
      from_coordinate: { x: 2, y: 3, z: 0 },
      to_coordinate: { x: 1, y: 1, z: 0 },
      moved_at: "2026-03-28T00:00:00+09:00",
      busy_until_tick: 12,
      message: "Moved",
      error_message: null,
    };

    const snapshot = applyManualMoveResult(makeSnapshot(), result);

    expect(snapshot.actors).toEqual([]);
  });
});
