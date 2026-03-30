import { describe, expect, it } from "vitest";

import type { SceneActor } from "../types";
import {
  getActorPalette,
  getFacingAngleDegrees,
  getVisualAnimationState,
  getWeatherOverlayStyle,
} from "./sceneVisuals";

function makeActor(overrides: Partial<SceneActor> = {}): SceneActor {
  return {
    actor_id: 1,
    player_id: 1,
    display_name: "Player 1",
    actor_kind: "player",
    tile_x: 1,
    tile_y: 1,
    facing: "down",
    sprite_key: "player_default",
    is_manual_controlled: false,
    is_llm_controlled: true,
    state: "idle",
    ...overrides,
  };
}

describe("sceneVisuals", () => {
  it("returns manual-control palette for manual actor", () => {
    const palette = getActorPalette(makeActor({ is_manual_controlled: true }));
    expect(palette.bodyColor).toBe(0xf2a65a);
  });

  it("returns world-object palette for non-player objects", () => {
    const palette = getActorPalette(makeActor({ actor_kind: "world_object" }));
    expect(palette.outlineColor).toBe(0x332044);
  });

  it("maps facing to degrees and falls back to down", () => {
    expect(getFacingAngleDegrees("up")).toBe(0);
    expect(getFacingAngleDegrees("right")).toBe(90);
    expect(getFacingAngleDegrees("unknown")).toBe(180);
  });

  it("creates rain and fog overlay styles, and returns null for clear", () => {
    expect(
      getWeatherOverlayStyle({
        weather_type: "RAIN",
        weather_intensity: 0.6,
        weather_overlay_key: "rain_light",
      }),
    ).toMatchObject({
      streakColor: 0xd7edff,
    });
    expect(
      getWeatherOverlayStyle({
        weather_type: "FOG",
        weather_intensity: 0.4,
        weather_overlay_key: "fog_morning",
      }),
    ).toMatchObject({
      streakColor: null,
    });
    expect(getWeatherOverlayStyle(null)).toBeNull();
  });

  it("keeps animation walking only while movement is visually active", () => {
    expect(
      getVisualAnimationState({ movedThisFrame: true, tweenActive: false }),
    ).toBe("walking");
    expect(
      getVisualAnimationState({ movedThisFrame: false, tweenActive: true }),
    ).toBe("walking");
    expect(
      getVisualAnimationState({ movedThisFrame: false, tweenActive: false }),
    ).toBe("idle");
  });
});
