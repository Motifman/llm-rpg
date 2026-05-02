/**
 * 実験（脱出ワールド）一覧の静的データ。
 *
 * 各ワールドの世界観・テーマ・エピローグ変化は docs/game/worlds.md を正本とする。
 * 将来 GET /api/worlds 等のエンドポイントへ差し替える前提。
 */

export type WorldSummary = {
  id: string;
  /** 画面中央の見出し（日本語） */
  title: string;
  /** 英字サブタイトル（テレメトリ／枝のラベル用） */
  subtitle: string;
  /** カードのキッカー（例: PROTOCOL.07） */
  protocolCode: string;
  /** 短い説明 */
  shortDescription: string;
  themeTags: string[];
  difficultyLabel: string;
  playTimeLabel: string;
  dangerLevel: number;
  /** 16:9 ヒーロー枠／カード背景に使う代表画像 */
  imageSrc: string;
  /**
   * カード内で一定時間ごとに切り替えるシーン画像群。
   * 未指定または長さ 1 の場合はアニメーションせず imageSrc を表示する。
   */
  sceneImages?: string[];
  /** 選択時に少女が読み上げる誘導台詞（1〜2行） */
  guideLine: string;
};

export const WORLDS: WorldSummary[] = [
  {
    id: "abandoned_hospital",
    title: "廃病院からの脱出 ―― 消し残された夜",
    subtitle: "SHIZUHARA HOSPITAL // MEMORY-FRAGMENT 01",
    protocolCode: "PROTOCOL.01",
    shortDescription:
      "記憶治療で知られた総合病院の廃墟。違和感を捲るほど、閉鎖の夜と旧友への選択が浮かび上がる。",
    themeTags: ["記憶", "選択", "心理ホラー"],
    difficultyLabel: "中",
    playTimeLabel: "45-60分",
    dangerLevel: 3,
    imageSrc: "/assets/worldSelect/abandoned-hospital-hero.png",
    guideLine:
      "……忘れていいって、誰が決めるんだろう。\nここは、消し残された夜を選び直す場所。",
  },
  {
    id: "snowbound_station",
    title: "雪原の駅 ―― 終電の残響",
    subtitle: "SNOWBOUND STATION // MEMORY-FRAGMENT 02",
    protocolCode: "PROTOCOL.02",
    shortDescription:
      "雪に半ば埋もれた無人駅。時計は止まり、遠くで列車の音だけが鳴り続ける。",
    themeTags: ["静寂", "選択", "時間"],
    difficultyLabel: "中",
    playTimeLabel: "35-50分",
    dangerLevel: 3,
    imageSrc: "/assets/worldSelect/snowbound-station-hero.svg",
    guideLine:
      "鐘の音が、まだ聞こえてる。\n誰を待っていたのか、思い出せたら、扉は開く。",
  },
  {
    id: "endless_banquet",
    title: "終わらない宴会場",
    subtitle: "ENDLESS BANQUET // MEMORY-FRAGMENT 03",
    protocolCode: "PROTOCOL.03",
    shortDescription:
      "永遠に続く晩餐。客は減らず、料理も減らない。誰が主催者なのかは分からない。",
    themeTags: ["会話", "社交", "迷宮"],
    difficultyLabel: "高",
    playTimeLabel: "50-70分",
    dangerLevel: 4,
    imageSrc: "/assets/worldSelect/endless-banquet-hero.svg",
    guideLine:
      "……ここは、好かれようとするほど遠ざかる場所。\n席を立つ勇気の話。",
  },
  {
    id: "underwater_library",
    title: "水面下の書庫",
    subtitle: "UNDERWATER LIBRARY // MEMORY-FRAGMENT 04",
    protocolCode: "PROTOCOL.04",
    shortDescription:
      "螺旋階段の先の書庫。水位は少しずつ上がり、棚の本が静かに沈んでいく。",
    themeTags: ["取捨選択", "静謐", "時間制限"],
    difficultyLabel: "高",
    playTimeLabel: "50-75分",
    dangerLevel: 4,
    imageSrc: "/assets/worldSelect/underwater-library-hero.svg",
    guideLine:
      "全部は救えない。\n――どれを残すか、ちゃんと選んで。",
  },
  {
    id: "mirrored_greenhouse",
    title: "鏡の温室",
    subtitle: "MIRRORED GREENHOUSE // MEMORY-FRAGMENT 05",
    protocolCode: "PROTOCOL.05",
    shortDescription:
      "鏡張りの温室。鏡の中の自分だけが、少し違う表情をしている。",
    themeTags: ["対話", "自己", "終盤"],
    difficultyLabel: "極",
    playTimeLabel: "70-90分",
    dangerLevel: 5,
    imageSrc: "/assets/worldSelect/mirrored-greenhouse-hero.svg",
    guideLine:
      "鏡の向こうの“あなた”の方が、たぶん綺麗。\n……それでも、こっちを選んで。",
  },
];
