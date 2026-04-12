import type { PrologueCharacterLayer, PrologueScene } from "./prologueTypes";

const BG1 = "/assets/prologue/prologue-bg-1.png";
const BG2 = "/assets/prologue/prologue-bg-2.png";
const BG3 = "/assets/prologue/prologue-bg-3.png";
/** タイトル画面と同じ荘園外観（`TitleScreen` の背景と共有） */
const BG4 = "/assets/title/title_background_instancia.png";
const BG5 = "/assets/prologue/prologue-bg-5.png";
const BG6 = "/assets/prologue/prologue-bg-6.png";

/** 門前の少女・BG6 後半シーン用（シーンごとに visible を切り替え可能） */
const GATE_GIRL_STANDING: PrologueCharacterLayer = {
  src: "/assets/prologue/gate_girl.png",
  visible: true,
  tintPreset: "neutral",
};

/**
 * 本編プロローグ。背景画像は `public/assets/prologue/`（BG4 はタイトル背景を参照）。
 */
export const PROLOGUE_SCENES: PrologueScene[] = [
  {
    id: "prologue-s1-01",
    backgroundSrc: BG1,
    body:
      "「……お疲れ様でした」\nその声に、曖昧な会釈を返したかどうかも覚えていない。",
  },
  {
    id: "prologue-s1-02",
    backgroundSrc: BG1,
    body:
      "日付を跨ぐのが当たり前になった時計の針。\n重い瞼をこすりながら、冷え切った自室のドアを開ける。",
  },
  {
    id: "prologue-s1-03",
    backgroundSrc: BG1,
    body:
      "スーツを脱ぐ気力すら、夜の静寂に吸い取られていく。\n倒れ込むように潜り込んだベッドの感触だけが、唯一の現実だった。",
  },
  {
    id: "prologue-s2-01",
    backgroundSrc: BG2,
    body:
      "ひび割れた天井の隅を眺める。\n思考は泥のように溶け、身体の輪郭が寝具に溶け出していく。",
  },
  {
    id: "prologue-s2-02",
    backgroundSrc: BG2,
    body:
      "……最近、妙な既視感を覚えることがある。\n自分の記憶、自分の経験。それらは本当に、私が歩んできた道なのだろうか。",
  },
  {
    id: "prologue-s2-03",
    backgroundSrc: BG2,
    body:
      "考えるのをやめよう。\n今はただ、この深い安らぎに身を任せればいい。\n……おやすみなさい。",
  },
  {
    id: "prologue-s3-01",
    backgroundSrc: BG3,
    body:
      "目が覚めると、私は霧の中に立っていた。\n夢だ、と直感する。そうでなければ、この非現実的な静けさを説明できない。",
  },
  {
    id: "prologue-s3-02",
    backgroundSrc: BG3,
    body:
      "ふと、足元の違和感に気づき、視線を落とした。\nそこにあるのは、踏みしめた土の感触。\n……けれど、土の隙間を埋めているのは、緑の草ではなかった。",
  },
  {
    id: "prologue-s3-03",
    backgroundSrc: BG3,
    body:
      "土に混じり、鈍い光を放ちながら流動する数式と記号の奔流。\nまるで大地そのものが、何らかの命令体系で編まれているかのような――\n見たこともない、生理的な嫌悪感を抱かせる光景。",
  },
  {
    id: "prologue-s4-01",
    backgroundSrc: BG4,
    body:
      "霧を払いながら進むと、その威容が姿を現した。\n古びたレンガ造りの屋敷。幾年もの時を閉じ込めたような、優雅で孤独な建築物。",
  },
  {
    id: "prologue-s4-02",
    backgroundSrc: BG4,
    body:
      "見事な庭園、美しく整えられた生垣。\nけれど、風にそよぐ葉の音は、どこかスピーカーから流れるノイズのように歪んでいる。",
  },
  {
    id: "prologue-s4-03",
    backgroundSrc: BG4,
    body:
      "ここは誰かの住処だろうか。\nそれとも、私と同じように道に迷った者の、最果ての場所なのだろうか。",
  },
  {
    id: "prologue-s5-01",
    backgroundSrc: BG5,
    body:
      "門のそばに、誰かが立っていた。\n……少女だ。\n時代錯誤なほどに端正なドレスを纏い、彼女は虚空を見つめていた。",
  },
  {
    id: "prologue-s5-02",
    backgroundSrc: BG5,
    body:
      "目が合う。\n彼女は一瞬、何かを見たてのように目を見開き、すぐにまばたきを挟んだ。戸惑いと、隠しきれない警戒が瞳の奥にあった。",
  },
  {
    id: "prologue-s5-03",
    backgroundSrc: BG5,
    /** 直接セリフが主体のシーン（キャラシート: docs/game/characters/gate_girl.md） */
    speaker: "門前の少女",
    body:
      "かすれた声で、彼女は言った。\n「……誰？　霧の向こうに、気配だけはあった。でも、こんなふうに姿を識別したのは、初めて」",
  },
  {
    id: "prologue-s6-01",
    backgroundSrc: BG6,
    body:
      "荘園を包んでいた霧が、視界の奥から薄れていく。\nそれは消え失せることではなく、門と庭と空の境界が、ようやく同じ景深に重なり始めたのだと感じた。",
  },
  {
    id: "prologue-s6-02",
    backgroundSrc: BG6,
    character: { ...GATE_GIRL_STANDING },
    body:
      "門の前の少女が、霧の向こうの幻影ではなく、はっきりと線を持って見えた。\n濡れた石畳と、鉄の門の冷たさまで、色が違って感じられる。",
  },
  {
    id: "prologue-s6-03",
    backgroundSrc: BG6,
    character: { ...GATE_GIRL_STANDING },
    speaker: "門前の少女",
    body:
      "彼女は、こちらを見て、短く言った。\n「……聞こえてる。ちゃんと」",
  },
];
