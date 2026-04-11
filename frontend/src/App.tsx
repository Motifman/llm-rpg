import { useState } from "react";

import { PrologueScreen } from "./prologue/PrologueScreen";
import { TitleScreen } from "./title/TitleScreen";

type AppPhase = "title" | "prologue" | "main";

/**
 * タイトル → プロローグ（試験）→ メイン（未接続）の遷移。
 * 「つづきから」はプロローグを挟まずメインへ。
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
      <div className="app-placeholder-main">
        <p>メイン画面（ワールド選択・GameShell 接続は今後ここへ）</p>
        <button onClick={() => setPhase("title")} type="button">
          タイトルへ戻る
        </button>
      </div>
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
