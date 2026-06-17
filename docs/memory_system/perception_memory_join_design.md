# 知覚と記憶の接合 — 設計メモ

AI Being が「初めての場所で『なんだここ?』と呟き、半年ぶりに会った相手に『久しぶり』
と返す」ような反応を、ハードコードや scenario 固有のお膳立てに頼らず、汎用的な認知層
として備えられないか — を考えるための設計議論を残します。実装の最終形ではなく、判断の
経緯と、開いている論点を共有することが目的です。

## なぜ書くか

Issue #471 の Option β 検証 run (200 tick 完走) を読み直したとき、agent の振る舞いに
気になる点がありました。run は完走し、技術的には健全です。それでも `survival_island_v2`
の住人たちは、`forest_edge` の前で立ち止まったまま 1 歩奥の `forest_clearing` に踏み込み
ませんでした。嵐の翌朝に「ふと前回の嵐を思い出した」と呟くこともなく、初めて会った相手に
「はじめまして」と言うこともありません。

LLM の確率性に帰せる部分はあるとしても、それだけでは説明しにくい構造的な欠落が
ありそうだ、というのが起点です。「今この瞬間の知覚」と「過去の記憶」を照合する経路が、
agent の設計のどこにも置かれていません。本ドキュメントはその欠落を素直に認めた上で、
最小の拡張を素描します。

## 観察された具体現象

`var/runs/issue471_optionB_A_140tick/` の trace から。

- 4 人の player は全員「狼煙の材料 = 流木 + 枯れ葉 + 火打ち石」を `memo_add` に書き取って
  います。目標は理解されている
- それでも 35 tick の間「枯れ葉が未確保」を memo に繰り返し書き続けます
- `forest_edge` には到達しますが、隣接する `forest_clearing` (枯れ葉が積もる場所) に
  踏み込まれません
- 嵐 (tick 96) が来たとき、過去の経験を想起する仕草はなく、`spot_graph_wait` を 9 連発
  します
- tick 144 で救助船は通り過ぎ、誰も signal_fire を点けていません

prompt を読み直すと、agent が参照できる情報の側にも傾向がありました。

- `【現在地と周囲】` の同 spot プレイヤーリストは名前だけを出します。初対面か、3 時間
  ぶりかの違いは prompt に乗っていません
- `exploration_progress` (各 spot の訪問回数) は内部で track されているものの、
  prompt_builder からは参照されていません
- 隣接 spot は接続名と spot 名だけが見えます。中身を知らない場所への入り方を選ぶ手が
  かりが乏しい
- episodic recall は cue 軸マッチで動きますが、時間下限フィルタを持たないため、
  sliding window にまだ生きている直近の出来事がそのまま再想起されます

agent は「現在のもの」を見ることはできるが、「自分が初めてそれに触れているか、過去に
触れたことがあるか」を知る術が、構造として置かれていない、と読みました。

## 思考実験で抽出された原則

10 個のシナリオ (サバイバル / 学園 / ミステリー / 家族 / 冒険 / 戦記 / 商人 / 恋愛 /
村人 NPC / ローグライク) で「いつ何を想起するべきか」を辿ったところ、共通して浮かんだ
性質がいくつかあります。

1. 想起は working memory に無いものを呼び戻すための機構である。直近観測に既に乗って
   いる出来事を recall するのは、想起としての役割を果たしにくい (= prompt token を消費
   しつつ新しい情報を加えない、agent からは「同じ事の反復」に見える)
2. 想起の強さは cue の特異性に比例する。同じ spot に居る (弱) より、ある名前が会話に
   出た (強) の方が、想起の引き金として自然
3. 想起の起点は知覚側にある。目の前に現れた人 / 場所 / 物が、過去を呼ぶ
4. 対象は entity / spot / event-type の 3 種。場所と状況パターン (嵐 / 夜 / 強い感情)
   にも対称的に familiarity が宿る
5. 「忘れていた」感覚は時間ギャップから生まれる。1 tick 前 vs 100 tick ぶり vs 初対面
6. 感情の強い記憶は、cue マッチが弱くても上がってくる。これがないと「ふと過去の恐怖が
   蘇った」のような連想想起は表現できない
7. 会話で出た固有名詞は強い trigger になる。名前が出れば、その対象についての記憶が
   引かれる (既存 `WorldNounMatcher` の方向性)

