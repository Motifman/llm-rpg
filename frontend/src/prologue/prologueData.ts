import type { PrologueScene } from "./prologueTypes";

const BG1 = "/assets/prologue/placeholder-scene-1.svg";
const BG2 = "/assets/prologue/placeholder-scene-2.svg";
const BG3 = "/assets/prologue/placeholder-scene-3.svg";
const BG4 = "/assets/prologue/placeholder-scene-4.svg";
const BG5 = "/assets/prologue/placeholder-scene-5.svg";
const BG6 = "/assets/prologue/placeholder-scene-6.svg";

/**
 * 本編プロローグ。背景は仮置き SVG（章ごとに色分け）。
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
      "目が合う。\n彼女の瞳に映ったのは、驚きではなく――まるで「待ちわびていた」かのような、深い諦念。",
  },
  {
    id: "prologue-s5-03",
    backgroundSrc: BG5,
    body:
      "彼女がゆっくりと唇を動かす。\n「……また、新しい『お客様』？ それとも……」",
  },
  {
    id: "prologue-s6-01",
    backgroundSrc: BG6,
    body:
      "「――いいえ。あなたは、私たちが呼びかけた『希望』であってほしい」",
  },
  {
    id: "prologue-s6-02",
    backgroundSrc: BG6,
    body:
      "彼女の手が、私の意識を現実から引き剥がすように伸びてくる。",
  },
  {
    id: "prologue-s6-03",
    backgroundSrc: BG6,
    body:
      "脳の深部で、機械的なビープ音が鳴り響いた。\nInitializing... Instance Connection Established.",
  },
];
