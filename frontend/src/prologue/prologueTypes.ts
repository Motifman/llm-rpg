/**
 * 立ち絵レイヤ。シーン単位で表示/非表示・画像・補正を切り替える。
 * `visible: false` のときは `src` があっても描画しない。
 */
export type PrologueCharacterLayer = {
  src: string;
  visible?: boolean;
  /** `prologueCharacterPresets.ts` のキー。未指定は neutral */
  tintPreset?: string;
  /** プリセットより優先。CSS `filter` の値（例: brightness(0.95) saturate(1.05)） */
  tintFilter?: string;
};

export type PrologueScene = {
  id: string;
  /** 背景画像（public 配下の URL） */
  backgroundSrc: string;
  /** 発話者。未指定時は名前タブを出さない */
  speaker?: string;
  body: string;
  /** 省略時は立ち絵なし */
  character?: PrologueCharacterLayer;
};
