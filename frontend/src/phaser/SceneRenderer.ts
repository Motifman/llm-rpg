import Phaser from "phaser";

import type { GameSceneSnapshot, SceneActor, SceneMonster } from "../types";
import {
  buildActorAnimationName,
  buildCatalogAnimationKey,
  buildTextureKey,
  resolveTileFrame,
  resolveTilesetManifestKey,
  type AnimationCatalogEntry,
  type AssetManifest,
  type ObjectManifestEntry,
  type TilesetManifestEntry,
} from "./assetCatalog";
import {
  getActorPalette,
  getFacingAngleDegrees,
  getWeatherOverlayStyle,
} from "./sceneVisuals";
import {
  getStringObjectProperty,
  isRenderableObject,
  type TiledDocument,
  type TiledObject,
} from "./tiledMap";

type CameraMode = "fixed" | "follow";

type RenderableEntity = {
  display_name: string;
  tile_x: number;
  tile_y: number;
  facing: string;
  sprite_key: string;
  state: string;
  is_manual_controlled?: boolean;
  actor_kind?: string;
};

type ActorSprite = {
  body: Phaser.GameObjects.Container;
  shadow: Phaser.GameObjects.Ellipse;
  label: Phaser.GameObjects.Text;
  visual: Phaser.GameObjects.GameObject;
  animationSprite: Phaser.GameObjects.Sprite | null;
  marker: Phaser.GameObjects.Triangle | null;
  idleTween: Phaser.Tweens.Tween | null;
  moveTween: Phaser.Tweens.Tween | null;
  shadowTween: Phaser.Tweens.Tween | null;
  labelTween: Phaser.Tweens.Tween | null;
  squashTween: Phaser.Tweens.Tween | null;
  actor: RenderableEntity;
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

  private monsterSprites = new Map<number, ActorSprite>();

  private mapGraphics?: Phaser.GameObjects.Graphics;

  private overlayGraphics?: Phaser.GameObjects.Graphics;

  private mapTileImages: Phaser.GameObjects.Image[] = [];

  private objectImages: Phaser.GameObjects.Image[] = [];

  private gatewayLabels: Phaser.GameObjects.Text[] = [];

  private tiledMapCache = new Map<string, TiledDocument>();

  private assetManifest: AssetManifest | null = null;

  private animationCatalog: Record<string, AnimationCatalogEntry> | null = null;

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
    await this.ensureAssetCatalogs();
    await this.ensureSceneAssets(tiledMap);
    this.drawMap(tiledMap);
    this.syncActors();
    this.syncMonsters();
    this.applyWeatherOverlay();
    this.applyCameraMode();
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

  private async ensureAssetCatalogs(): Promise<void> {
    if (this.assetManifest != null && this.animationCatalog != null) {
      return;
    }

    const [manifestResponse, animationResponse] = await Promise.all([
      fetch("/assets/catalogs/asset_manifest.json"),
      fetch("/assets/catalogs/animation_catalog.json"),
    ]);
    if (!manifestResponse.ok) {
      throw new Error("Failed to load asset manifest.");
    }
    if (!animationResponse.ok) {
      throw new Error("Failed to load animation catalog.");
    }

    this.assetManifest = (await manifestResponse.json()) as AssetManifest;
    this.animationCatalog = (await animationResponse.json()) as Record<string, AnimationCatalogEntry>;
  }

  private async ensureSceneAssets(mapDocument: TiledDocument): Promise<void> {
    if (this.sceneSnapshot == null || this.assetManifest == null || this.animationCatalog == null) {
      return;
    }

    const queuedLoads: Array<(loader: Phaser.Loader.LoaderPlugin) => void> = [];

    const tilesetKey = resolveTilesetManifestKey(this.assetManifest, this.sceneSnapshot.map);
    if (tilesetKey != null) {
      const tilesetEntry = this.assetManifest.tilesets?.[tilesetKey];
      if (tilesetEntry != null) {
        this.queueTilesetLoad(tilesetKey, tilesetEntry, queuedLoads);
      }
    }

    for (const actor of this.sceneSnapshot.actors) {
      const animationEntry = this.animationCatalog[actor.sprite_key];
      if (animationEntry != null) {
        this.queueActorLoad(actor.sprite_key, animationEntry, queuedLoads);
      }
    }
    for (const monster of this.sceneSnapshot.monsters) {
      const animationEntry = this.animationCatalog[monster.sprite_key];
      if (animationEntry != null) {
        this.queueActorLoad(monster.sprite_key, animationEntry, queuedLoads);
      }
    }

    for (const object of this.collectRenderableMapObjects(mapDocument)) {
      const assetKey = getStringObjectProperty(object, "asset_key");
      const objectEntry =
        assetKey == null ? null : this.assetManifest.objects?.[assetKey] ?? null;
      if (assetKey == null || objectEntry == null) {
        continue;
      }
      this.queueObjectLoad(assetKey, objectEntry, queuedLoads);
    }

    if (queuedLoads.length > 0) {
      await this.runLoader((loader) => {
        queuedLoads.forEach((configure) => configure(loader));
      });
    }

    this.registerAnimationsForCurrentScene();
  }

  private queueTilesetLoad(
    tilesetKey: string,
    tilesetEntry: TilesetManifestEntry,
    queuedLoads: Array<(loader: Phaser.Loader.LoaderPlugin) => void>,
  ): void {
    const textureKey = buildTextureKey("tileset", tilesetKey);
    if (this.textures.exists(textureKey)) {
      return;
    }
    queuedLoads.push((loader) => {
      loader.spritesheet(textureKey, tilesetEntry.image, {
        frameWidth: tilesetEntry.tile_width,
        frameHeight: tilesetEntry.tile_height,
      });
    });
  }

  private queueActorLoad(
    actorSpriteKey: string,
    animationEntry: AnimationCatalogEntry,
    queuedLoads: Array<(loader: Phaser.Loader.LoaderPlugin) => void>,
  ): void {
    const textureKey = buildTextureKey("actor", actorSpriteKey);
    if (this.textures.exists(textureKey)) {
      return;
    }
    queuedLoads.push((loader) => {
      loader.spritesheet(textureKey, animationEntry.image, {
        frameWidth: animationEntry.frame_width,
        frameHeight: animationEntry.frame_height,
      });
    });
  }

  private queueObjectLoad(
    assetKey: string,
    objectEntry: ObjectManifestEntry,
    queuedLoads: Array<(loader: Phaser.Loader.LoaderPlugin) => void>,
  ): void {
    const textureKey = buildTextureKey("object", assetKey);
    if (this.textures.exists(textureKey)) {
      return;
    }
    queuedLoads.push((loader) => {
      loader.image(textureKey, objectEntry.image);
    });
  }

  private collectRenderableMapObjects(mapDocument: TiledDocument): TiledObject[] {
    const objects: TiledObject[] = [];
    for (const layer of mapDocument.layers) {
      if (layer.type !== "objectgroup" || layer.objects == null || layer.visible === false) {
        continue;
      }
      for (const object of layer.objects) {
        if (isRenderableObject(object)) {
          objects.push(object);
        }
      }
    }
    return objects;
  }

  private registerAnimationsForCurrentScene(): void {
    if (this.sceneSnapshot == null || this.animationCatalog == null) {
      return;
    }

    for (const actor of this.sceneSnapshot.actors) {
      const entry = this.animationCatalog[actor.sprite_key];
      if (entry == null) {
        continue;
      }
      const textureKey = buildTextureKey("actor", actor.sprite_key);
      if (!this.textures.exists(textureKey)) {
        continue;
      }
      for (const [animationName, clip] of Object.entries(entry.animations)) {
        const animationKey = buildCatalogAnimationKey(actor.sprite_key, animationName);
        if (this.anims.exists(animationKey)) {
          continue;
        }
        this.anims.create({
          key: animationKey,
          frames: clip.frames.map((frame) => ({ key: textureKey, frame })),
          frameRate: clip.frame_rate,
          repeat: clip.repeat,
        });
      }
    }
  }

  private runLoader(configure: (loader: Phaser.Loader.LoaderPlugin) => void): Promise<void> {
    return new Promise((resolve, reject) => {
      const onComplete = () => {
        cleanup();
        resolve();
      };
      const onError = (file: Phaser.Loader.File) => {
        cleanup();
        reject(new Error(`Failed to load asset: ${file.src}`));
      };
      const cleanup = () => {
        this.load.off(Phaser.Loader.Events.COMPLETE, onComplete);
        this.load.off(Phaser.Loader.Events.FILE_LOAD_ERROR, onError);
      };

      this.load.once(Phaser.Loader.Events.COMPLETE, onComplete);
      this.load.once(Phaser.Loader.Events.FILE_LOAD_ERROR, onError);
      configure(this.load);
      this.load.start();
    });
  }

  private drawMap(mapDocument: TiledDocument): void {
    this.mapGraphics?.clear();
    this.destroyMapImages();

    const tileWidth = mapDocument.tilewidth || DEFAULT_TILE_SIZE;
    const tileHeight = mapDocument.tileheight || DEFAULT_TILE_SIZE;
    const width = mapDocument.width * tileWidth;
    const height = mapDocument.height * tileHeight;
    const tilesetKey =
      this.assetManifest == null || this.sceneSnapshot == null
        ? null
        : resolveTilesetManifestKey(this.assetManifest, this.sceneSnapshot.map);
    const tilesetEntry =
      tilesetKey == null ? null : this.assetManifest?.tilesets?.[tilesetKey] ?? null;
    const tilesetTextureKey =
      tilesetKey == null ? null : buildTextureKey("tileset", tilesetKey);

    for (const layer of mapDocument.layers) {
      if (layer.visible === false) {
        continue;
      }
      if (layer.type === "tilelayer" && layer.data != null) {
        layer.data.forEach((gid, index) => {
          const x = (index % mapDocument.width) * tileWidth;
          const y = Math.floor(index / mapDocument.width) * tileHeight;
          if (
            gid > 0 &&
            tilesetEntry != null &&
            tilesetTextureKey != null &&
            this.textures.exists(tilesetTextureKey)
          ) {
            const tileImage = this.add
              .image(x, y, tilesetTextureKey, resolveTileFrame(tilesetEntry, gid))
              .setOrigin(0, 0)
              .setAlpha(layer.opacity ?? 1)
              .setDepth(y);
            this.mapTileImages.push(tileImage);
          } else {
            this.drawFallbackTile(gid, x, y, tileWidth, tileHeight, layer.opacity ?? 1);
          }
        });
      }
      if (layer.type === "objectgroup" && layer.objects != null) {
        for (const object of layer.objects) {
          const objectHeight = object.height ?? tileHeight;
          const objectWidth = object.width ?? tileWidth;
          const drawY = object.y - objectHeight;

          this.maybeRenderObjectSprite(object);

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

    this.renderGatewayLabels();
    this.cameras.main.setBounds(0, 0, width, height);
  }

  private drawFallbackTile(
    gid: number,
    x: number,
    y: number,
    tileWidth: number,
    tileHeight: number,
    opacity: number,
  ): void {
    this.mapGraphics?.fillStyle(TILE_COLORS[gid] ?? 0x20322b, opacity);
    this.mapGraphics?.fillRect(x, y, tileWidth, tileHeight);
    this.mapGraphics?.lineStyle(1, 0x1a2823, 0.35);
    this.mapGraphics?.strokeRect(x, y, tileWidth, tileHeight);
    this.mapGraphics?.fillStyle(0xffffff, 0.025);
    this.mapGraphics?.fillRect(x, y, tileWidth, tileHeight / 4);
  }

  private maybeRenderObjectSprite(object: TiledObject): void {
    if (this.assetManifest == null || !isRenderableObject(object)) {
      return;
    }
    const assetKey = getStringObjectProperty(object, "asset_key");
    const objectEntry =
      assetKey == null ? null : this.assetManifest.objects?.[assetKey] ?? null;
    if (assetKey == null || objectEntry == null) {
      return;
    }
    const textureKey = buildTextureKey("object", assetKey);
    if (!this.textures.exists(textureKey)) {
      return;
    }

    const objectWidth = object.width ?? objectEntry.width;
    const objectHeight = object.height ?? objectEntry.height;
    const objectImage = this.add
      .image(object.x + objectWidth / 2, object.y, textureKey)
      .setOrigin(0.5, 1)
      .setDisplaySize(objectWidth, objectHeight)
      .setDepth(object.y);
    this.objectImages.push(objectImage);
  }

  private renderGatewayLabels(): void {
    if (this.sceneSnapshot == null) {
      return;
    }

    for (const gateway of this.sceneSnapshot.gateways) {
      const { x, y } = this.toPixel(gateway.tile_x, gateway.tile_y);
      this.mapGraphics?.lineStyle(3, 0xffd166, 1);
      this.mapGraphics?.strokeCircle(x, y, 12);
      this.mapGraphics?.fillStyle(0xffd166, 0.18);
      this.mapGraphics?.fillCircle(x, y, 12);

      const label = this.add
        .text(x, y - 18, gateway.target_spot_name, {
          fontFamily: "Georgia, serif",
          fontSize: "10px",
          color: "#ffe8a3",
          backgroundColor: "#20322bcc",
          padding: { left: 4, right: 4, top: 2, bottom: 2 },
        })
        .setOrigin(0.5, 1)
        .setDepth(y + 4);
      this.gatewayLabels.push(label);
    }
  }

  private destroyMapImages(): void {
    this.mapTileImages.forEach((image) => image.destroy());
    this.mapTileImages = [];
    this.objectImages.forEach((image) => image.destroy());
    this.objectImages = [];
    this.gatewayLabels.forEach((label) => label.destroy());
    this.gatewayLabels = [];
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

  private syncMonsters(): void {
    if (this.sceneSnapshot == null) {
      return;
    }
    const nextIds = new Set(this.sceneSnapshot.monsters.map((monster) => monster.monster_id));
    for (const [monsterId, sprite] of this.monsterSprites.entries()) {
      if (!nextIds.has(monsterId)) {
        this.destroyActorSprite(sprite);
        this.monsterSprites.delete(monsterId);
      }
    }
    for (const monster of this.sceneSnapshot.monsters) {
      const existing = this.monsterSprites.get(monster.monster_id);
      if (existing == null) {
        this.monsterSprites.set(monster.monster_id, this.createActorSprite(monster));
        continue;
      }
      this.updateActorSprite(existing, monster);
    }
  }

  private createActorSprite(actor: RenderableEntity): ActorSprite {
    const { x, y } = this.toPixel(actor.tile_x, actor.tile_y);
    const shadow = this.add.ellipse(x, y + 12, 22, 8, 0x050505, 0.28).setDepth(y - 1);
    const { visual, animationSprite, marker } = this.createActorVisual(actor);
    const body = this.add.container(x, y, [visual]).setDepth(y);
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
      visual,
      animationSprite,
      marker,
      idleTween: null,
      moveTween: null,
      shadowTween: null,
      labelTween: null,
      squashTween: null,
      actor,
    };
    actorSprite.idleTween = this.createIdleTween(actorSprite);
    this.syncActorAnimation(actorSprite, actor);
    return actorSprite;
  }

  private updateActorSprite(sprite: ActorSprite, actor: RenderableEntity): void {
    const nextPosition = this.toPixel(actor.tile_x, actor.tile_y);
    const moved =
      Math.round(sprite.body.x) !== nextPosition.x || Math.round(sprite.body.y) !== nextPosition.y;
    const moveDuration = this.getMoveDurationMs(actor);

    sprite.idleTween?.stop();
    sprite.idleTween = null;
    sprite.moveTween?.stop();
    sprite.moveTween = null;
    sprite.shadowTween?.stop();
    sprite.shadowTween = null;
    sprite.labelTween?.stop();
    sprite.labelTween = null;
    sprite.squashTween?.stop();
    sprite.squashTween = null;
    this.tweens.killTweensOf(sprite.body);
    this.tweens.killTweensOf(sprite.shadow);
    this.tweens.killTweensOf(sprite.label);

    if (moved) {
      sprite.actor = {
        ...actor,
        state: "walking",
      };
      this.syncActorAnimation(sprite, sprite.actor);
      sprite.moveTween = this.tweens.add({
        targets: sprite.body,
        x: nextPosition.x,
        y: nextPosition.y,
        duration: moveDuration,
        ease: "Sine.InOut",
        onComplete: () => {
          sprite.body.setPosition(nextPosition.x, nextPosition.y);
          sprite.body.setScale(1, 1);
          sprite.actor = {
            ...actor,
            state: "idle",
          };
          this.syncActorAnimation(sprite, sprite.actor);
          sprite.idleTween = this.createIdleTween(sprite);
        },
      });
      sprite.squashTween = this.tweens.add({
        targets: sprite.body,
        scaleY: { from: 0.96, to: 1.02 },
        scaleX: { from: 1.04, to: 0.98 },
        duration: moveDuration,
        ease: "Sine.InOut",
        yoyo: true,
      });
      sprite.shadowTween = this.tweens.add({
        targets: sprite.shadow,
        x: nextPosition.x,
        y: nextPosition.y + 12,
        duration: moveDuration,
        ease: "Sine.InOut",
      });
      this.tweens.add({
        targets: sprite.shadow,
        scaleX: { from: 1.1, to: 0.92 },
        alpha: { from: 0.18, to: 0.32 },
        duration: moveDuration,
        ease: "Sine.InOut",
        yoyo: true,
      });
      sprite.labelTween = this.tweens.add({
        targets: sprite.label,
        x: nextPosition.x,
        y: nextPosition.y - 22,
        duration: moveDuration,
        ease: "Sine.Out",
      });
    } else {
      sprite.body.setPosition(nextPosition.x, nextPosition.y);
      sprite.shadow.setPosition(nextPosition.x, nextPosition.y + 12);
      sprite.label.setPosition(nextPosition.x, nextPosition.y - 22);
      sprite.body.setScale(1, 1);
      sprite.actor = {
        ...actor,
        state: actor.state ?? "idle",
      };
      this.syncActorAnimation(sprite, sprite.actor);
      sprite.idleTween = this.createIdleTween(sprite);
    }

    sprite.label.setText(actor.display_name);
    sprite.body.setDepth(nextPosition.y);
    sprite.shadow.setDepth(nextPosition.y - 1);
    sprite.label.setDepth(nextPosition.y + 1);
    this.refreshFallbackActorVisual(sprite, actor);
    this.applyCameraMode();
  }

  private createActorVisual(actor: RenderableEntity): {
    visual: Phaser.GameObjects.GameObject;
    animationSprite: Phaser.GameObjects.Sprite | null;
    marker: Phaser.GameObjects.Triangle | null;
  } {
    const catalogEntry = this.animationCatalog?.[actor.sprite_key] ?? null;
    const textureKey = buildTextureKey("actor", actor.sprite_key);

    if (catalogEntry != null && this.textures.exists(textureKey)) {
      const sprite = this.add.sprite(0, 0, textureKey, 0);
      sprite.setOrigin(catalogEntry.anchor?.x ?? 0.5, catalogEntry.anchor?.y ?? 0.9);
      return {
        visual: sprite,
        animationSprite: sprite,
        marker: null,
      };
    }

    const palette = getActorPalette(actor);
    const marker = this.createFacingMarker(actor);
    const placeholder = this.add.container(0, 0, [
      this.add.rectangle(0, 6, 14, 10, palette.outlineColor, 0.88),
      this.add.rectangle(0, -2, 18, 18, palette.bodyColor, 1),
      this.add.rectangle(-2, -6, 8, 6, palette.accentColor, 0.8),
      marker,
    ]);
    return {
      visual: placeholder,
      animationSprite: null,
      marker,
    };
  }

  private refreshFallbackActorVisual(sprite: ActorSprite, actor: RenderableEntity): void {
    if (sprite.animationSprite != null || sprite.marker == null) {
      return;
    }
    sprite.marker.setRotation(Phaser.Math.DegToRad(getFacingAngleDegrees(actor.facing)));
  }

  private syncActorAnimation(sprite: ActorSprite, actor: RenderableEntity): void {
    if (sprite.animationSprite == null) {
      return;
    }
    const animationName = buildActorAnimationName(actor);
    const animationKey = buildCatalogAnimationKey(actor.sprite_key, animationName);
    if (!this.anims.exists(animationKey)) {
      return;
    }
    if (sprite.animationSprite.anims.currentAnim?.key !== animationKey) {
      sprite.animationSprite.play(animationKey, true);
    }
  }

  private createFacingMarker(actor: RenderableEntity): Phaser.GameObjects.Triangle {
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
        camera.setZoom(1);
        return;
      }
    }

    camera.stopFollow();
    camera.setZoom(1);
    camera.centerOn(mapWidth / 2, mapHeight / 2);
  }

  private getMoveDurationMs(actor: RenderableEntity): number {
    const state = actor.state?.toLowerCase() ?? "";
    if (state === "walking") {
      return 140;
    }
    return DEFAULT_MOVE_DURATION_MS;
  }

  private destroyActorSprite(sprite: ActorSprite): void {
    sprite.idleTween?.stop();
    sprite.moveTween?.stop();
    sprite.shadowTween?.stop();
    sprite.labelTween?.stop();
    sprite.squashTween?.stop();
    sprite.body.destroy();
    sprite.shadow.destroy();
    sprite.label.destroy();
    sprite.marker?.destroy();
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
