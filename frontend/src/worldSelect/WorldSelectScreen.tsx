import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AmbientMonitoringLayer } from "../ambient/AmbientMonitoringLayer";
import "../prologue/PrologueScreen.css";
import {
  GameButton,
  GameFrameButton,
  GameProtocolButton,
} from "../ui/GameUi";
import {
  DEFAULT_GATE_GIRL_SRC,
  GATE_GIRL_MOMENTS,
  GATE_GIRL_MOMENT_MS,
  GATE_GIRL_SPECIAL_MOMENTS,
  SHOW_GATE_GIRL_HIT_AREAS,
  type GateGirlMoment,
} from "./gateGirlMoments";
import { WORLDS, type WorldSummary } from "./worldSelectData";
import "./WorldSelectScreen.css";

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
 * - 立ち絵：固定レイヤー＋下クリップ。スタックは CSS（カード／矢印は main 側でキャラより手前）。
 * - 全面背景：選択中ワールドの画像をぼんやり敷く。
 * - 下：Prologue 流用の対話バー＋ CTA。
 */
export function WorldSelectScreen({ onBack, onPickWorld }: WorldSelectScreenProps) {
  const [index, setIndex] = useState(0);
  const selected: WorldSummary | undefined = WORLDS[index];

  const [charLayers, setCharLayers] = useState<[string, string]>([
    DEFAULT_GATE_GIRL_SRC,
    DEFAULT_GATE_GIRL_SRC,
  ]);
  const [charVisible, setCharVisible] = useState<0 | 1>(0);
  const charVisibleRef = useRef<0 | 1>(0);
  charVisibleRef.current = charVisible;

  const [pendingCharFade, setPendingCharFade] = useState<0 | 1 | null>(null);
  const [gateMoment, setGateMoment] = useState<GateGirlMoment | null>(null);
  const [dialogueTick, setDialogueTick] = useState(0);
  const gateMomentTimerRef = useRef<number | null>(null);

  const clearGateMomentTimer = useCallback(() => {
    if (gateMomentTimerRef.current != null) {
      window.clearTimeout(gateMomentTimerRef.current);
      gateMomentTimerRef.current = null;
    }
  }, []);

  const applyCharacterSrc = useCallback((targetSrc: string) => {
    setCharLayers((prev) => {
      const v = charVisibleRef.current;
      if (prev[v] === targetSrc) {
        return prev;
      }
      const hidden = (1 - v) as 0 | 1;
      const next: [string, string] = [prev[0], prev[1]];
      next[hidden] = targetSrc;
      queueMicrotask(() => {
        setPendingCharFade(hidden);
      });
      return next;
    });
  }, []);

  useEffect(() => {
    if (pendingCharFade === null) {
      return;
    }
    const id = window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        setCharVisible(pendingCharFade);
        charVisibleRef.current = pendingCharFade;
        setPendingCharFade(null);
      });
    });
    return () => window.cancelAnimationFrame(id);
  }, [pendingCharFade]);

  useEffect(() => {
    const target = gateMoment?.imageSrc ?? DEFAULT_GATE_GIRL_SRC;
    applyCharacterSrc(target);
  }, [gateMoment, applyCharacterSrc]);

  useEffect(() => {
    clearGateMomentTimer();
    setGateMoment(null);
  }, [selected?.id, clearGateMomentTimer]);

  useEffect(() => {
    return () => clearGateMomentTimer();
  }, [clearGateMomentTimer]);

  const measureImgRef = useRef<HTMLImageElement | null>(null);
  const layerImgRefs = useRef<[HTMLImageElement | null, HTMLImageElement | null]>([
    null,
    null,
  ]);
  const [visibleImgBox, setVisibleImgBox] = useState<{
    left: number;
    top: number;
    width: number;
    height: number;
  } | null>(null);

  // 表示中の立ち絵 img の位置/サイズ（stack 内座標）を追跡し、
  // クリック判定とデバッグ枠の基準として使う。
  useEffect(() => {
    const img = layerImgRefs.current[charVisible];
    if (!img) return;
    const update = () => {
      setVisibleImgBox({
        left: img.offsetLeft,
        top: img.offsetTop,
        width: img.offsetWidth,
        height: img.offsetHeight,
      });
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(img);
    window.addEventListener("resize", update);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [charVisible, charLayers]);

  const triggerGateMoment = useCallback(
    (pick: GateGirlMoment) => {
      clearGateMomentTimer();
      setGateMoment(pick);
      setDialogueTick((t) => t + 1);
      gateMomentTimerRef.current = window.setTimeout(() => {
        setGateMoment(null);
        setDialogueTick((t) => t + 1);
        gateMomentTimerRef.current = null;
      }, GATE_GIRL_MOMENT_MS);
    },
    [clearGateMomentTimer],
  );

  const onGateGirlClick = useCallback(
    (e: React.MouseEvent<HTMLButtonElement>) => {
      const img = layerImgRefs.current[charVisible] ?? measureImgRef.current;
      if (img) {
        const rect = img.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
          const px = ((e.clientX - rect.left) / rect.width) * 100;
          const py = ((e.clientY - rect.top) / rect.height) * 100;
          if (SHOW_GATE_GIRL_HIT_AREAS) {
            // 判定領域の調整用ログ
            // eslint-disable-next-line no-console
            console.log(
              `[gate-girl] click @ ${px.toFixed(1)}%, ${py.toFixed(1)}%`,
            );
          }
          const hit = GATE_GIRL_SPECIAL_MOMENTS.find(
            (m) =>
              px >= m.hitArea.x &&
              px <= m.hitArea.x + m.hitArea.w &&
              py >= m.hitArea.y &&
              py <= m.hitArea.y + m.hitArea.h,
          );
          if (hit) {
            triggerGateMoment(hit);
            return;
          }
        }
      }
      const pick =
        GATE_GIRL_MOMENTS[Math.floor(Math.random() * GATE_GIRL_MOMENTS.length)]!;
      triggerGateMoment(pick);
    },
    [triggerGateMoment, charVisible],
  );

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
    <div className="ws-root game-screen" lang="ja">
      <BackgroundLayer world={selected} />
      <AmbientMonitoringLayer variant="world" />

      <div className="ws-shell">
        <header className="ws-chrome">
          <GameButton
            aria-label="もどる"
            className="ws-back-button"
            icon="arrow_back"
            label="もどる"
            onClick={onBack}
            type="button"
            variant="ghost"
          />
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
          <section className="ws-title-block" aria-label="画面タイトル">
            <h1>WORLD SELECT</h1>
            <p>ワールドを選択して下さい</p>
          </section>

          <section
            className="ws-reel"
            aria-label="実験ワールドカード"
            onWheel={onWheel}
          >
            <GameFrameButton
              aria-label="前のワールドへ"
              className="ws-reel-nav ws-reel-nav--prev"
              icon="chevron_left"
              onClick={goPrev}
              type="button"
            />

            <div className="ws-reel-stage">
              <SidePeek world={prevWorld} dir="prev" />
              <CardStack worlds={WORLDS} activeIndex={index} onSelect={setIndex} />
              <SidePeek world={nextWorld} dir="next" />
              <div className="ws-reel-pager" aria-hidden>
                {String(index + 1).padStart(2, "0")} /{" "}
                {String(WORLDS.length).padStart(2, "0")}
              </div>
            </div>

            <GameFrameButton
              aria-label="次のワールドへ"
              className="ws-reel-nav ws-reel-nav--next"
              icon="chevron_right"
              onClick={goNext}
              type="button"
            />
          </section>

          <DialogueBar
            contentKey={`${selected.id}-${dialogueTick}-${gateMoment ? "m" : "g"}`}
            line={gateMoment?.line ?? selected.guideLine}
            lineVariant={gateMoment ? "moment" : "guide"}
            onStart={onPickWorld ? handleStart : undefined}
          />
        </main>

        <div className="ws-character-layer">
          <button
            type="button"
            className="ws-character-hit"
            onClick={onGateGirlClick}
            aria-label="門前の少女に話しかける"
          >
            <span className="ws-character-stack" aria-hidden>
              <img
                alt=""
                className="ws-character-img ws-character-img--measure"
                decoding="async"
                src={DEFAULT_GATE_GIRL_SRC}
                ref={measureImgRef}
              />
              <span className="ws-character-layers">
                <img
                  alt=""
                  className="ws-character-img ws-character-img--layer"
                  decoding="async"
                  src={charLayers[0]}
                  style={{ opacity: charVisible === 0 ? 1 : 0 }}
                  ref={(el) => {
                    layerImgRefs.current[0] = el;
                  }}
                />
                <img
                  alt=""
                  className="ws-character-img ws-character-img--layer"
                  decoding="async"
                  src={charLayers[1]}
                  style={{ opacity: charVisible === 1 ? 1 : 0 }}
                  ref={(el) => {
                    layerImgRefs.current[1] = el;
                  }}
                />
              </span>
              {SHOW_GATE_GIRL_HIT_AREAS && visibleImgBox
                ? GATE_GIRL_SPECIAL_MOMENTS.map((m) => (
                    <span
                      key={m.id}
                      className="ws-character-hitbox-debug"
                      style={{
                        left: `${
                          visibleImgBox.left +
                          (visibleImgBox.width * m.hitArea.x) / 100
                        }px`,
                        top: `${
                          visibleImgBox.top +
                          (visibleImgBox.height * m.hitArea.y) / 100
                        }px`,
                        width: `${(visibleImgBox.width * m.hitArea.w) / 100}px`,
                        height: `${(visibleImgBox.height * m.hitArea.h) / 100}px`,
                      }}
                    >
                      {m.id}
                    </span>
                  ))
                : null}
            </span>
          </button>
        </div>
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
    <article
      className={isActive ? "ws-card ws-card--active" : "ws-card"}
      onClick={onActivate}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onActivate();
        }
      }}
      aria-current={isActive ? "true" : undefined}
      role="button"
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
          <div className="ws-card-stats" aria-label="ワールド情報">
            <span>想定 {world.playTimeLabel}</span>
            <span className="ws-danger">
              危険度
              <span className="ws-danger-bars" aria-hidden>
                {Array.from({ length: 5 }, (_, i) => (
                  <span
                    key={i}
                    className={i < world.dangerLevel ? "ws-danger-bar ws-danger-bar--on" : "ws-danger-bar"}
                  />
                ))}
              </span>
            </span>
          </div>
          <div className="ws-card-meta">
            {world.themeTags.map((tag) => (
              <button
                key={tag}
                type="button"
                className="ws-chip"
                onClick={(e) => {
                  e.stopPropagation();
                }}
                aria-label={`${tag}タグ`}
              >
                {tag}
              </button>
            ))}
            <button
              type="button"
              className="ws-chip ws-chip--difficulty"
              onClick={(e) => {
                e.stopPropagation();
              }}
              aria-label={`難易度 ${world.difficultyLabel}`}
            >
              難易度 {world.difficultyLabel}
            </button>
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
    </article>
  );
}

