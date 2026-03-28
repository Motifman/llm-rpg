import { useEffect, useMemo, useRef, useState } from "react";

import { apiClient } from "../api/client";
import type {
  GameSceneSnapshot,
  MoveResult,
  SceneActor,
  StreamMessage,
  WorldSceneSummary,
} from "../types";
import {
  applyManualMoveResult,
  applySceneDeltaEvent,
  shouldAutoSwitchScene,
  updateOverviewForSceneEvent,
} from "../runtime/sceneRuntimeState";

type ConnectionState = "idle" | "connecting" | "open" | "closed" | "error";

type CameraMode = "fixed" | "follow";

export function useSceneRuntime() {
  const [overview, setOverview] = useState<WorldSceneSummary[]>([]);
  const [selectedSpotId, setSelectedSpotId] = useState<number | null>(null);
  const [snapshot, setSnapshot] = useState<GameSceneSnapshot | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const websocketRef = useRef<WebSocket | null>(null);
  const latestSceneVersionRef = useRef<number>(0);
  const trackedActorIdRef = useRef<number | null>(null);
  const cameraModeRef = useRef<CameraMode>("fixed");

  async function refreshOverview(): Promise<void> {
    const data = await apiClient.getWorldOverview();
    setOverview(data);
    if (data.length > 0) {
      setSelectedSpotId((current) => current ?? data[0].spot_id);
    }
  }

  useEffect(() => {
    let active = true;
    void refreshOverview()
      .then(() => {
        if (!active) {
          return;
        }
      })
      .catch((error: Error) => {
        if (!active) {
          return;
        }
        setErrorMessage(error.message);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (selectedSpotId == null) {
      return;
    }
    let active = true;
    setConnectionState("connecting");
    setErrorMessage(null);
    void apiClient
      .getSceneSnapshot(selectedSpotId)
      .then((data) => {
        if (!active) {
          return;
        }
        latestSceneVersionRef.current = data.scene_version;
        setSnapshot(data);
      })
      .catch((error: Error) => {
        if (!active) {
          return;
        }
        setConnectionState("error");
        setErrorMessage(error.message);
      });
    return () => {
      active = false;
    };
  }, [selectedSpotId]);

  useEffect(() => {
    if (snapshot == null) {
      return;
    }
    websocketRef.current?.close();
    setConnectionState("connecting");

    const websocket = apiClient.connectSceneStream(
      snapshot.scene_id,
      latestSceneVersionRef.current,
      {
        onMessage: (message: StreamMessage) => {
          if (message.type === "scene_events") {
            setConnectionState("open");
            latestSceneVersionRef.current = message.latest_scene_version;
            setOverview((currentOverview) =>
              message.events.reduce(updateOverviewForSceneEvent, currentOverview),
            );
            const autoSwitchSpotId = message.events.reduce<number | null>(
              (currentSpotId, event) =>
                currentSpotId ??
                shouldAutoSwitchScene(event, {
                  trackedActorId: trackedActorIdRef.current,
                  cameraMode: cameraModeRef.current,
                }),
              null,
            );
            if (autoSwitchSpotId != null) {
              setSelectedSpotId(autoSwitchSpotId);
            }
            setSnapshot((current) => {
              if (current == null) {
                return current;
              }
              return message.events.reduce(applySceneDeltaEvent, current);
            });
            return;
          }
          if (message.type === "error") {
            setConnectionState("error");
            setErrorMessage(message.detail);
          }
        },
        onClose: () => setConnectionState("closed"),
        onError: () => setConnectionState("error"),
      },
    );
    websocketRef.current = websocket;
    const pollTimer = window.setInterval(() => {
      if (websocket.readyState !== WebSocket.OPEN) {
        return;
      }
      websocket.send(
        JSON.stringify({
          action: "poll",
          last_seen_scene_version: latestSceneVersionRef.current,
        }),
      );
    }, 500);

    return () => {
      window.clearInterval(pollTimer);
      websocket.close();
      websocketRef.current = null;
    };
  }, [snapshot?.scene_id]);

  const manualActor = useMemo<SceneActor | null>(() => {
    if (snapshot == null) {
      return null;
    }
    return (
      snapshot.actors.find((actor) => actor.is_manual_controlled) ??
      snapshot.actors[0] ??
      null
    );
  }, [snapshot]);

  useEffect(() => {
    trackedActorIdRef.current = manualActor?.actor_id ?? null;
  }, [manualActor?.actor_id]);

  const moveManualActor = async (
    actorId: number,
    direction: string,
  ): Promise<MoveResult> => {
    const result = await apiClient.moveActor(actorId, direction);
    setSnapshot((current) =>
      current == null ? current : applyManualMoveResult(current, result),
    );
    if (result.to_spot_id !== result.from_spot_id) {
      if (cameraModeRef.current === "follow" && trackedActorIdRef.current === actorId) {
        setSelectedSpotId(result.to_spot_id);
      }
      void refreshOverview().catch(() => undefined);
    }
    return result;
  };

  const setCameraMode = (mode: CameraMode): void => {
    cameraModeRef.current = mode;
  };

  return {
    connectionState,
    errorMessage,
    manualActor,
    moveManualActor,
    overview,
    setCameraMode,
    selectedSpotId,
    setSelectedSpotId,
    snapshot,
  };
}
