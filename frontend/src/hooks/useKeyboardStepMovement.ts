import { useEffect, useRef } from "react";

const INITIAL_REPEAT_DELAY_MS = 220;
const REPEAT_INTERVAL_MS = 120;

const KEY_DIRECTION_MAP: Record<string, string> = {
  ArrowUp: "north",
  w: "north",
  W: "north",
  ArrowDown: "south",
  s: "south",
  S: "south",
  ArrowLeft: "west",
  a: "west",
  A: "west",
  ArrowRight: "east",
  d: "east",
  D: "east",
};

type UseKeyboardStepMovementArgs = {
  enabled: boolean;
  actorId: number | null;
  onMove: (actorId: number, direction: string) => Promise<void>;
};

export function resolveDirectionFromKey(key: string): string | null {
  return KEY_DIRECTION_MAP[key] ?? null;
}

export function useKeyboardStepMovement({
  enabled,
  actorId,
  onMove,
}: UseKeyboardStepMovementArgs): void {
  const moveCallbackRef = useRef(onMove);
  const activeDirectionRef = useRef<string | null>(null);
  const repeatTimerRef = useRef<number | null>(null);
  const delayTimerRef = useRef<number | null>(null);
  const isBusyRef = useRef(false);

  moveCallbackRef.current = onMove;

  useEffect(() => {
    if (!enabled || actorId == null) {
      clearTimers(delayTimerRef.current, repeatTimerRef.current);
      activeDirectionRef.current = null;
      return;
    }

    const step = async (direction: string) => {
      if (isBusyRef.current) {
        return;
      }
      isBusyRef.current = true;
      try {
        await moveCallbackRef.current(actorId, direction);
      } finally {
        isBusyRef.current = false;
      }
    };

    const stopCurrentDirection = () => {
      activeDirectionRef.current = null;
      clearTimers(delayTimerRef.current, repeatTimerRef.current);
      delayTimerRef.current = null;
      repeatTimerRef.current = null;
    };

    const startDirection = (direction: string) => {
      if (activeDirectionRef.current === direction) {
        return;
      }
      stopCurrentDirection();
      activeDirectionRef.current = direction;
      void step(direction);
      delayTimerRef.current = window.setTimeout(() => {
        repeatTimerRef.current = window.setInterval(() => {
          void step(direction);
        }, REPEAT_INTERVAL_MS);
      }, INITIAL_REPEAT_DELAY_MS);
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      const direction = resolveDirectionFromKey(event.key);
      if (direction == null) {
        return;
      }
      event.preventDefault();
      startDirection(direction);
    };

    const handleKeyUp = (event: KeyboardEvent) => {
      const direction = resolveDirectionFromKey(event.key);
      if (direction == null) {
        return;
      }
      if (activeDirectionRef.current === direction) {
        stopCurrentDirection();
      }
    };

    const handleWindowBlur = () => {
      stopCurrentDirection();
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    window.addEventListener("blur", handleWindowBlur);
    return () => {
      stopCurrentDirection();
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
      window.removeEventListener("blur", handleWindowBlur);
    };
  }, [actorId, enabled]);
}

function clearTimers(
  delayTimer: number | null,
  repeatTimer: number | null,
): void {
  if (delayTimer != null) {
    window.clearTimeout(delayTimer);
  }
  if (repeatTimer != null) {
    window.clearInterval(repeatTimer);
  }
}
