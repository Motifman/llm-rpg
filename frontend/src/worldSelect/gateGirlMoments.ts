/**
 * ワールド選択：門前の少女タップ時に表示する（セリフ, 立ち絵）の組。
 * 立ち絵は `frontend/public/assets/prologue/` 配下に配置（`/assets/prologue/…` で配信）。
 */
export const DEFAULT_GATE_GIRL_SRC = "/assets/prologue/gate_girl.png";

/** 少し恥ずかしそうな立ち絵（透過 PNG） */
export const GATE_GIRL_SHY_SRC = "/assets/prologue/gate_girl_shy.png";

/** 怒って腕を組んでいる立ち絵（透過 PNG） */
export const GATE_GIRL_ANGRY_SRC = "/assets/prologue/gate_girl_angry.png";

/** 少し微笑んでいる立ち絵（透過 PNG） */
export const GATE_GIRL_SMILE_SRC = "/assets/prologue/gate_girl_smile.png";

export type GateGirlMoment = {
  readonly line: string;
  readonly imageSrc: string;
};

/**
 * 立ち絵に対する判定領域（長方形）。
 * 値はすべて立ち絵画像の幅／高さに対する 0〜100 の % 単位。
 * 左上原点で `(x, y)` から `(x + w, y + h)` の範囲がヒット領域。
 */
export type GateGirlHitRect = {
  readonly x: number;
  readonly y: number;
  readonly w: number;
  readonly h: number;
};

export type GateGirlSpecialMoment = GateGirlMoment & {
  readonly id: string;
  readonly hitArea: GateGirlHitRect;
};

/**
 * 特殊判定（タップ箇所が一致した場合のみ発火）。
 * 配列の前方が優先。複数領域が重なる場合は最初にヒットしたものを採用。
 *
 * 判定領域の調整は下記 `hitArea` の値を変えるだけ。
 * 開発中は `SHOW_GATE_GIRL_HIT_AREAS = true` にすると、
 * 立ち絵に半透明の枠とラベルが重なって表示される。
 */
export const GATE_GIRL_SPECIAL_MOMENTS: readonly GateGirlSpecialMoment[] = [
  {
    id: "chest",
    line: "ちょっと……どこ触ってるの。次やったら、本気で怒るからね。",
    imageSrc: GATE_GIRL_ANGRY_SRC,
    // 胸あたり（要調整）
    hitArea: { x: 40, y: 26, w: 24, h: 10 },
  },
];

/** 開発時に判定領域を可視化する（本番リリース時は false） */
export const SHOW_GATE_GIRL_HIT_AREAS = false;

export const GATE_GIRL_MOMENTS: readonly GateGirlMoment[] = [
  {
    line: "照れちゃうな……でも、悪い気はしないかな。",
    imageSrc: GATE_GIRL_SMILE_SRC,
  },
  {
    line: "……そんなに何度も触らないで。さすがに、恥ずかしいから。",
    imageSrc: GATE_GIRL_SHY_SRC,
  },
  {
    line: "もう……画面越しなのに、近すぎるよ。",
    imageSrc: GATE_GIRL_SHY_SRC,
  },
  {
    line: "……今のは、見なかったことにしてくれる？",
    imageSrc: DEFAULT_GATE_GIRL_SRC,
  },
  {
    line: "ねえ、そろそろ……ちゃんと先に進んでほしいな。",
    imageSrc: GATE_GIRL_SHY_SRC,
  },
];

/** セリフ表示が長引きすぎないよう、しばらくしたらガイドへ戻す（ミリ秒） */
export const GATE_GIRL_MOMENT_MS = 5_000;
