import { useCallback, useEffect, useState } from "react";

import { PROLOGUE_SCENES } from "./prologueData";
import "./PrologueScreen.css";
import { resolveCharacterTintFilter } from "./prologueCharacterPresets";
import { LibraryTypewriterText } from "./LibraryTypewriterText";
import type { PrologueScene } from "./prologueTypes";

export type PrologueScreenProps = {
  scenes?: PrologueScene[];
  onExit: () => void;
  onBack?: () => void;
};

export function PrologueScreen({
  scenes = PROLOGUE_SCENES,
  onExit,
  onBack,
}: PrologueScreenProps) {
  const [sceneIndex, setSceneIndex] = useState(0);
  const [lineDone, setLineDone] = useState(false);
  const [instant, setInstant] = useState(false);

  const scene = scenes[sceneIndex];
  const isLast = sceneIndex >= scenes.length - 1;

  useEffect(() => {
    setLineDone(false);
    setInstant(false);
  }, [scene?.id]);

  const onTypingComplete = useCallback(() => {
    setLineDone(true);
  }, []);

  const handleAdvance = useCallback(() => {
    if (!scene) {
      return;
    }
    if (!lineDone) {
      if (!instant) {
        setInstant(true);
      }
      return;
    }
    if (isLast) {
      onExit();
      return;
    }
    setSceneIndex((i) => i + 1);
  }, [instant, isLast, lineDone, onExit, scene]);

  const handleSkipAll = useCallback(() => {
    onExit();
  }, [onExit]);

  if (!scene) {
    return null;
  }

  const character = scene.character;
  const showCharacter = character != null && character.visible !== false;
  const characterTint = showCharacter
    ? resolveCharacterTintFilter(character.tintPreset, character.tintFilter)
    : undefined;
  const speakerLabel = scene.speaker?.trim();
  const showSpeakerTab = Boolean(speakerLabel);

  return (
    <div className="prologue-root" lang="ja">
      <div className="prologue-bg-wrap" aria-hidden>
        <img
          alt=""
          className="prologue-bg"
          decoding="async"
          key={scene.id}
          src={scene.backgroundSrc}
        />
        <div className="prologue-bg-dim" />
      </div>

      {showCharacter ? (
        <div className="prologue-character-layer" aria-hidden>
          <img
            alt=""
            className="prologue-character-img"
            decoding="async"
            src={character.src}
            style={characterTint != null ? { filter: characterTint } : undefined}
          />
        </div>
      ) : null}

      <div className="prologue-chrome">
        {onBack ? (
          <button className="prologue-ts-btn" onClick={onBack} type="button">
            <span className="prologue-ts-btn-icon" aria-hidden>
              arrow_back
            </span>
            <span className="prologue-ts-btn-label">タイトルへ</span>
          </button>
        ) : null}
        <span className="prologue-chrome-fill" aria-hidden />
        <button className="prologue-ts-btn" onClick={handleSkipAll} type="button">
          <span className="prologue-ts-btn-icon" aria-hidden>
            skip_next
          </span>
          <span className="prologue-ts-btn-label">スキップ</span>
        </button>
      </div>

      <button
        className="prologue-stage"
        onClick={handleAdvance}
        type="button"
        aria-label={lineDone ? (isLast ? "プロローグを終了" : "次のシーンへ") : "表示を完了"}
      >
        <div
          className={
            showSpeakerTab
              ? "prologue-text-panel-shell"
              : "prologue-text-panel-shell prologue-text-panel-shell--no-speaker"
          }
        >
          {showSpeakerTab ? (
            <div className="prologue-panel-titlebar">
              <span className="prologue-panel-title">{speakerLabel}</span>
            </div>
          ) : null}
          <div className="prologue-text-panel">
            <div className="prologue-panel-body">
              <div className="prologue-terminal-mark" aria-hidden>
                <span className="prologue-terminal-icon material-symbols-outlined">
                  terminal
                </span>
              </div>
              <div className="prologue-body">
                <LibraryTypewriterText
                  key={scene.id}
                  className="prologue-body-text"
                  instant={instant}
                  sceneKey={scene.id}
                  text={scene.body}
                  onTypingComplete={onTypingComplete}
                />
              </div>
            </div>
            <div className="prologue-hint">
              {lineDone
                ? isLast
                  ? "クリックで次へ（終了）"
                  : "クリックで次のシーン"
                : "クリックで全文表示"}
            </div>
          </div>
        </div>
      </button>
    </div>
  );
}
