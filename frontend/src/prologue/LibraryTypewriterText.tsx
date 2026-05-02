import { useCallback, useEffect, useRef, useState } from "react";
import Typewriter from "typewriter-effect";

export type LibraryTypewriterTextProps = {
  text: string;
  sceneKey: string;
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

/**
 * typewriter-effect を使った表示。`instant` 時は即全文。
 */
export function LibraryTypewriterText({
  text,
  sceneKey,
  instant,
  onTypingComplete,
  className,
}: LibraryTypewriterTextProps) {
  const reducedMotion = usePrefersReducedMotion();
  const completeRef = useRef(false);
  const onDoneRef = useRef(onTypingComplete);

  useEffect(() => {
    onDoneRef.current = onTypingComplete;
  }, [onTypingComplete]);

  useEffect(() => {
    completeRef.current = false;
  }, [sceneKey, text]);

  const handleComplete = useCallback(() => {
    if (completeRef.current) {
      return;
    }
    completeRef.current = true;
    onDoneRef.current();
  }, []);

  useEffect(() => {
    if (instant || reducedMotion) {
      handleComplete();
    }
  }, [instant, reducedMotion, sceneKey, text, handleComplete]);

  if (instant || reducedMotion) {
    return (
      <span className={className} style={{ whiteSpace: "pre-wrap" }}>
        {text}
      </span>
    );
  }

  return (
    <span className={`${className ?? ""} prologue-library-tw`}>
      <Typewriter
        component="span"
        key={sceneKey}
        options={{
          delay: 42,
          cursor: "▍",
          wrapperClassName: "prologue-tw-wrapper",
          cursorClassName: "prologue-tw-cursor",
          skipAddStyles: true,
        }}
        onInit={(typewriter) => {
          typewriter.typeString(text).callFunction(handleComplete).start();
        }}
      />
    </span>
  );
}
