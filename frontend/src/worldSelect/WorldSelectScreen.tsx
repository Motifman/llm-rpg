import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AmbientMonitoringLayer } from "../ambient/AmbientMonitoringLayer";
import "../prologue/PrologueScreen.css";
import { WORLDS, type WorldSummary } from "./worldSelectData";
import "./WorldSelectScreen.css";

const GATE_GIRL_SRC = "/assets/prologue/gate_girl.png";
const SCENE_INTERVAL_MS = 5200;

export type WorldSelectScreenProps = {
  onBack: () => void;
  /** 実験ワールド確定後（キャラ選択など）。未実装の間は省略可 */
  onPickWorld?: (worldId: string) => void;
};

/**
 * 実験（脱出ワールド）選択画面。
 *
 * - カードはやや左寄せ。横に前後ワールドのスリバー（多少覗き見）。
 * - 立ち絵：固定レイヤー＋下クリップ。重なり順は カード < キャラ < 対話パネル。
 * - 全面背景：選択中ワールドの画像をぼんやり敷く。
 * - 下：Prologue 流用の対話バー＋ CTA。
 */
export function WorldSelectScreen({ onBack, onPickWorld }: WorldSelectScreenProps) {
  const [index, setIndex] = useState(0);
  const selected: WorldSummary | undefined = WORLDS[index];

  const goPrev = useCallback(() => {
    setIndex((i) => (i - 1 + WORLDS.length) % WORLDS.length);
  }, []);
  const goNext = useCallback(() => {
    setIndex((i) => (i + 1) % WORLDS.length);
  }, []);

  const handleStart = useCallback(() => {
    if (!selected || !onPickWorld) return;
    onPickWorld(selected.id);
  }, [onPickWorld, selected]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowDown" || e.key === "ArrowRight") {
        e.preventDefault();
        goNext();
      } else if (e.key === "ArrowUp" || e.key === "ArrowLeft") {
        e.preventDefault();
        goPrev();
      } else if (e.key === "Enter") {
        e.preventDefault();
        handleStart();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [goNext, goPrev, handleStart]);

  const onWheel = useCallback(
    (e: React.WheelEvent<HTMLDivElement>) => {
      if (Math.abs(e.deltaY) < 18) return;
      if (e.deltaY > 0) goNext();
      else goPrev();
    },
    [goNext, goPrev],
  );

  if (!selected) return null;

  const worldCount = WORLDS.length;
  const prevWorld = WORLDS[(index - 1 + worldCount) % worldCount];
  const nextWorld = WORLDS[(index + 1) % worldCount];

  return (
    <div className="ws-root" lang="ja">
      <BackgroundLayer world={selected} />
      <AmbientMonitoringLayer variant="world" />

      <div className="ws-shell">
        <header className="ws-chrome">
          <button className="prologue-ts-btn" onClick={onBack} type="button">
            <span className="prologue-ts-btn-icon" aria-hidden>
              arrow_back
            </span>
            <span className="prologue-ts-btn-label">もどる</span>
          </button>
          <div className="ws-chrome-fill" aria-hidden />
          <div className="ws-telemetry" aria-hidden>
            <div>
              <span className="ws-telemetry-k">PROTOCOL</span> EXPERIMENT_SELECT
            </div>
            <div>
              <span className="ws-telemetry-k">SUBJECT</span>{" "}
              {selected.id.toUpperCase()}
            </div>
            <div>
              <span className="ws-telemetry-k">CHANNEL</span> DREAM_LAYER /
              STABLE
            </div>
          </div>
        </header>

        <main className="ws-main">
          <section
            className="ws-reel"
            aria-label="実験ワールドカード"
            onWheel={onWheel}
          >
            <button
              type="button"
              className="ws-reel-nav ws-reel-nav--prev"
              onClick={goPrev}
              aria-label="前のワールドへ"
            >
              <span className="material-symbols-outlined" aria-hidden>
                chevron_left
              </span>
            </button>

            <div className="ws-reel-stage">
              <SidePeek world={prevWorld} dir="prev" />
              <CardStack worlds={WORLDS} activeIndex={index} onSelect={setIndex} />
              <SidePeek world={nextWorld} dir="next" />
              <div className="ws-reel-pager" aria-hidden>
                {String(index + 1).padStart(2, "0")} /{" "}
                {String(WORLDS.length).padStart(2, "0")}
              </div>
            </div>

            <button
              type="button"
              className="ws-reel-nav ws-reel-nav--next"
              onClick={goNext}
              aria-label="次のワールドへ"
            >
              <span className="material-symbols-outlined" aria-hidden>
                chevron_right
              </span>
            </button>
          </section>
        </main>

        <div className="ws-character-layer" aria-hidden>
          <img
            alt=""
            className="ws-character-img"
            decoding="async"
            src={GATE_GIRL_SRC}
          />
        </div>

        <DialogueBar
          contentKey={selected.id}
          line={selected.guideLine}
          onStart={onPickWorld ? handleStart : undefined}
        />
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------- */

type SidePeekProps = { world: WorldSummary; dir: "prev" | "next" };

function SidePeek({ world, dir }: SidePeekProps) {
  return (
    <div
      className={`ws-side-peek ws-side-peek--${dir}`}
      aria-hidden
    >
      <img
        alt=""
        className="ws-side-peek-img"
        decoding="async"
        src={world.imageSrc}
      />
    </div>
  );
}

/* ---------------------------------------------------------------------- */

type BackgroundLayerProps = { world: WorldSummary };

function BackgroundLayer({ world }: BackgroundLayerProps) {
  return (
    <div className="ws-bg" aria-hidden>
      <img
        alt=""
        className="ws-bg-img"
        decoding="async"
        key={world.id}
        src={world.imageSrc}
      />
      <div className="ws-bg-dim" />
      <div className="ws-scanline" />
    </div>
  );
}

/* ---------------------------------------------------------------------- */

type CardStackProps = {
  worlds: WorldSummary[];
  activeIndex: number;
  onSelect: (i: number) => void;
};

function CardStack({ worlds, activeIndex, onSelect }: CardStackProps) {
  const offsetExpr = useMemo(
    () => `translateX(calc(var(--ws-card-slide-step) * ${-activeIndex}))`,
    [activeIndex],
  );
  const stackWidth = useMemo(
    () =>
      `calc(var(--ws-card-slide-step) * ${worlds.length} - var(--ws-card-gap))`,
    [worlds.length],
  );
  return (
    <div className="ws-stack-viewport">
      <ul
        className="ws-stack"
        style={{ transform: offsetExpr, width: stackWidth }}
      >
        {worlds.map((w, i) => {
          const distance = i - activeIndex;
          const state =
            distance === 0
              ? "active"
              : Math.abs(distance) === 1
              ? "near"
              : "far";
          return (
            <li key={w.id} className={`ws-stack-slot ws-stack-slot--${state}`}>
              <WorldCard
                world={w}
                isActive={distance === 0}
                onActivate={() => onSelect(i)}
              />
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/* ---------------------------------------------------------------------- */

type WorldCardProps = {
  world: WorldSummary;
  isActive: boolean;
  onActivate: () => void;
};

function WorldCard({ world, isActive, onActivate }: WorldCardProps) {
  const scenes = world.sceneImages?.length ? world.sceneImages : [world.imageSrc];
  const [sceneIdx, setSceneIdx] = useState(0);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    setSceneIdx(0);
    if (!isActive || scenes.length <= 1) return;
    timerRef.current = window.setInterval(() => {
      setSceneIdx((i) => (i + 1) % scenes.length);
    }, SCENE_INTERVAL_MS);
    return () => {
      if (timerRef.current != null) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [isActive, scenes.length]);

  return (
    <button
      type="button"
      className={isActive ? "ws-card ws-card--active" : "ws-card"}
      onClick={onActivate}
      aria-current={isActive ? "true" : undefined}
      tabIndex={isActive ? 0 : -1}
    >
      <div className="ws-card-media" aria-hidden>
        {scenes.map((src, i) => (
          <img
            key={src + i}
            alt=""
            className={
              i === sceneIdx ? "ws-card-scene ws-card-scene--on" : "ws-card-scene"
            }
            decoding="async"
            src={src}
          />
        ))}
        <div className="ws-card-veil" />
      </div>

      {/* 上端帯：PROTOCOL 行の下にタイトル（大きめ） */}
      <div className="ws-card-strip">
        <span className="ws-card-strip-code">{world.protocolCode}</span>
        <span className="ws-card-strip-title">{world.title}</span>
      </div>

      {isActive ? (
        <div className="ws-card-info">
          <p className="ws-card-subtitle">{world.subtitle}</p>
          <p className="ws-card-desc">{world.shortDescription}</p>
          <div className="ws-card-meta">
            {world.themeTags.map((tag) => (
              <span key={tag} className="ws-chip">
                {tag}
              </span>
            ))}
            <span className="ws-chip ws-chip--difficulty">
              難易度 {world.difficultyLabel}
            </span>
          </div>

          {scenes.length > 1 ? (
            <div className="ws-card-dots" aria-hidden>
              {scenes.map((_, i) => (
                <span
                  key={i}
                  className={
                    i === sceneIdx ? "ws-card-dot ws-card-dot--on" : "ws-card-dot"
                  }
                />
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </button>
  );
}

/* ---------------------------------------------------------------------- */

type DialogueBarProps = {
  /** ワールド切替時に本文フェードを再実行するためのキー */
  contentKey: string;
  line: string;
  onStart?: () => void;
};

function DialogueBar({ contentKey, line, onStart }: DialogueBarProps) {
  return (
    <div className="ws-dialogue">
      <div className="ws-dialogue-shell prologue-text-panel-shell">
        <div className="prologue-panel-titlebar">
          <span className="prologue-panel-title">門前の少女</span>
        </div>
        <div className="prologue-text-panel">
          <div className="prologue-panel-body">
            <div className="prologue-terminal-mark" aria-hidden>
              <span className="prologue-terminal-icon material-symbols-outlined">
                terminal
              </span>
            </div>
            <div className="prologue-body">
              <p className="ws-dialogue-line ws-dialogue-line--enter" key={contentKey}>
                {line}
              </p>
            </div>
          </div>
          <div className="ws-dialogue-actions">
            <button
              type="button"
              className="ws-btn-tertiary"
              onClick={() => {
                /* もう少し考える */
              }}
            >
              もう少し考える
            </button>
            <button
              type="button"
              className="ws-btn-primary"
              onClick={onStart}
              disabled={!onStart}
            >
              <span className="ws-btn-primary-jp">実験を開始する</span>
              <span className="ws-btn-primary-en">INITIATE EXPERIMENT</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
