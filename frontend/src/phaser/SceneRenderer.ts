import Phaser from "phaser";

import type { GameSceneSnapshot, SceneActor } from "../types";
import {
  getActorPalette,
  getFacingAngleDegrees,
  getWeatherOverlayStyle,
} from "./sceneVisuals";

type CameraMode = "fixed" | "follow";

type ActorSprite = {
  body: Phaser.GameObjects.Container;
  shadow: Phaser.GameObjects.Ellipse;
  label: Phaser.GameObjects.Text;
  marker: Phaser.GameObjects.Triangle;
  idleTween: Phaser.Tweens.Tween | null;
  actor: SceneActor;
};

type TiledLayer = {
  id: number;
  name: string;
  type: "tilelayer" | "objectgroup";
  data?: number[];
  width?: number;
  height?: number;
  visible?: boolean;
  opacity?: number;
  objects?: Array<{
    id: number;
    name: string;
    type: string;
    x: number;
    y: number;
    width?: number;
    height?: number;
  }>;
};

type TiledDocument = {
  width: number;
  height: number;
  tilewidth: number;
  tileheight: number;
  layers: TiledLayer[];
};

const DEFAULT_TILE_SIZE = 32;
const DEFAULT_MOVE_DURATION_MS = 180;
const TILE_COLORS: Record<number, number> = {
  0: 0x000000,
  1: 0x355c4f,
  2: 0x4b7a60,
  3: 0x8f6b43,
  4: 0x2f4158,
};

export class SceneRenderer extends Phaser.Scene {
  private sceneSnapshot: GameSceneSnapshot | null = null;

  private actorSprites = new Map<number, ActorSprite>();

  private mapGraphics?: Phaser.GameObjects.Graphics;

  private overlayGraphics?: Phaser.GameObjects.Graphics;

  private hudLabel?: Phaser.GameObjects.Text;

  private tiledMapCache = new Map<string, TiledDocument>();

  private cameraMode: CameraMode = "fixed";

  private trackedActorId: number | null = null;

  constructor() {
    super("scene-renderer");
  }

  setSnapshot(snapshot: GameSceneSnapshot | null): void {
    this.sceneSnapshot = snapshot;
    if (!this.sys.isActive()) {
      return;
    }
    void this.renderScene();
  }

  setCameraMode(mode: CameraMode, trackedActorId: number | null): void {
    this.cameraMode = mode;
    this.trackedActorId = trackedActorId;
    if (!this.sys.isActive()) {
      return;
    }
    this.applyCameraMode();
  }

  create(): void {
    this.cameras.main.setBackgroundColor("#081310");
    this.mapGraphics = this.add.graphics();
    this.overlayGraphics = this.add.graphics().setDepth(900).setAlpha(0);
    this.hudLabel = this.add
      .text(12, 12, "", {
        fontFamily: "Georgia, serif",
        fontSize: "16px",
        color: "#f8f3dc",
      })
      .setScrollFactor(0)
      .setDepth(1000);
    void this.renderScene();
  }

  private async renderScene(): Promise<void> {
    if (
      this.sceneSnapshot == null ||
      this.mapGraphics == null ||
      this.overlayGraphics == null
    ) {
      return;
    }

    const tiledMap = await this.loadTiledMap(this.sceneSnapshot.map.tiled_map_path);
    this.drawMap(tiledMap);
    this.syncActors();
    this.applyWeatherOverlay();
    this.applyCameraMode();

    this.hudLabel?.setText(
      `${this.sceneSnapshot.spot_name} | ${this.cameraMode.toUpperCase()} | Weather: ${
        this.sceneSnapshot.weather?.weather_type ?? "CLEAR"
      }`,
    );
  }

  private async loadTiledMap(mapPath: string): Promise<TiledDocument> {
    if (this.tiledMapCache.has(mapPath)) {
      return this.tiledMapCache.get(mapPath)!;
    }
    const response = await fetch(mapPath);
    if (!response.ok) {
      throw new Error(`Failed to load map: ${mapPath}`);
    }
    const document = (await response.json()) as TiledDocument;
    this.tiledMapCache.set(mapPath, document);
    return document;
  }

