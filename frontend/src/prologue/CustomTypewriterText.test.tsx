import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CustomTypewriterText } from "./CustomTypewriterText";

function mockMotionPreference(reduced: boolean): void {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: reduced,
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  });
}

describe("CustomTypewriterText", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockMotionPreference(false);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("shows full text immediately when instant", () => {
    const onTypingComplete = vi.fn();
    render(
      <CustomTypewriterText
        instant
        sceneKey="s1"
        text="即時表示テスト"
        onTypingComplete={onTypingComplete}
      />,
    );
    expect(screen.getByText("即時表示テスト").textContent).toContain("即時表示テスト");
    expect(onTypingComplete).toHaveBeenCalledTimes(1);
  });

  it("types out text over time then completes", () => {
    const onTypingComplete = vi.fn();
    render(
      <CustomTypewriterText
        instant={false}
        sceneKey="s2"
        text="ab"
        onTypingComplete={onTypingComplete}
      />,
    );
    expect(screen.queryByText("ab")).toBeNull();
    act(() => {
      vi.runAllTimers();
    });
    expect(screen.getByText("ab").textContent).toContain("ab");
    expect(onTypingComplete).toHaveBeenCalledTimes(1);
  });
});