これらは個別のシナリオ要件ではなく、ある程度の長さを持つ agent の振る舞い全般に
共通する性質に見えます。scenario ごとに ad-hoc に対処するより、汎用認知層として整備
した方が筋に合うのではないか、というのが現時点の判断です。

## 提案する 3 層の memory architecture

```
┌─────────────────────────────────────────────────────────┐
│ Layer 1: Encounter Memory                                │
│   役割: familiarity 信号 (初対面 / 再会 / 初訪問 / 再訪)  │
│   対象: entity / spot / event-type の 3 種 (polymorphic)  │
│   状態: (first_seen_tick, last_seen_tick, count)         │
│   trigger: observation pipeline の入口で照合              │
│   出力: 【現在地と周囲】に注記、recall への signal        │
└─────────────────────────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ Layer 2: Episodic Recall (既存、改修)                     │
│   役割: 関連する経験の能動的想起                          │
│   入力: encounter event + noun_match + emotion + place    │
│   制約: sliding window 範囲外のみ (= 時間下限フィルタ)    │
│   scoring: cue 特異性 + emotional salience                │
└─────────────────────────────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ Layer 3: Semantic Memory (既存 Phase 9-4c)                │
│   役割: 学び / 法則 / 世界知識 (run をまたいで通用する)   │
│   入力: episodic から抽出                                 │
└─────────────────────────────────────────────────────────┘
```

### Encounter Memory の設計判断

- 「何を以て encounter とみなすか」を engine で判断しない方針を取ります。observation
  pipeline を通る entity / spot / event-type を encounter として記録します。閾値判定を
  持たないこと自体が判断です。scenario の感覚モデル (= 何が observation を生むか) に
  そのまま従います
- entity_key は polymorphic な string にします。`player:noa` / `spot:forest_clearing` /
  `weather:storm` / `emotion:fear` のように prefix で kind を表します
- state は最小から始めます。first_seen / last_seen / count の 3 つ。intensity や context
  は必要になってから追加します
- 「忘却」は当面入れません。snapshot resume との相性を考えて全保持から始めて、token
  圧迫が観測されたら decay を検討します

### Episodic Recall の改修 (R1–R5)

| ラベル | 内容 | ねらい |
|---|---|---|
| R1 | sliding window 最古エントリの occurred_tick より古い episode のみ recall。安全 floor (例 5 tick) を併用 | 直近重複の排除 |
| R2 | temporal 軸を recall から削除、cue 軸が全部空の時のみ fallback | 「何も一致しなくても直近が入る」の停止 |
| R3 | 単一 cue マッチを減点、複数 cue 同時マッチを加点 | 状況的関連性の高い想起 |
| R4 | `WorldNounMatcher` の入力を speech / inner_thought / 他 player 発話 にも広げる | 会話起点の想起の自然化 |
| R5 | Encounter event を recall trigger に追加 | 出会いと想起の自然な連動 |

### 「現在の感情」と「過去の感情」を分けて持つ

L4 mid summary は 15 件溜まってから生成される構造で、recall trigger に使う「今」の
感情としては遅延が大きすぎます。そのため次のように分けます。

- **R6a (現在感情の signal)**: 直近 5–10 tick の observation prose を軽量 LLM service で
  分類し、(`dominant_emotion`, `intensity`) を継続的に保持します。Encounter Memory に
  `emotion:fear@0.8` のような event として記録します
- **R6b (過去感情の量化)**: L4 schema に `emotional_intensity` / `dominant_emotion` を
  追加し、episodic store にも focus_emotion を残します。recall scoring で
  `score += intensity * weight` の boost をかけます

これにより「嵐が来た」現在感情の signal が「過去の強い恐怖体験」を想起させる、という
連想想起の経路が成立します。

## 検討した代案と却下理由

### 案 A: 接続先 section に隣接 spot の description を出す

`【現在地と周囲】` の「接続先」項目に、隣接 spot の description 冒頭 1 文を含める案を
最初に検討しました。これだと `forest_clearing` を訪れる前に「枯れ葉が積もっている」と
agent に伝わり、枯れ葉問題は直接解決します。

却下した理由: 行ったことのない場所の中身を、訪れる前に知っている状態が不自然です。
枯れ葉問題を解いたとしても、より一般的な「未知のものに対する反応」が不自然になります。
同じ理由で、未訪問 spot にヒント文字列を埋め込む案 (heartbeat で「あの場所に行ってみる
とよいかも」を inject する案) も却下しました。問題は「未踏の場所がある自覚」が無いこと
であって、答えを先回りで与えることではないと整理しました。