  private drawMap(mapDocument: TiledDocument): void {
    this.mapGraphics?.clear();
    const tileWidth = mapDocument.tilewidth || DEFAULT_TILE_SIZE;
    const tileHeight = mapDocument.tileheight || DEFAULT_TILE_SIZE;
    const width = mapDocument.width * tileWidth;
    const height = mapDocument.height * tileHeight;

    for (const layer of mapDocument.layers) {
      if (layer.visible === false) {
        continue;
      }
      if (layer.type === "tilelayer" && layer.data != null) {
        layer.data.forEach((gid, index) => {
          const x = (index % mapDocument.width) * tileWidth;
          const y = Math.floor(index / mapDocument.width) * tileHeight;
          this.mapGraphics?.fillStyle(TILE_COLORS[gid] ?? 0x20322b, layer.opacity ?? 1);
          this.mapGraphics?.fillRect(x, y, tileWidth, tileHeight);
          this.mapGraphics?.lineStyle(1, 0x1a2823, 0.35);
          this.mapGraphics?.strokeRect(x, y, tileWidth, tileHeight);
          this.mapGraphics?.fillStyle(0xffffff, 0.025);
          this.mapGraphics?.fillRect(x, y, tileWidth, tileHeight / 4);
        });
      }
      if (layer.type === "objectgroup" && layer.objects != null) {
        for (const object of layer.objects) {
          const objectHeight = object.height ?? tileHeight;
          const objectWidth = object.width ?? tileWidth;
          const drawY = object.y - objectHeight;

          if (object.type === "gateway") {
            this.mapGraphics?.lineStyle(2, 0xf2a65a, 0.95);
            this.mapGraphics?.strokeRect(object.x, drawY, objectWidth, objectHeight);
            this.mapGraphics?.fillStyle(0xf2a65a, 0.12);
            this.mapGraphics?.fillRect(object.x, drawY, objectWidth, objectHeight);
          }
          if (object.type === "area") {
            this.mapGraphics?.lineStyle(2, 0x75c4a4, 0.65);
            this.mapGraphics?.strokeRect(object.x, drawY, objectWidth, objectHeight);
          }
          if (object.type === "collision") {
            this.mapGraphics?.fillStyle(0x090c0f, 0.22);
            this.mapGraphics?.fillRect(object.x, drawY, objectWidth, objectHeight);
          }
        }
      }
    }

    this.cameras.main.setBounds(0, 0, width, height);
  }

  private syncActors(): void {
    if (this.sceneSnapshot == null) {
      return;
    }
    const nextIds = new Set(this.sceneSnapshot.actors.map((actor) => actor.actor_id));

    for (const [actorId, sprite] of this.actorSprites.entries()) {
      if (!nextIds.has(actorId)) {
        this.destroyActorSprite(sprite);
        this.actorSprites.delete(actorId);
      }
    }

    for (const actor of this.sceneSnapshot.actors) {
      const existing = this.actorSprites.get(actor.actor_id);
      if (existing == null) {
        this.actorSprites.set(actor.actor_id, this.createActorSprite(actor));
        continue;
      }
      this.updateActorSprite(existing, actor);
    }
  }

  private createActorSprite(actor: SceneActor): ActorSprite {
    const { x, y } = this.toPixel(actor.tile_x, actor.tile_y);
    const palette = getActorPalette(actor);
    const shadow = this.add.ellipse(x, y + 12, 22, 8, 0x050505, 0.28).setDepth(y - 1);
    const legs = this.add.rectangle(0, 6, 14, 10, palette.outlineColor, 0.88);
    const torso = this.add.rectangle(0, -2, 18, 18, palette.bodyColor, 1);
    const highlight = this.add.rectangle(-2, -6, 8, 6, palette.accentColor, 0.8);
    const marker = this.createFacingMarker(actor);
    const body = this.add.container(x, y, [legs, torso, highlight, marker]).setDepth(y);
    const label = this.add
      .text(x, y - 22, actor.display_name, {
        fontFamily: "Georgia, serif",
        fontSize: "11px",
        color: "#f8f3dc",
      })
      .setOrigin(0.5, 1)
      .setDepth(y + 1);
    const actorSprite: ActorSprite = {
      body,
      shadow,
      label,
      marker,
      idleTween: null,
      actor,
    };
    actorSprite.idleTween = this.createIdleTween(actorSprite);
    return actorSprite;
  }

  private updateActorSprite(sprite: ActorSprite, actor: SceneActor): void {
    const oldPosition = this.toPixel(sprite.actor.tile_x, sprite.actor.tile_y);
    const nextPosition = this.toPixel(actor.tile_x, actor.tile_y);
    const moved = oldPosition.x !== nextPosition.x || oldPosition.y !== nextPosition.y;
    const moveDuration = this.getMoveDurationMs(actor);

    if (moved) {
      sprite.idleTween?.stop();
      this.tweens.add({
        targets: sprite.body,
        x: nextPosition.x,
        y: nextPosition.y,
        scaleY: { from: 0.96, to: 1.02 },
        scaleX: { from: 1.04, to: 0.98 },
        duration: moveDuration,
        ease: "Sine.InOut",
        yoyo: true,
        onComplete: () => {
          sprite.body.setScale(1, 1);
          sprite.idleTween = this.createIdleTween(sprite);
        },
      });
      this.tweens.add({
        targets: sprite.shadow,
        x: nextPosition.x,
        y: nextPosition.y + 12,
        scaleX: { from: 1.1, to: 0.92 },
        alpha: { from: 0.18, to: 0.32 },
        duration: moveDuration,
        ease: "Sine.InOut",
        yoyo: true,
      });
      this.tweens.add({
        targets: sprite.label,
        x: nextPosition.x,
        y: nextPosition.y - 22,
        duration: moveDuration,
        ease: "Sine.Out",
      });
    }

    sprite.label.setText(actor.display_name);
    sprite.body.setDepth(nextPosition.y);
    sprite.shadow.setDepth(nextPosition.y - 1);
    sprite.label.setDepth(nextPosition.y + 1);
    sprite.marker.destroy();
    sprite.marker = this.createFacingMarker(actor);
    const palette = getActorPalette(actor);
    sprite.body.removeAll(true);
    sprite.body.add([
      this.add.rectangle(0, 6, 14, 10, palette.outlineColor, 0.88),
      this.add.rectangle(0, -2, 18, 18, palette.bodyColor, 1),
      this.add.rectangle(-2, -6, 8, 6, palette.accentColor, 0.8),
      sprite.marker,
    ]);
    sprite.actor = {
      ...actor,
      state: moved ? "walking" : "idle",
    };
    this.applyCameraMode();
  }

