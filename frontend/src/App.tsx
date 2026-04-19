import { useState } from "react";

import { PrologueScreen } from "./prologue/PrologueScreen";
import { TitleScreen } from "./title/TitleScreen";
import { WorldSelectScreen } from "./worldSelect/WorldSelectScreen";

type AppPhase = "title" | "prologue" | "main";

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
  const [phase, setPhase] = useState<AppPhase>("title");

  if (phase === "prologue") {
    return (
      <PrologueScreen
        onBack={() => setPhase("title")}
        onExit={() => setPhase("main")}
      />
    );
  }

  if (phase === "main") {
    return (
      <WorldSelectScreen
        onBack={() => setPhase("title")}
        onPickWorld={() => {
          /* キャラ選択・導入ノベルは今後ここへ */
        }}
      />
    );
  }

  return (
    <TitleScreen
      onContinue={() => setPhase("main")}
      onQuit={quitFromTitle}
      onStart={() => setPhase("prologue")}
    />
  );
}
