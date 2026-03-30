import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  resolveDirectionFromKey,
  useKeyboardStepMovement,
} from "./useKeyboardStepMovement";

describe("resolveDirectionFromKey", () => {
  it("maps arrow keys and WASD", () => {
    expect(resolveDirectionFromKey("ArrowUp")).toBe("north");
    expect(resolveDirectionFromKey("a")).toBe("west");
    expect(resolveDirectionFromKey("D")).toBe("east");
  });

  it("returns null for unsupported keys", () => {
    expect(resolveDirectionFromKey("Enter")).toBeNull();
  });
});

describe("useKeyboardStepMovement", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("issues an immediate step and repeats while a movement key is held", async () => {
    const onMove = vi.fn().mockResolvedValue(undefined);
    renderHook(() =>
      useKeyboardStepMovement({
        enabled: true,
        actorId: 7,
        onMove,
      }),
    );

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowRight" }));
    await vi.runOnlyPendingTimersAsync();
    expect(onMove).toHaveBeenCalledWith(7, "east");

    await vi.advanceTimersByTimeAsync(350);
    expect(onMove.mock.calls.length).toBeGreaterThanOrEqual(2);

    window.dispatchEvent(new KeyboardEvent("keyup", { key: "ArrowRight" }));
    const callsAfterRelease = onMove.mock.calls.length;
    await vi.advanceTimersByTimeAsync(300);
    expect(onMove).toHaveBeenCalledTimes(callsAfterRelease);
  });

  it("does nothing when disabled or actor id is missing", async () => {
    const onMove = vi.fn().mockResolvedValue(undefined);
    renderHook(() =>
      useKeyboardStepMovement({
        enabled: false,
        actorId: null,
        onMove,
      }),
    );

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "w" }));
    await vi.advanceTimersByTimeAsync(500);
    expect(onMove).not.toHaveBeenCalled();
  });

  it("does not start duplicate intervals for repeated keydown events", async () => {
    const onMove = vi.fn().mockResolvedValue(undefined);
    renderHook(() =>
      useKeyboardStepMovement({
        enabled: true,
        actorId: 5,
        onMove,
      }),
    );

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowUp" }));
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowUp" }));
    await vi.advanceTimersByTimeAsync(260);

    expect(onMove.mock.calls.length).toBeLessThanOrEqual(2);
  });
});
