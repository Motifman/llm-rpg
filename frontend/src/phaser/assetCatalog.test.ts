import { describe, expect, it } from "vitest";

import type { SceneActor, SceneMap } from "../types";
import {
  buildActorAnimationName,
  buildCatalogAnimationKey,
  buildTextureKey,
  facingToAnimationDirection,
  resolveTileFrame,
  resolveTilesetManifestKey,
  type AssetManifest,
  type TilesetManifestEntry,
} from "./assetCatalog";

const baseActor: SceneActor = {
  actor_id: 1,
  player_id: 1,
  display_name: "Hero",
  actor_kind: "player",
  tile_x: 0,
  tile_y: 0,
  facing: "south",
  sprite_key: "player_default",
  is_manual_controlled: true,
  is_llm_controlled: false,
  state: "idle",
  busy_until_tick: null,
};

describe("assetCatalog helpers", () => {
  it("maps engine facings to animation directions", () => {
    expect(facingToAnimationDirection("north")).toBe("up");
    expect(facingToAnimationDirection("south")).toBe("down");
    expect(facingToAnimationDirection("west")).toBe("left");
    expect(facingToAnimationDirection("east")).toBe("right");
  });

  it("builds actor animation names from state and facing", () => {
    expect(buildActorAnimationName(baseActor)).toBe("idle_down");
    expect(
      buildActorAnimationName({
        ...baseActor,
        facing: "left",
        state: "walking",
      }),
    ).toBe("walk_left");
  });

  it("creates stable texture and animation keys", () => {
    expect(buildTextureKey("actor", "player_default")).toBe("actor:player_default");
    expect(buildCatalogAnimationKey("player_default", "walk_down")).toBe(
      "player_default:walk_down",
    );
  });

  it("resolves tileset key and frame mapping", () => {
    const manifest: AssetManifest = {
      tilesets: {
        tileset_sbs_town: {
          image: "/tileset.png",
          license: "CC0",
          tile_width: 32,
          tile_height: 32,
          gid_frame_map: { "1": 3, "2": 4 },
        },
      },
    };
    const sceneMap: SceneMap = {
      map_asset_key: "starter",
      tiled_map_path: "/data/maps/spot_1.json",
      tile_width: 32,
      tile_height: 32,
      map_width_tiles: 10,
      map_height_tiles: 10,
      collision_layer_name: "collision",
      tileset_keys: ["tileset_sbs_town"],
    };

    expect(resolveTilesetManifestKey(manifest, sceneMap)).toBe("tileset_sbs_town");
    expect(
      resolveTileFrame(manifest.tilesets!.tileset_sbs_town as TilesetManifestEntry, 2),
    ).toBe(4);
  });
});