/* ---------------------------------------------------------------------- */

type DialogueBarProps = {
  /** ワールド切替時に本文フェードを再実行するためのキー */
  contentKey: string;
  line: string;
  /** タップ時セリフはやわらかいクロスフェード風 */
  lineVariant?: "guide" | "moment";
  onStart?: () => void;
};

function DialogueBar({ contentKey, line, lineVariant = "guide", onStart }: DialogueBarProps) {
  const lineClass =
    lineVariant === "moment"
      ? "ws-dialogue-line ws-dialogue-line--moment"
      : "ws-dialogue-line ws-dialogue-line--enter";
  return (
    <div className="ws-dialogue">
      <div className="ws-dialogue-shell prologue-text-panel-shell">
        <div className="ws-dialogue-panel prologue-text-panel">
          <div className="prologue-terminal-mark ws-dialogue-terminal-mark" aria-hidden>
            <span className="prologue-terminal-icon material-symbols-outlined">
              terminal
            </span>
          </div>
          <div className="prologue-panel-body">
            <div className="prologue-body">
              <span className="ws-dialogue-speaker">門前の少女</span>
              <p className={lineClass} key={contentKey}>
                {line}
              </p>
            </div>
          </div>
          <div className="ws-dialogue-actions">
            <GameProtocolButton
              className="ws-btn-primary"
              disabled={!onStart}
              label="実験を開始する"
              onClick={onStart}
              sublabel="取り消し不可 / INITIATE"
              type="button"
            />
          </div>
        </div>
      </div>
    </div>
  );
}
