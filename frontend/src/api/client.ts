import type {
  GameSceneSnapshot,
  MoveResult,
  StreamMessage,
  WorldSceneSummary,
} from "../types";

function normalizeBaseUrl(rawValue: string | undefined, fallback: string): string {
  const value = rawValue?.trim() || fallback;
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

const HTTP_BASE_URL = normalizeBaseUrl(
  import.meta.env.VITE_API_BASE_URL,
  "http://127.0.0.1:8000",
);
const WS_BASE_URL = normalizeBaseUrl(
  import.meta.env.VITE_WS_BASE_URL,
  "ws://127.0.0.1:8000",
);

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${HTTP_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null;
    throw new Error(body?.detail || `Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export const apiClient = {
  getWorldOverview(): Promise<WorldSceneSummary[]> {
    return requestJson<WorldSceneSummary[]>("/api/world/overview");
  },

  getSceneSnapshot(spotId: number): Promise<GameSceneSnapshot> {
    return requestJson<GameSceneSnapshot>(`/api/scenes/${spotId}/snapshot`);
  },

  pause(): Promise<void> {
    return fetch(`${HTTP_BASE_URL}/api/control/pause`, { method: "POST" }).then(
      ensureNoContent,
    );
  },

  resume(): Promise<void> {
    return fetch(`${HTTP_BASE_URL}/api/control/resume`, { method: "POST" }).then(
      ensureNoContent,
    );
  },

  setSpeed(speedMultiplier: number): Promise<void> {
    return fetch(`${HTTP_BASE_URL}/api/control/speed`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ speed_multiplier: speedMultiplier }),
    }).then(ensureNoContent);
  },

  moveActor(actorId: number, direction: string): Promise<MoveResult> {
    return requestJson<MoveResult>(`/api/actors/${actorId}/move`, {
      method: "POST",
      body: JSON.stringify({ direction }),
    });
  },

  connectSceneStream(
    sceneId: string,
    lastSeenSceneVersion: number,
    handlers: {
      onMessage: (message: StreamMessage) => void;
      onClose: () => void;
      onError: () => void;
    },
  ): WebSocket {
    const websocket = new WebSocket(
      `${WS_BASE_URL}/api/scenes/${sceneId}/stream?last_seen_scene_version=${lastSeenSceneVersion}`,
    );
    websocket.onmessage = (event) => {
      handlers.onMessage(JSON.parse(event.data) as StreamMessage);
    };
    websocket.onclose = handlers.onClose;
    websocket.onerror = handlers.onError;
    return websocket;
  },
};

async function ensureNoContent(response: Response): Promise<void> {
  if (response.ok) {
    return;
  }
  const body = (await response.json().catch(() => null)) as
    | { detail?: string }
    | null;
  throw new Error(body?.detail || `Request failed: ${response.status}`);
}
