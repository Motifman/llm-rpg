import { useEffect, useState } from "react";

import { AmbientMonitoringLayer } from "../ambient/AmbientMonitoringLayer";
import "./TitleScreen.css";
import { TitleDisconnectOverlay } from "./TitleDisconnectOverlay";
import { pickTitleHudLine, TITLE_HUD_LINES, TITLE_HUD_TICK_MS } from "./titleHudLines";

export type TitleScreenProps = {
  /** 新規ゲーム開始（ワールド選択などへ） */
  onStart: () => void;
  /** セーブがあれば読み込み（現状はプレースホルダ可） */
  onContinue: () => void;
  /** アプリ終了・タブを閉じる案内 */
  onQuit: () => void;
};

/**
 * Stitch プロジェクト「夢ノ館デジタルグリッチ」内スクリーン
 * 「Title Screen - The Fractured Aristocrat」に基づくタイトル UI。
 * 背景は `title_background_instancia.png`（旧 Stitch 由来の背景は `background_legacy.png` に退避）。
 * グレインは Stitch エクスポート由来の `grain.png` を `public/assets/title/` に同梱。
 */
function initialHudLines(): [string, string, string] {
  const a = TITLE_HUD_LINES[0] ?? "";
  const b = TITLE_HUD_LINES[4] ?? a;
  const c = TITLE_HUD_LINES[8] ?? b;
  return [a, b, c];
}

export function TitleScreen({ onStart, onContinue, onQuit }: TitleScreenProps) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [disconnectOpen, setDisconnectOpen] = useState(false);
  const [hudLines, setHudLines] = useState<[string, string, string]>(initialHudLines);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const tick = () => {
      setHudLines((prev) => {
        const newest = pickTitleHudLine(prev[2]);
        return [prev[1], prev[2], newest];
      });
    };
    if (mq.matches) {
      return;
    }
    const id = window.setInterval(tick, TITLE_HUD_TICK_MS);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (!settingsOpen) {
      return;
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setSettingsOpen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [settingsOpen]);

  return (
    <div className="ts-root" lang="ja">
      <div className="ts-bg" aria-hidden>
        <img
          alt=""
          className="ts-bg-img ts-bg-img--breathe"
          decoding="async"
          src="/assets/title/title_background_instancia.png"
        />
        <div className="ts-bg-fade" />
        <div className="ts-corner-vignette" />
        <div className="ts-scanline-overlay" />
        <div className="ts-grain" />
      </div>

      <AmbientMonitoringLayer variant="title" />

      <div className="ts-shell">
        <main className="ts-main">
          <div className="ts-main-stack">
            <div className="ts-hero-wrap">
              <h1 className="ts-hero-title">INSTANCIA</h1>
              <div className="ts-hero-meta">
                <span>[Location: Meiji_Mansion_Sim]</span>
                <div className="ts-meta-line" />
                <span>[Time: 04:44_Dusk]</span>
              </div>
            </div>

            <nav className="ts-nav" aria-label="メインメニュー">
              <button className="ts-btn ts-btn--primary" onClick={onStart} type="button">
                <span className="ts-btn-icon" aria-hidden>
                  play_arrow
                </span>
                <span>はじめる</span>
                <span className="ts-btn-hint">INSTANCE_ID: 0xFA4</span>
              </button>
              <button className="ts-btn" onClick={onContinue} type="button">
                <span className="ts-btn-icon" aria-hidden>
                  history
                </span>
                <span>つづきから</span>
                <span className="ts-btn-hint">LOAD_CHECKPOINT_01</span>
              </button>
              <button
                className="ts-btn"
                onClick={() => setSettingsOpen(true)}
                type="button"
              >
                <span className="ts-btn-icon" aria-hidden>
                  settings
                </span>
                <span>せってい</span>
                <span className="ts-btn-hint">SYS_CONFIG_OVERRIDE</span>
              </button>
              <button className="ts-btn" onClick={() => setDisconnectOpen(true)} type="button">
                <span className="ts-btn-icon" aria-hidden>
                  power_settings_new
                </span>
                <span>やめる</span>
                <span className="ts-btn-hint">TERMINATE_SESSION</span>
              </button>
            </nav>
          </div>
        </main>

        <aside className="ts-hud-gauges" aria-hidden>
          <div className="ts-gauge-track">
            <div className="ts-gauge-fill ts-gauge-fill--a" />
          </div>
          <div className="ts-gauge-track">
            <div className="ts-gauge-fill ts-gauge-fill--b" />
          </div>
          <div className="ts-gauge-track">
            <div className="ts-gauge-fill ts-gauge-fill--c" />
          </div>
        </aside>

        <aside className="ts-hud" aria-hidden>
          <div className="ts-hud-log">
            <div className="ts-hud-line ts-hud-line--dim">{hudLines[0]}</div>
            <div className="ts-hud-line ts-hud-line--sec">{hudLines[1]}</div>
            <div key={hudLines[2]} className="ts-hud-line ts-hud-line--dim ts-hud-line--enter">
              {hudLines[2]}
            </div>
          </div>
        </aside>

        <div className="ts-border-v ts-border-v--l" aria-hidden />
        <div className="ts-border-v ts-border-v--r" aria-hidden />
      </div>

      <div className="ts-fx" aria-hidden>
        <div className="ts-fx-line ts-fx-line--1" />
        <div className="ts-fx-line ts-fx-line--2" />
        <div className="ts-fx-frame" />
      </div>

      {settingsOpen ? (
        <div
          className="ts-modal-overlay"
          onClick={() => setSettingsOpen(false)}
          role="presentation"
        >
          <div
            className="ts-modal"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-labelledby="ts-settings-title"
            aria-modal="true"
          >
            <h3 id="ts-settings-title">せってい</h3>
            <p>
              表示・音声・入力などの詳細設定は今後のフェーズで接続予定です。現状はプレースホルダです。
            </p>
            <div className="ts-modal-actions">
              <button onClick={() => setSettingsOpen(false)} type="button">
                とじる
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {disconnectOpen ? (
        <TitleDisconnectOverlay
          onComplete={() => {
            setDisconnectOpen(false);
            onQuit();
          }}
        />
      ) : null}
    </div>
  );
}
