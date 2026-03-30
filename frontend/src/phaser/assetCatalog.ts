import type { SceneMap } from "../types";

export type AnimationClip = {
  frames: number[];
  frame_rate: number;
  repeat: number;
};

export type AnimationCatalogEntry = {
  image: string;
  frame_width: number;
  frame_height: number;
  anchor?: { x: number; y: number };
  animations: Record<string, AnimationClip>;
};

export type TilesetManifestEntry = {
  image: string;
  tsx?: string;
  license: string;
  tile_width: number;
  tile_height: number;
  gid_frame_map?: Record<string, number>;
};

export type ObjectManifestEntry = {
  image: string;
  width: number;
  height: number;
  license: string;
};

export type AssetManifest = {
  actors?: Record<string, Record<string, unknown>>;
  monsters?: Record<string, Record<string, unknown>>;
  objects?: Record<string, ObjectManifestEntry>;
  tilesets?: Record<string, TilesetManifestEntry>;
};

export function facingToAnimationDirection(facing: string): "up" | "down" | "left" | "right" {
  const normalized = facing.toLowerCase();
  if (normalized === "north" || normalized === "up") {
    return "up";
  }
  if (normalized === "south" || normalized === "down") {
    return "down";
  }
  if (normalized === "west" || normalized === "left") {
    return "left";
  }
  return "right";
}

export function buildActorAnimationName(actor: {
  facing: string;
  state: string;
}): string {
  const direction = facingToAnimationDirection(actor.facing);
  const normalizedState = actor.state?.toLowerCase() ?? "idle";
  const mode = normalizedState === "walking" ? "walk" : "idle";
  return `${mode}_${direction}`;
}

export function buildCatalogAnimationKey(spriteKey: string, animationName: string): string {
  return `${spriteKey}:${animationName}`;
}

export function resolveTilesetManifestKey(
  manifest: AssetManifest,
  sceneMap: SceneMap,
): string | null {
  if (sceneMap.tileset_keys.length > 0) {
    const directKey = sceneMap.tileset_keys.find((key) => manifest.tilesets?.[key] != null);
    if (directKey != null) {
      return directKey;
    }
  }
  const keys = Object.keys(manifest.tilesets ?? {});
  return keys[0] ?? null;
}

export function resolveTileFrame(
  tileset: TilesetManifestEntry,
  gid: number,
): number {
  if (gid <= 0) {
    return 0;
  }
  const mappedFrame = tileset.gid_frame_map?.[String(gid)];
  if (mappedFrame != null) {
    return mappedFrame;
  }
  return Math.max(0, gid - 1);
}

export function buildTextureKey(namespace: string, assetKey: string): string {
  return `${namespace}:${assetKey}`;
}
