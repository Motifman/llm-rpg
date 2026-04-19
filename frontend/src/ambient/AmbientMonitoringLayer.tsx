import { useEffect, useMemo, useState } from "react";

import { TITLE_HUD_LINES } from "../title/titleHudLines";

import "./AmbientMonitoringLayer.css";

const GATE_SILHOUETTE_SRC = "/assets/prologue/gate_girl.png";

export type AmbientMonitoringLayerProps = {
  /** タイトルはやや控えめ、ワールド選択は背景が濃いのでわずかに強める */
  variant?: "title" | "world";
  className?: string;
};

function buildLogBlocks(lines: readonly string[], repeats: number): string[] {
  const out: string[] = [];
  for (let r = 0; r < repeats; r += 1) {
    for (const line of lines) {
      out.push(line);
    }
  }
  return out;
}

/** エラー系キーワード＋列ごとの位相で「たまに」アラート色 */
const LOG_ALERT_RE =
  /\b(error|fatal|fail|fault|breach|refused|lost|reset|unstable|rejected)\b|timed\s*out/i;

function ambientLogLineClass(line: string, index: number, column: "a" | "b"): string {
  const phase = column === "b" ? 3 : 0;
  const occasional = (index * 7 + phase) % 23 === 5 || (index * 11 + phase) % 31 === 13;
  const alert = LOG_ALERT_RE.test(line) || occasional;
  return [
    "ambient-log-line",
    !alert && column === "b" ? "ambient-log-line--col-b" : "",
    alert ? "ambient-log-line--alert" : "",
  ]
    .filter(Boolean)
    .join(" ");
}

