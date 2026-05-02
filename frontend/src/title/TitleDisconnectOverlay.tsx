import { useEffect, useRef, useState } from "react";

import "./TitleDisconnectOverlay.css";

type LogKind = "info" | "err";

type LogRow = {
  id: number;
  text: string;
  kind: LogKind;
};

const FULL_SCRIPT: Omit<LogRow, "id">[] = [
  { text: "[04:44:09.032] dream_uplink … channel=dream_stack  state=idle", kind: "info" },
  { text: "[04:44:09.041] session_boundary_check … PASS (Mansion_Sim)", kind: "info" },
  { text: "[04:44:09.058] SYNC oneiric_buffer … latency=12ms", kind: "info" },
  { text: "[04:44:09.071] TERMINATE_SESSION requested  source=title_menu", kind: "info" },
  { text: "[04:44:09.084] handshake dream_gateway.instancia … OK", kind: "info" },
  { text: "[04:44:09.102] uplink_quality … RSSI=-38dB  jitter=low", kind: "info" },
  { text: "[04:44:09.128] dream_token … refresh  TTL=440s", kind: "info" },
  { text: "[04:44:09.156] ROUTE egress=client→sessionHost  hops=3", kind: "info" },
  { text: "[04:44:09.201] WARN  memory_fragment drift=0.4% (within band)", kind: "info" },
  { text: "[04:44:09.244] 夢同期スレッド … graceful_stop  enqueue", kind: "info" },
  { text: "[04:44:09.288] audio_bus … drained", kind: "info" },
  { text: "[04:44:09.331] render_pipe … stopping  last_frame=ack", kind: "info" },
  { text: "[04:44:09.402] uplink_keepalive … last ping  ACK", kind: "info" },
  { text: "[04:44:09.467] ERR  uplink stall detected  retry=1/5  host=dream_gateway", kind: "err" },
  { text: "[04:44:09.521] ERR  packet_loss spike  route=ingress→dream_stack", kind: "err" },
  { text: "[04:44:09.584] ERR  heartbeat missed  Δt=820ms", kind: "err" },
  { text: "[04:44:09.641] ERR  TLS session … remote closed (UNKNOWN_CA)", kind: "err" },
  { text: "[04:44:09.702] ERR  pipe broken  errno=EPIPE  peer=dream_gateway", kind: "err" },
  { text: "[04:44:09.766] ERR  stream_reset  code=0xE_CONN_RESET", kind: "err" },
  { text: "[04:44:09.831] ERR  dream_sync … checksum mismatch  frame=last", kind: "err" },
  { text: "[04:44:09.894] ERR  session_host … connection refused (553)", kind: "err" },
  { text: "[04:44:09.958] ERR  cascade_fail  subsystem=DREAM_LINK", kind: "err" },
  { text: "[04:44:10.021] ERR  uplink … circuit_open  cooldown=∞", kind: "err" },
  { text: "[04:44:10.088] ERR  NO_ROUTE_TO_INSTANCIA  resolver=FAIL", kind: "err" },
  { text: "[04:44:10.151] ERR  dream_gateway … host unreachable", kind: "err" },
  { text: "[04:44:10.218] ERR  SYNC_FAILURE  dream_layer detach_forced", kind: "err" },
  { text: "[04:44:10.284] ERR  CONN_LOST  user_presence … evaporating", kind: "err" },
  { text: "[04:44:10.351] ABORT  session … terminated  reason=DREAM_EXIT", kind: "err" },
];

const SHORT_SCRIPT: Omit<LogRow, "id">[] = [
  { text: "[04:44:09] TERMINATE_SESSION … accepted", kind: "info" },
  { text: "[04:44:09] ERR  uplink_reset  host=dream_gateway", kind: "err" },
  { text: "[04:44:09] ERR  dream_sync FAILURE  detach_forced", kind: "err" },
  { text: "[04:44:09] ERR  CONN_LOST", kind: "err" },
  { text: "[04:44:09] ABORT  session=DREAM_EXIT", kind: "err" },
];

type Phase = "stream" | "flash";

export type TitleDisconnectOverlayProps = {
  /** フラッシュ終了後に呼ぶ（例: window.close） */
  onComplete: () => void;
};

function readPrefersReducedMotion(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function assignIds(rows: Omit<LogRow, "id">[]): LogRow[] {
  return rows.map((row, idx) => ({ ...row, id: idx + 1 }));
}

export function TitleDisconnectOverlay({ onComplete }: TitleDisconnectOverlayProps) {
  const reduced = readPrefersReducedMotion();
  const [phase, setPhase] = useState<Phase>("stream");
  const [lines, setLines] = useState<LogRow[]>([]);
  const logRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(0);

  useEffect(() => {
    const script = reduced ? SHORT_SCRIPT : FULL_SCRIPT;
    if (reduced) {
      nextId.current = script.length;
      setLines(assignIds(script));
      const end = window.setTimeout(() => setPhase("flash"), 420);
      return () => window.clearTimeout(end);
    }

    let cancelled = false;
    let i = 0;
    let timeoutId = 0;

    const finishStream = () => {
      timeoutId = window.setTimeout(() => {
        if (!cancelled) {
          setPhase("flash");
        }
      }, 380);
    };

    const tick = () => {
      if (cancelled) {
        return;
      }
      if (i >= script.length) {
        finishStream();
        return;
      }
      const row = script[i];
      i += 1;
      nextId.current += 1;
      setLines((prev) => [...prev, { ...row, id: nextId.current }]);
      timeoutId = window.setTimeout(tick, 82);
    };

    tick();

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [reduced]);

  useEffect(() => {
    const el = logRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [lines]);

  useEffect(() => {
    if (phase !== "flash") {
      return;
    }
    /* アニメーション長に合わせる（TitleDisconnectOverlay.css の @keyframes） */
    const ms = reduced ? 360 : 880;
    const id = window.setTimeout(() => {
      onComplete();
    }, ms);
    return () => window.clearTimeout(id);
  }, [phase, onComplete, reduced]);

  return (
    <div className="ts-disc" role="presentation">
      <div className="ts-disc-scan" aria-hidden />
      <div className="ts-disc-vignette" aria-hidden />

      <header className="ts-disc-head">
        <h2 className="ts-disc-head-k">接続解除中</h2>
        <p className="ts-disc-head-sub">SESSION // TERMINATE · DREAM_UPLINK</p>
      </header>

      <div className="ts-disc-terminal-wrap">
        <div className="ts-disc-terminal">
          <div className="ts-disc-terminal-bar" aria-hidden>
            <span>instancia-cli — zsh — 80×24</span>
            <span>ALERT</span>
          </div>
          <div
            ref={logRef}
            className="ts-disc-log"
            aria-live="polite"
            aria-relevant="additions"
            aria-label="切断ログ"
          >
            <div className="ts-disc-log-inner">
              {lines.map((row) => (
                <p
                  key={row.id}
                  className={
                    row.kind === "err" ? "ts-disc-line ts-disc-line--err" : "ts-disc-line"
                  }
                >
                  {row.text}
                </p>
              ))}
            </div>
          </div>
        </div>
      </div>

      {phase === "flash" ? <div className="ts-disc-flash" aria-hidden /> : null}
    </div>
  );
}
