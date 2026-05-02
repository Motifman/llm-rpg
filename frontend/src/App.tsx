import { useState } from "react";

import { AmbientMonitoringLayer } from "./ambient/AmbientMonitoringLayer";
import { CharacterSelectScreen } from "./characterSelect/CharacterSelectScreen";
import { GameShell } from "./GameShell";
import { PrologueScreen } from "./prologue/PrologueScreen";
import { TitleScreen } from "./title/TitleScreen";
import { WorldSelectScreen } from "./worldSelect/WorldSelectScreen";

type AppPhase = "title" | "prologue" | "worldSelect" | "characterSelect" | "game";

/**
 * 開発時のみ: 背景モニタリングレイヤ単体のプレビュー。
 * 例: http://localhost:5173/?ambientPreview=1
 * タイトル用の控えめトーン: &variant=title
 * 本番ビルドでは無効（通常 UI のみ）。
 */
function readDevAmbientPreviewVariant(): "title" | "world" | null {
  if (!import.meta.env.DEV || typeof window === "undefined") {
    return null;
  }
  const q = new URLSearchParams(window.location.search);
  if (q.get("ambientPreview") !== "1") {
    return null;
  }
  return q.get("variant") === "title" ? "title" : "world";
}

function readDevInitialPhase(): AppPhase {
  if (!import.meta.env.DEV || typeof window === "undefined") {
    return "title";
  }
  const phase = new URLSearchParams(window.location.search).get("phase");
  if (
    phase === "title" ||
    phase === "prologue" ||
    phase === "worldSelect" ||
    phase === "characterSelect" ||
    phase === "game"
  ) {
    return phase;
  }
  return "title";
}

function AmbientDevPreviewShell({ variant }: { variant: "title" | "world" }) {
  return (
    <div className="ambient-dev-preview" lang="ja">
      <AmbientMonitoringLayer variant={variant} />
      <p className="ambient-dev-preview-hint">
        dev: AmbientMonitoringLayer のみ表示中。通常どおりに戻すには URL から{" "}
        <code>?ambientPreview=1</code> を削除してください。
        {variant === "world" ? (
          <>
            {" "}
            タイトル用トーンは <code>?ambientPreview=1&amp;variant=title</code>。
          </>
        ) : null}
      </p>
    </div>
  );
}

/**
 * タイトル → プロローグ（試験）→ ワールド選択 → … の遷移。
 * 「つづきから」はプロローグを挟まずメイン（ワールド選択）へ。
 */
function quitFromTitle(): void {
  window.close();
  window.setTimeout(() => {
    alert("ブラウザのタブを閉じるか、このウィンドウを終了してください。");
  }, 0);
}

export function App() {
  const [phase, setPhase] = useState<AppPhase>(() => readDevInitialPhase());
  const [selectedWorldId, setSelectedWorldId] = useState("abandoned_hospital");
  const ambientPreview = readDevAmbientPreviewVariant();
  if (ambientPreview) {
    return <AmbientDevPreviewShell variant={ambientPreview} />;
  }

  if (phase === "prologue") {
    return (
      <PrologueScreen
        onBack={() => setPhase("title")}
        onExit={() => setPhase("worldSelect")}
      />
    );
  }

  if (phase === "worldSelect") {
    return (
      <WorldSelectScreen
        onBack={() => setPhase("title")}
        onPickWorld={(worldId) => {
          setSelectedWorldId(worldId);
          setPhase("characterSelect");
        }}
      />
    );
  }

  if (phase === "characterSelect") {
    return (
      <CharacterSelectScreen
        worldId={selectedWorldId}
        onBack={() => setPhase("worldSelect")}
        onTransfer={() => setPhase("game")}
      />
    );
  }

  if (phase === "game") {
    return <GameShell />;
  }

  return (
    <TitleScreen
      onContinue={() => setPhase("worldSelect")}
      onQuit={quitFromTitle}
      onStart={() => setPhase("prologue")}
    />
  );
}
