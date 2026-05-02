import { useEffect, useRef, useState } from "react";

export type CustomTypewriterTextProps = {
  text: string;
  /** シーンが変わるたびに変えるとアニメーションがリセットされる */
  sceneKey: string;
  /** true なら即全文表示（クリックスキップ用） */
  instant: boolean;
  onTypingComplete: () => void;
  className?: string;
};

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() =>
    window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

function delayForChar(char: string): number {
  if (/[。．、，!！?？…]/.test(char)) {
    return 90 + Math.random() * 140;
  }
  if (/[ 　\n]/.test(char)) {
    return 18 + Math.random() * 40;
  }
  return 22 + Math.random() * 38;
}

/**
 * 依存なしのタイプライター表示。句読点で一拍、軽いランダム遅延。
 */
export function CustomTypewriterText({
  text,
  sceneKey,
  instant,
  onTypingComplete,
  className,
}: CustomTypewriterTextProps) {
  const reducedMotion = usePrefersReducedMotion();
  const [visibleCount, setVisibleCount] = useState(0);
  const completeRef = useRef(false);
  const onDoneRef = useRef(onTypingComplete);
  const timeoutRef = useRef<number | null>(null);

  useEffect(() => {
    onDoneRef.current = onTypingComplete;
  }, [onTypingComplete]);

  useEffect(() => {
    completeRef.current = false;
    setVisibleCount(0);
  }, [sceneKey, text]);

  useEffect(() => {
    if (timeoutRef.current != null) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }

    const finish = () => {
      if (completeRef.current) {
        return;
      }
      completeRef.current = true;
      onDoneRef.current();
    };

    if (instant || reducedMotion) {
      setVisibleCount(text.length);
      finish();
      return;
    }

    let index = 0;
    const step = () => {
      if (index >= text.length) {
        finish();
        return;
      }
      index += 1;
      setVisibleCount(index);
      if (index >= text.length) {
        finish();
        return;
      }
      const nextChar = text[index] ?? "";
      timeoutRef.current = window.setTimeout(step, delayForChar(nextChar));
    };

    const first = text[0];
    timeoutRef.current = window.setTimeout(
      step,
      first != null ? delayForChar(first) : 0,
    );

    return () => {
      if (timeoutRef.current != null) {
        window.clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
    };
  }, [text, sceneKey, instant, reducedMotion]);

  const visible = text.slice(0, visibleCount);
  const done = visibleCount >= text.length;

  return (
    <span className={className} style={{ whiteSpace: "pre-wrap" }}>
      {visible}
      {!done ? (
        <span className="prologue-cursor" aria-hidden>
          ▍
        </span>
      ) : null}
    </span>
  );
}
