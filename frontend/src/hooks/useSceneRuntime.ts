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
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectAttemptRef = useRef<number>(0);
  const latestSceneVersionRef = useRef<number>(0);
  const trackedActorIdRef = useRef<number | null>(null);
  const cameraModeRef = useRef<CameraMode>("fixed");
  const [streamNonce, setStreamNonce] = useState(0);

  async function refreshSceneSnapshot(spotId: number): Promise<GameSceneSnapshot> {
    const data = await apiClient.getSceneSnapshot(spotId);
    latestSceneVersionRef.current = data.scene_version;
    setSnapshot(data);
    setErrorMessage(null);
    return data;
  }

  async function refreshOverview(): Promise<void> {
    const data = await apiClient.getWorldOverview();
    setOverview(data);
    setErrorMessage(null);
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
    void refreshSceneSnapshot(selectedSpotId)
      .then((data) => {
        if (!active) {
          return;
        }
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
    if (selectedSpotId == null || connectionState === "open") {
      return;
    }
    let cancelled = false;
    const timer = window.setInterval(() => {
      void refreshSceneSnapshot(selectedSpotId).catch((error: Error) => {
        if (cancelled) {
          return;
        }
        setErrorMessage(error.message);
      });
    }, 1000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [connectionState, selectedSpotId]);

  useEffect(() => {
    if (snapshot == null) {
      return;
    }
    let cancelled = false;
    if (reconnectTimerRef.current != null) {
      window.clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    websocketRef.current?.close();
    setConnectionState("connecting");

    const websocket = apiClient.connectSceneStream(
      snapshot.scene_id,
      latestSceneVersionRef.current,
      {
        onOpen: () => {
          if (cancelled) {
            return;
          }
          reconnectAttemptRef.current = 0;
          setConnectionState("open");
          setErrorMessage(null);
        },
        onMessage: (message: StreamMessage) => {
          if (cancelled) {
            return;
          }
          if (message.type === "scene_events") {
            setConnectionState("open");
            setErrorMessage(null);
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
        onClose: () => {
          if (cancelled) {
            return;
          }
          setConnectionState("closed");
          scheduleReconnect();
        },
        onError: () => {
          if (cancelled) {
            return;
          }
          setConnectionState("error");
          scheduleReconnect();
        },
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
    }, 250);
    const heartbeatTimer = window.setInterval(() => {
      if (websocket.readyState !== WebSocket.OPEN) {
        return;
      }
      websocket.send(JSON.stringify({ action: "ping" }));
    }, 2000);

    function scheduleReconnect() {
      if (reconnectTimerRef.current != null) {
        return;
      }
      const delayMs = Math.min(250 * 2 ** reconnectAttemptRef.current, 2000);
      reconnectAttemptRef.current += 1;
      reconnectTimerRef.current = window.setTimeout(() => {
        reconnectTimerRef.current = null;
        setStreamNonce((current) => current + 1);
      }, delayMs);
    }

    return () => {
      cancelled = true;
      window.clearInterval(pollTimer);
      window.clearInterval(heartbeatTimer);
      if (reconnectTimerRef.current != null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      websocket.close();
      websocketRef.current = null;
    };
  }, [snapshot?.scene_id, streamNonce]);

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
    setErrorMessage(null);
    await refreshSceneSnapshot(result.to_spot_id);
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
