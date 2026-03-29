import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useSceneRuntime } from "./useSceneRuntime";

const apiClientMock = vi.hoisted(() => ({
  getWorldOverview: vi.fn(),
  getSceneSnapshot: vi.fn(),
  moveActor: vi.fn(),
  connectSceneStream: vi.fn(),
}));

vi.mock("../api/client", () => ({
  apiClient: apiClientMock,
}));

class MockWebSocket {
  static readonly OPEN = 1;
  static readonly CLOSED = 3;

  readyState = MockWebSocket.OPEN;
  onopen?: () => void;
  onmessage?: (event: { data: string }) => void;
  onclose?: () => void;
  onerror?: () => void;
  sentMessages: string[] = [];

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }

  send(message: string) {
    this.sentMessages.push(message);
  }

  emitOpen() {
    this.onopen?.();
  }

  emitMessage(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }

  emitClose() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }
}

function makeOverview() {
  return [
    {
      spot_id: 1,
      scene_id: "spot-1",
      spot_name: "Starter Town",
      actor_count: 1,
      monster_count: 0,
      weather_type: "CLEAR",
      scene_version: 0,
    },
  ];
}

function makeSnapshot() {
  return {
    scene_id: "spot-1",
    spot_id: 1,
    spot_name: "Starter Town",
    map: {
      map_asset_key: "spot_1",
      tiled_map_path: "/maps/spot_1.json",
      tile_width: 32,
      tile_height: 32,
      map_width_tiles: 4,
      map_height_tiles: 4,
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
      current_tick: 100,
    },
    actors: [
      {
        actor_id: 1,
        player_id: 1,
        display_name: "Hero",
        actor_kind: "player",
        tile_x: 0,
        tile_y: 0,
        facing: "right",
        sprite_key: "player_default",
        is_manual_controlled: true,
        is_llm_controlled: false,
        state: "idle",
        busy_until_tick: null,
      },
    ],
    monsters: [],
    weather: { weather_type: "CLEAR", weather_intensity: 0, weather_overlay_key: null },
    gateways: [],
    areas: [],
    ui_logs: [],
    scene_version: 0,
    server_time_ms: 0,
  };
}

describe("useSceneRuntime", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    apiClientMock.getWorldOverview.mockResolvedValue(makeOverview());
    apiClientMock.getSceneSnapshot.mockResolvedValue(makeSnapshot());
    apiClientMock.moveActor.mockResolvedValue({
      success: true,
      player_id: 1,
      player_name: "Hero",
      from_spot_id: 1,
      from_spot_name: "Starter Town",
      to_spot_id: 1,
      to_spot_name: "Starter Town",
      from_coordinate: { x: 0, y: 0, z: 0 },
      to_coordinate: { x: 1, y: 0, z: 0 },
      moved_at: "2026-03-29T00:00:00",
      busy_until_tick: 102,
      message: "moved",
      error_message: null,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("reconnects after websocket close and clears error on successful move", async () => {
    const sockets: MockWebSocket[] = [];
    apiClientMock.connectSceneStream.mockImplementation((_, __, handlers) => {
      const socket = new MockWebSocket();
      socket.onopen = handlers.onOpen;
      socket.onmessage = (event) => handlers.onMessage(JSON.parse(event.data));
      socket.onclose = handlers.onClose;
      socket.onerror = handlers.onError;
      sockets.push(socket);
      return socket as unknown as WebSocket;
    });

    const { result } = renderHook(() => useSceneRuntime());

    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current.snapshot?.scene_id).toBe("spot-1");
    expect(sockets).toHaveLength(1);

    act(() => {
      sockets[0].emitOpen();
      sockets[0].emitMessage({
        type: "scene_events",
        scene_id: "spot-1",
        latest_scene_version: 1,
        events: [
          {
            event_id: "evt-1",
            event_type: "tick_advanced",
            scene_id: "spot-1",
            spot_id: 1,
            scene_version: 1,
            emitted_at_ms: 1,
            payload: { current_tick: 101 },
          },
        ],
      });
      sockets[0].emitClose();
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(300);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(apiClientMock.connectSceneStream).toHaveBeenCalledTimes(2);
    expect(sockets[1]).toBeDefined();

    await act(async () => {
      await result.current.moveManualActor(1, "east");
    });

    expect(result.current.errorMessage).toBeNull();
  });
});