  private createFacingMarker(actor: SceneActor): Phaser.GameObjects.Triangle {
    const triangle = this.add.triangle(0, -15, 0, 10, 6, -2, -6, -2, 0xffffff);
    triangle.setRotation(Phaser.Math.DegToRad(getFacingAngleDegrees(actor.facing)));
    triangle.setAlpha(0.92);
    return triangle;
  }

  private createIdleTween(sprite: ActorSprite): Phaser.Tweens.Tween {
    return this.tweens.add({
      targets: sprite.body,
      y: sprite.body.y - 1.4,
      duration: 900,
      ease: "Sine.InOut",
      yoyo: true,
      repeat: -1,
    });
  }

  private applyWeatherOverlay(): void {
    if (this.sceneSnapshot == null || this.overlayGraphics == null) {
      return;
    }
    const mapWidth =
      this.sceneSnapshot.map.map_width_tiles *
      (this.sceneSnapshot.map.tile_width || DEFAULT_TILE_SIZE);
    const mapHeight =
      this.sceneSnapshot.map.map_height_tiles *
      (this.sceneSnapshot.map.tile_height || DEFAULT_TILE_SIZE);

    this.overlayGraphics.clear();
    const overlayStyle = getWeatherOverlayStyle(this.sceneSnapshot.weather);
    if (overlayStyle == null) {
      this.tweens.add({
        targets: this.overlayGraphics,
        alpha: 0,
        duration: 220,
        ease: "Sine.Out",
      });
      return;
    }

    this.overlayGraphics.fillStyle(overlayStyle.fillColor, overlayStyle.alpha);
    this.overlayGraphics.fillRect(0, 0, mapWidth, mapHeight);
    if (overlayStyle.streakColor != null) {
      this.overlayGraphics.lineStyle(1, overlayStyle.streakColor, overlayStyle.streakAlpha);
      for (let x = -40; x < mapWidth + 40; x += overlayStyle.streakSpacing) {
        this.overlayGraphics.lineBetween(x, 0, x + 24, mapHeight);
      }
    }
    this.tweens.add({
      targets: this.overlayGraphics,
      alpha: 1,
      duration: 320,
      ease: "Sine.InOut",
    });
  }

  private applyCameraMode(): void {
    if (this.sceneSnapshot == null) {
      return;
    }
    const mapWidth =
      this.sceneSnapshot.map.map_width_tiles *
      (this.sceneSnapshot.map.tile_width || DEFAULT_TILE_SIZE);
    const mapHeight =
      this.sceneSnapshot.map.map_height_tiles *
      (this.sceneSnapshot.map.tile_height || DEFAULT_TILE_SIZE);
    const camera = this.cameras.main;

    if (this.cameraMode === "follow" && this.trackedActorId != null) {
      const actorSprite = this.actorSprites.get(this.trackedActorId);
      if (actorSprite != null) {
        camera.startFollow(actorSprite.body, true, 0.12, 0.12);
        camera.setZoom(1.15);
        return;
      }
    }

    camera.stopFollow();
    camera.setZoom(1);
    camera.centerOn(mapWidth / 2, mapHeight / 2);
  }

  private getMoveDurationMs(actor: SceneActor): number {
    const state = actor.state?.toLowerCase() ?? "";
    if (state === "walking") {
      return 140;
    }
    return DEFAULT_MOVE_DURATION_MS;
  }

  private destroyActorSprite(sprite: ActorSprite): void {
    sprite.idleTween?.stop();
    sprite.body.destroy();
    sprite.shadow.destroy();
    sprite.label.destroy();
    sprite.marker.destroy();
  }

  private toPixel(tileX: number, tileY: number): { x: number; y: number } {
    const tileWidth = this.sceneSnapshot?.map.tile_width ?? DEFAULT_TILE_SIZE;
    const tileHeight = this.sceneSnapshot?.map.tile_height ?? DEFAULT_TILE_SIZE;
    return {
      x: tileX * tileWidth + tileWidth / 2,
      y: tileY * tileHeight + tileHeight / 2,
    };
  }
}