export function AmbientMonitoringLayer({
  variant = "world",
  className,
}: AmbientMonitoringLayerProps) {
  const ecgGradientId = useMemo(
    () => `ambient-ecg-grad-${Math.random().toString(36).slice(2, 11)}`,
    [],
  );
  const ecgGradientIdB = useMemo(
    () => `ambient-ecg-grad-b-${Math.random().toString(36).slice(2, 11)}`,
    [],
  );
  const [reduceMotion, setReduceMotion] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduceMotion(mq.matches);
    const onChange = () => setReduceMotion(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const logA = useMemo(() => buildLogBlocks(TITLE_HUD_LINES, 4), []);
  const logB = useMemo(() => {
    const rotated = [...TITLE_HUD_LINES.slice(10), ...TITLE_HUD_LINES.slice(0, 10)];
    return buildLogBlocks(rotated, 4);
  }, []);

  const rootClass = [
    "ambient-root",
    variant === "title" ? "ambient-root--title" : "ambient-root--world",
    reduceMotion ? "ambient-root--static" : "",
    className ?? "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={rootClass} aria-hidden>
      <div className="ambient-grid" />

      <div className="ambient-log-ribbon">
        <div className="ambient-log-col ambient-log-col--a">
          <div className="ambient-log-track">
            {logA.map((line, i) => (
              <div key={`a1-${i}`} className={ambientLogLineClass(line, i, "a")}>
                {line}
              </div>
            ))}
            {logA.map((line, i) => (
              <div key={`a2-${i}`} className={ambientLogLineClass(line, i, "a")}>
                {line}
              </div>
            ))}
          </div>
        </div>
        <div className="ambient-log-col ambient-log-col--b">
          <div className="ambient-log-track">
            {logB.map((line, i) => (
              <div key={`b1-${i}`} className={ambientLogLineClass(line, i, "b")}>
                {line}
              </div>
            ))}
            {logB.map((line, i) => (
              <div key={`b2-${i}`} className={ambientLogLineClass(line, i, "b")}>
                {line}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="ambient-monitor ambient-monitor--tr">
        <div className="ambient-monitor-chrome">
          <span className="ambient-monitor-dots" aria-hidden>
            <span />
            <span />
            <span />
          </span>
          <span className="ambient-monitor-label">SUBJECT_TRACE / CAM_04</span>
        </div>
        <div className="ambient-monitor-body">
          <img
            alt=""
            className="ambient-monitor-silhouette"
            decoding="async"
            src={GATE_SILHOUETTE_SRC}
          />
          <div className="ambient-monitor-scan" />
        </div>
        <div className="ambient-monitor-footer">
          <span className="ambient-monitor-tag">SIG: unstable</span>
          <span className="ambient-monitor-tag">FRAME: interlaced</span>
        </div>
      </div>

      <div className="ambient-charts ambient-charts--br">
        <div className="ambient-chart-row ambient-chart-row--pies">
          <div className="ambient-chart ambient-chart--pie" title="">
            <div className="ambient-pie-ring ambient-pie-ring--a" />
            <span className="ambient-chart-cap">ALLOC</span>
          </div>
          <div className="ambient-chart ambient-chart--pie" title="">
            <div className="ambient-pie-ring ambient-pie-ring--b" />
            <span className="ambient-chart-cap">SYNC</span>
          </div>
        </div>

        <div className="ambient-chart ambient-chart--title-gauges">
          <span className="ambient-chart-cap">UPLINK</span>
          <div className="ambient-title-gauges">
            <div className="ambient-gauge-track">
              <div className="ambient-gauge-fill ambient-gauge-fill--0" />
            </div>
            <div className="ambient-gauge-track">
              <div className="ambient-gauge-fill ambient-gauge-fill--1" />
            </div>
            <div className="ambient-gauge-track">
              <div className="ambient-gauge-fill ambient-gauge-fill--2" />
            </div>
            <div className="ambient-gauge-track">
              <div className="ambient-gauge-fill ambient-gauge-fill--3" />
            </div>
          </div>
        </div>

        <div className="ambient-chart ambient-chart--bars">
          <div className="ambient-bar ambient-bar--0" />
          <div className="ambient-bar ambient-bar--1" />
          <div className="ambient-bar ambient-bar--2" />
          <div className="ambient-bar ambient-bar--3" />
          <div className="ambient-bar ambient-bar--4" />
          <div className="ambient-bar ambient-bar--5" />
          <span className="ambient-chart-cap">LOAD</span>
        </div>

        <div className="ambient-chart ambient-chart--ecg">
          <svg
            className="ambient-ecg-svg"
            viewBox="0 0 320 48"
            preserveAspectRatio="none"
            aria-hidden
          >
            <defs>
              <linearGradient id={ecgGradientId} x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor="rgba(244,189,103,0)" />
                <stop offset="45%" stopColor="rgba(244,189,103,0.55)" />
                <stop offset="100%" stopColor="rgba(255,180,172,0.35)" />
              </linearGradient>
            </defs>
            <path
              className="ambient-ecg-path ambient-ecg-path--a"
              d="M0,24 H40 L48,24 L52,8 L56,40 L64,24 H88 L96,10 L104,38 L112,24 H140 L148,24 L152,6 L156,42 L164,24 H200 L208,12 L216,36 L224,24 H260 L268,24 L272,14 L276,34 L280,24 H320"
              fill="none"
              stroke={`url(#${ecgGradientId})`}
              strokeWidth="1.25"
              vectorEffect="non-scaling-stroke"
            />
          </svg>
          <span className="ambient-chart-cap">WAVE_A</span>
        </div>

        <div className="ambient-chart ambient-chart--ecg ambient-chart--ecg-b">
          <svg
            className="ambient-ecg-svg"
            viewBox="0 0 320 48"
            preserveAspectRatio="none"
            aria-hidden
          >
            <defs>
              <linearGradient id={ecgGradientIdB} x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor="rgba(255,180,172,0.08)" />
                <stop offset="50%" stopColor="rgba(244,189,103,0.45)" />
                <stop offset="100%" stopColor="rgba(200,90,98,0.4)" />
              </linearGradient>
            </defs>
            <path
              className="ambient-ecg-path ambient-ecg-path--b"
              d="M0,28 H24 L32,28 L38,14 L44,36 L52,28 H76 L84,8 L92,40 L100,28 H128 L136,28 L142,18 L148,34 L154,28 H188 L196,22 L204,38 L212,28 H248 L256,28 L262,12 L268,40 L274,28 H320"
              fill="none"
              stroke={`url(#${ecgGradientIdB})`}
              strokeWidth="1.2"
              vectorEffect="non-scaling-stroke"
            />
          </svg>
          <span className="ambient-chart-cap">WAVE_B</span>
        </div>
      </div>
    </div>
  );
}