### 案 B: Episodic store の逆引きで familiarity を判定する

新規 subsystem を増やさず、`episodic_store.find_first_episode_mentioning(entity_id)` を
追加して、結果が空なら初対面と判定する案。

却下した理由は 3 つあります。

- episode は chunk close の単位で書かれるため、「同 spot に居るがまだ chunk が閉じて
  いない」状態で初対面判定がブレます
- 毎 turn 全 entity に対して逆引きを走らせるコストが、prompt 構築の hot path で看過
  しにくい
- 「familiarity 信号 (知っている / 知らない)」と「詳細想起 (どんな相手か)」は機能として
  分けた方が拡張しやすい。例えば後者だけ重く、前者は軽い、という非対称な実装が自然に
  なる。「相手のことは知っているが、詳細は思い出せない」という体験を表現する余地も
  生まれる

これらから、Encounter Memory は専用の軽量テーブルとして独立させる方針を選びました。

### 案 C: L5 long summary に「未踏 / 未知」を含めるよう生成プロンプトで誘導する

L5 が `self_image` / `world_view` の 2 軸を持つので、ここに `epistemic_gap` を加えて
「自分がまだ知らないこと」を書かせる案。

却下しない代案として残します。Encounter Memory が低遅延の familiarity 信号、L5
epistemic_gap が低頻度の自己モデル更新、という役割分担で両立します。L5 単独で「初対面の
瞬間反応」を支えるのは生成タイミングの都合で難しいので、Encounter Memory が中心、L5
拡張が補助、という順序を想定しています。

## 開いている論点

実装に踏み出す前に、もう少し議論したい点があります。

1. **Encounter の event-type 拡張の範囲**。entity / spot は具体対象で扱いやすい一方、
   weather / emotion / time のような event-type は周期性があり、count が爆発する
   リスクがあります。intensity 重み付けと連続 dedup を入れるか、event-type を最初から
   分離した小スコープ subsystem として始めるか、未決
2. **R1 の動的境界の安全 floor**。sliding window が idle 期に長期間を覆う場合に recall
   が空になる懸念があります。`SAFETY_FLOOR` の初期値は 5 tick 程度から始めて、観測しながら
   調整する想定
3. **R6a の軽量 LLM service の頻度**。heartbeat 周期に同期 (6 tick に 1 度) で十分か、
   action_result 発生時に都度動かすべきか
4. **「忘却」の必要性**。snapshot resume での integrity を優先するなら全保持。最初は
   decay 無しで始めて、必要になってから入れます
5. **`temporal` 軸の挙動**。R2 で完全削除すると、cue が全く立たないターンで recall が
   空になります。fallback として残すか、残すなら優先度をどう下げるか
6. **PR の粒度**。Encounter Memory 導入 / Episodic recall 改修 / L4-L5 emotional 拡張 は
   依存関係を持つので、独立した 3 PR に分けて、Encounter → recall 改修 → emotional 拡張
   の順で積み上げる想定

## 暫定方針

順序を強く決めるものではありませんが、現時点では次のように考えています。

- Encounter Memory の domain VO / interface / in-memory 実装 + snapshot codec を独立して
  入れる
- observation_pipeline と prompt_builder の wiring を入れて、`【現在地と周囲】` に注記が
  出るところまで動かす
- 短い run (20–40 tick) で挙動を確認する
- 続けて R1 と R5 を入れる
- R6 (emotional salience) は別議論として独立させる

順序や粒度は議論次第で変えます。

## 関連

- `docs/memory_system/episodic_memory_system_spec.md` — 既存 episodic 仕様
- `docs/memory_system/short_term_memory_design.md` — L1 / L4 / L5 設計
- `docs/design_decisions.md` #4 — travel / wait は tool 内で tick を進めない (engine
  不変条件)
- Issue #471 / PR #519 — `do_wait` の nested advance_tick 除去 (200 tick 完走を可能に
  した修正)
- PR #520 — rolling_summary 用 world snapshot codec (本議論の対象 run の前提)
- PR #466 — K run 分析 (集団意思決定が成立した run の質的指標。本ドキュメントの比較対象)
