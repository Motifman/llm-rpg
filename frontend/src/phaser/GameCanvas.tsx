import { useEffect, useRef } from "react";
import Phaser from "phaser";

import type { GameSceneSnapshot } from "../types";
import { SceneRenderer } from "./SceneRenderer";

type Props = {
  snapshot: GameSceneSnapshot | null;
  cameraMode: "fixed" | "follow";
  trackedActorId: number | null;
};

export function GameCanvas({ snapshot, cameraMode, trackedActorId }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const gameRef = useRef<Phaser.Game | null>(null);
  const sceneRef = useRef<SceneRenderer | null>(null);

  useEffect(() => {
    if (containerRef.current == null || gameRef.current != null) {
      return;
    }

    const scene = new SceneRenderer();
    sceneRef.current = scene;

    gameRef.current = new Phaser.Game({
      type: Phaser.AUTO,
      parent: containerRef.current,
      width: 960,
      height: 540,
      backgroundColor: "#081310",
      scene: [scene],
      render: {
        antialias: true,
        pixelArt: false,
      },
    });

    return () => {
      gameRef.current?.destroy(true);
      gameRef.current = null;
      sceneRef.current = null;
    };
  }, []);

  useEffect(() => {
    sceneRef.current?.setSnapshot(snapshot);
  }, [snapshot]);

  useEffect(() => {
    sceneRef.current?.setCameraMode(cameraMode, trackedActorId);
  }, [cameraMode, trackedActorId]);

  return <div className="game-canvas" ref={containerRef} />;
}
