# ビーイング・アーキテクチャ Part II: 経験生成器としての世界、経験の輸出、スケール

> **Part I** ([being_architecture_master_plan.md](being_architecture_master_plan.md), PR #460)
> は「1 体のビーイングの心」(階層的目標 / 予測 / 学習 / 欲求) の計画だった。
>
> **Part II (本ドキュメント)** は視座を 2 段上げる:
>
> 1. **真の目標の言語化**: プロダクトは「ワールド」でも「シナリオクリア」でもなく、
>    **世界で生きた経験を積んだ AI そのもの**。世界は経験生成器であり、
>    経験は外部 (人間との会話、AITuber 等) に輸出されて初めて価値になる
> 2. **現実装への批判的レビュー**: この視座から見たとき、いまのコードの
>    どこが構造的にまずいかを、対処療法でなく根本原因のレベルで指摘する
>
> 制約 (本計画の全提案が従う):
> - **ハードコードしない** — 世界の風味・シナリオ固有値・運用パラメータをコードに焼かない
> - **対処療法でなく根本解決** — 症状ごとに「対処療法の誘惑」を明示し、退ける
>
> 関連: [scaling_and_coherence_roadmap.md](scaling_and_coherence_roadmap.md) (#346) /
> [design_decisions.md](design_decisions.md) /
> [research_threads/](research_threads/)

---

## 0. ビジョンの再定義 — なぜ世界を作っているのか

原点の問題意識 (2026-06-13 の会話より):

> AI エージェントには経験がない。だから AI らしさが見えてこなくて、AITuber などに
> 使っても面白くない。だったら世界を作ってそこで AI を遊ばせて、そこでの経験を
> 外部に出したり、話せるようにしたら、キャラクター性が出て面白いのではないか。

これを設計の言葉に翻訳すると:

| 概念 | 定義 |
|---|---|
| **経験 (experience)** | 主観的に生きられた出来事の蓄積。episodic (あの時あの場所) + semantic (世界の法則) + L4/L5 (いまの自分の物語) + 関係 (誰と何があったか) の総体 |
| **世界 (world)** | 経験の生成器。希少性・危険・他者・時間が、安全な LLM 対話では決して生まれない「本物の経験」を作る |
| **ビーイング (being)** | 経験の所有者。**世界から独立した存在**であり、世界への参加は人生の一部にすぎない |
| **輸出 (export)** | 経験が世界の外で発露すること。人間との対話で「先週、嵐で店の屋根が飛んでさ」と語れること。AITuber 配信、チャット、二次創作の種 |

**含意 1 — 評価関数が変わる**: 無人島シナリオの「クリア」は中間評価にすぎない
(Part I の階層計画・長期記憶の単体テスト)。本当の評価は
**「この AI と話して、生きてきた感じがするか」**。

**含意 2 — 資産は記憶である**: ワールドのコードは交換可能。シナリオも交換可能。
**交換不可能なのは、各ビーイングが積んだ経験のデータ**。これが消えたら全部やり直し。

**含意 3 — 既存設計の正しさの再確認**: 観測駆動 + 会話ツールの設計は、
人間との会話を「もう 1 つの観測源」として自然に扱える (人間の発話 = `ObservationOutput`、
ビーイングの返答 = speech tool)。これは偶然ではなく、**経験の入口と出口を
ObservationOutput / tool という transport 非依存の形に揃えてきた**から。
この対称性は Part II の最重要資産であり、壊してはならない。

---

## 1. スケーリング計画の現在地監査 (docs × コード)

[scaling_and_coherence_roadmap.md](scaling_and_coherence_roadmap.md) (#346) の
4 Step を、2026-06-13 時点のコードと突き合わせた結果:

| Step | 内容 | 実装状況 | 根拠 (コード) |
|---|---|---|---|
| **Step 1** | LLM 呼び出し (Phase A) の並列化 | ❌ **未実装** | `application/llm/services/llm_turn_trigger.py:49` — `for pid in to_run: run_turn(...)` の完全シリアルループ。`infrastructure/llm/litellm_client.py` は同期 `litellm.completion` のみで `acompletion` 経路なし |
| **Step 2** | tool 適用衝突を「intent failed 観測」で吸収 | ❌ 未実装 | orchestrator に intent queue 経路なし (シリアル前提のため衝突自体が起きない) |
| **Step 3** | heartbeat 撤廃 → per-agent idle timer (スパースハートビート) | ✅ **実装済み** | `application/observation/services/heartbeat_observation_emitter.py` — 「N tick おきに必ず (floor)」から「N tick 沈黙したときだけ (ceiling)」へ転換済み。`note_player_activity` で active player への冗長発火を抑止、`is_traveling_provider` で移動中除外 (#404/#407)。観測 `schedules_turn=True` の audit も #412 で実施済み |
| **Step 4** | spot-level lock + shard commit (サーバ分割の前段) | ❌ 未実装 (計画通り将来) | SQLite が書き込みを直列化するため、Postgres 移行 ([sqlite_full_migration_roadmap.md](sqlite_full_migration_roadmap.md)) とセット |

### ⚠️ ドキュメントとコードの矛盾 (要訂正)

[design_decisions.md](design_decisions.md) 判断 9 に
**「並列化済 (#346 Step 1) で wall time はそれなりに改善した」** とあるが、
上記の通り **turn 実行の並列化 (Step 1) は未実装**。実装済みなのは
episodic 主観補完の ThreadPool (#309) と短期記憶 scheduler の thread_pool モード
(別系統の非同期化) であり、turn の Phase A 並列化ではない。

これは小さな記述ミスに見えるが、**「docs が事実とずれていると、それを読んで
判断する未来の作業者 (人間も agent も) が誤る」** という silent failure の一種。
設計判断 5 (silent failure を構造で塞ぐ) の精神に従い、**本 PR とは別に
design_decisions.md の当該行を訂正する PR を切るべき** (1 PR = 1 目的)。

### 監査からの評価: Step 1-4 は必要だが、根本ではない

Step 1-4 はすべて **「熟慮 1 回あたりのスループット」と「起床回数」** の改善であり、
コスト構造の根本等式:

```
起床 1 回 = フル prompt 構築 1 回 = LLM call 1 回 (4-8K token)
```

には触れない。Step 3 (実装済み) で「静かな世界はほぼ無料」になったが、
**「賑やかな世界」のコストは依然 LLM call 数に正比例**する。
1000 体が市場で活動する世界は、Step 1-4 を全部入れても回らない。
根本解は §2 R3 (二過程アーキテクチャ) で扱う。

---

## 2. 批判的レビュー — 5 つの根本問題

各問題を「症状 → 対処療法の誘惑 (退ける) → 根本原因 → 根本解」の形式で書く。

### R1: ビーイングがプロセスに寄生している (存在の所有権問題) ⭐ 最重要

**症状**:
- run が終わるとビーイングは消える。次の run の「エイダ」は同名の別人
- L4/L5 は `RollingSummaryShortTermMemory` のプロセス内 dict、memo は
  `InMemoryMemoStore`、todo は `InMemoryTodoStore` — すべて揮発
- episodic / semantic は SQLite 実装が**存在する** (`infrastructure/repository/
  sqlite_subjective_episode_store.py` 等) が、`SUBJECTIVE_EPISODE_DB_PATH` による
  **store 単位のオプトイン**であり、「ビーイング 1 体を丸ごと保存・復元する」単位がない

**対処療法の誘惑**: 「全 InMemory store に SQLite 版を足して env で繋ぐ」。
→ 退ける。store が 10 個に増えるたびに env が 10 個増え、「L4 は残ったが memo が
消えた」型の **部分復元 silent failure** を量産する (PR #439-#446 で学んだ
「2 箇所目の env 解釈」問題の再演)。

**根本原因**: **「ビーイング」という集約がコード上に存在しない**。
いま存在するのは (a) world 側の player aggregate (HP / inventory = 肉体) と
(b) application 層に散在する記憶サービス群 (= 心の破片) であり、
**心を所有する主体がいない**。だから「保存」も「復元」も「移動」も主語を欠く。

**根本解 — Being を第一級の bounded context にする**:

```
domain/being/  (新 bounded context, 17 個目)
├── aggregate/being.py          # BeingId を root とする集約
│     - identity: persona 不変核 (名前 / 第一人称 / 価値プロファイル)
│     - memory_refs: 各記憶 store への所有参照 (L4/L5 世代, episodic, semantic, memo, 関係)
│     - attachments: 現在どの世界のどの player に「乗って」いるか (0..1)
├── repository/being_repository.py   # save/load = ビーイング丸ごとの snapshot/restore
└── ...
```

- **世界への参加は attachment (関係) であって identity ではない**。
  `Being(being_id=ada) が world=survival_island_v2 の player_id=1 に乗る`。
  detach しても経験は Being に残り、別世界・別 run・外部対話 (R4) に持ち越せる
- 全記憶 store のキーを `player_id: int` から **`being_id` に揃える**
  (現 `player_id` は attachment 経由で解決)。これが「丸ごと保存」を 1 メソッドにする
- 永続化は store 単位 env ではなく **Being 単位の設定 1 箇所**
  (`ResolvedLlmRuntimeConfig` に集約 — 設計判断 11 準拠)
- 復元の完全性は「全 store が揃って初めて Being が load 成功」の **all-or-nothing** で
  保証 (部分復元を構造的に禁止 — 設計判断 5 準拠)

**これは Part I の前提でもある**: Part I の C4 (信念) / C6 (他者モデル) / S2 (関係台帳)
はすべて「誰の信念か」を `player_id` で持つ設計になっている。Being 集約を先に
立てないと、これらが全部 run-scoped で作られてしまい、後からの移行コストが膨らむ。

### R2: 時間が単一ワールドの tick に幽閉されている

**症状**: 経験のタイムスタンプが `occurred_at (datetime)` と `tick (int)` の
二重系で、tick は「いま動いている 1 つの世界のループカウンタ」を暗黙の前提にする。
外部対話 (リアルタイム) や世界停止中の経験は、この時間軸上に置き場がない。

**対処療法の誘惑**: 「外部対話用に tick を偽造する (配信 1 分 = 1 tick とみなす等)」。
→ 退ける。換算率というハードコードが生まれ、複数世界・複数 interface で破綻する。

**根本原因**: 「ビーイングの主観時間」と「世界のシミュレーション時間」が
未分離。人間で言えば「カレンダー」と「職場のタイムカード」を同一視している。

**根本解**: **ビーイングの経験は実時間 (`occurred_at`) を一次キーとする全順序列**とし、
`world_id + tick` は「その経験がどの世界のいつ起きたか」を示す**属性**に格下げする。
- 幸い episodic / observation 系は既に `occurred_at: datetime` を必ず持っている
  (`ObservationEntry`, `SubjectiveEpisode`)。やることは「tick を主キー扱いしている
  箇所の棚卸し」と「経験 record への `world_id` 属性追加」で、革命ではなく整理
- これにより「水曜は島で 30 tick 生き、木曜は配信で人間と話し、金曜にまた島へ」
  という人生が単一タイムラインに自然に並ぶ

### R3: 「起床 = フル LLM call」の等式 (習慣レイヤーの不在)

**症状**: §1 の監査の通り。スパースハートビート (Step 3) で起床回数は
アクティビティ比例になったが、起床 1 回の単価 (フル prompt + LLM call) は固定。
さらに物語面でも: 毎起床がフル熟慮なので、ビーイングに「考えごとをしながら
ぼんやり歩く」「いつも通りに店を開ける」という**無意識の生活の質感がない**。

**対処療法の誘惑**: 「もっと安いモデルに全部差し替える」「max_turns を絞る」。
→ 退ける。前者は熟慮の質 (設計判断 9: 判断ミス > wall time) を落とし、
後者は行動量を削るだけで単価構造を変えない。

**根本原因**: アーキテクチャに **System 1 (習慣・自動行動) が存在せず、
System 2 (熟慮) しかない**。人間の行動の大半は習慣なのに、ビーイングは
全行動を熟慮で賄っている。これはコスト問題であると同時に人間らしさの問題。

**根本解 — 二過程アーキテクチャ (Habit Layer)**:

```
観測到着 (schedules_turn=True)
   ↓
[HabitMatcher]  … LLM を呼ばない。Being が保有する習慣 (条件 → 行動列) と照合
   ├─ 一致 & surprise 低 → 習慣の次の 1 手を実行 (LLM call ゼロ)
   └─ 不一致 or surprise 高 (Part I C3 の SurpriseEvaluator を流用)
        ↓
      [フル LLM turn]  … 熟慮。結果として新しい習慣を形成・改訂できる
```

- **習慣は Being の所有物** (R1 の集約に `habits` として置く): 条件 (cue 集合) +
  行動列 + 形成根拠 (episode 参照) + 信頼度。**ハードコードされたルーチンではなく、
  熟慮の結果から昇格される** (Part I C4 の信念昇格と同型のメカニズム —
  「同じ文脈で同じ行動列を N 回選んだら習慣候補」)
- 習慣実行中も観測は溜まり、episodic 化される (経験は欠けない)。surprise が
  閾値を超えた瞬間に熟慮へ escalate (C3 がそのまま switch になる)
- **これが Step 1-4 と直交する根本のスケール解**: 1000 体のうち熟慮が必要なのは
  各 tick で数 % になり、LLM コストは「世界の事件量」に比例するようになる。
  「平穏に生活する人」は文字通りほぼ無料で生活する
- 派生効果: LOD (詳細度) シミュレーションが無料で付く — 観測者が見ていない
  地域は習慣のみdocs で回し、注目時に熟慮を解凍

### R4: 経験の出口がない (輸出インターフェースの不在)

**症状**: 経験を蓄積する経路は揃ってきたが、**世界の外から経験に触れる手段が
trace.jsonl の grep しかない**。「エイダ、先週どうだった?」に答えるパスがない。

**対処療法の誘惑**: 「trace を要約して台本を作る別スクリプト」。
→ 退ける。それは録画の編集であって、**本人が語る**のではない。キャラクター性は
「記憶を持つ本人が、いま、相手に合わせて語る」ことから出る。

**根本原因**: prompt 構築が「世界内の行動選択」という単一の合成しか持たない。
しかし材料を見れば、`DefaultPromptBuilder` は section モジュラー
(`PromptSectionProviders`) で、記憶セクション (L5 / L4 / episodic recall /
semantic / memo) は**世界状態と独立に組める**。能動想起ツール
(`memory_explore_related`) も既にある。**欠けているのは第二の合成だけ**。

**根本解 — Interview Composition (対話用の第二プロンプト合成)**:

```
InterviewPromptBuilder (新規。DefaultPromptBuilder と同じ部品の別合成)
  §1 いまの自分 (L5: 自己像/世界観/最終目標)        … 世界の記憶そのまま
  §2 関連する学び (semantic)                        … 同上
  §3 最近の流れ (L4)                                … 同上
  §4 想起した記憶 (会話内容を situation_cue 化して passive recall) … 同上
  §5 この対話の文脈 (相手は誰か / これは配信か私信か / 開示ポリシー)
  §6 対話履歴 (人間の発話 = ObservationOutput として)
  tool: speech 系 + memory_explore_related (能動想起) + 対話終了
```

- **人間の発話は観測、返答は speech tool** — 世界内会話と完全に同型 (含意 3 の
  対称性を保つ)。対話セッション自体も episodic 化され、**「配信で人間に
  こう聞かれた」が世界に持ち帰られる経験になる** (翌日、世界内で仲間に話せる)
- 対話中、世界では「不在」(R1 の attachment を一時 detach するか、世界内で
  「眠っている」扱いにするかはシナリオデザインの選択) — **配信は人生の一部**になる
- 開示ポリシー (世界の何をどこまで話してよいか、メタ発言の扱い) は
  **ハードコードせず Being / シナリオ設定のデータ** (§5 に注入)
- 速度要件: 対話はリアルタイムなので、ここでも R3 の二過程が効く
  (相槌・定型応答は習慣、深い話は熟慮)

### R5: 「世界の風味」がコードに滲んでいる (ハードコード監査)

**症状** (例):
- `heartbeat_observation_emitter.py:58` — `_HEARTBEAT_PROSE = "周囲に大きな変化はない。少し時間が経った。"` が application 層の定数。砂漠でも吹雪でも市場でも同じ文言
- `PromptLimits.default_action_instruction` のフォールバック日本語文
- L4/L5 圧縮プロンプト・system prompt テンプレートの長文日本語が services 内の文字列リテラル

**対処療法の誘惑**: 「気づいたものから i18n 的に外部ファイル化」。
→ 半分正しいが、基準なしにやると「何を外に出すべきか」で毎回議論になる。

**根本原因**: **「認知の構造」と「世界の風味」の区別が未定義**。
PR #455/#456 (objective_text のシナリオ駆動化、hardcoded「脱出」の撤廃) で
方向は出ているが、原則として明文化されていない。

**根本解 — 区別の原則を立て、design_decisions.md に追加する**:

> **認知の構造** (どう考えるかの指示: L4/L5 圧縮の出力規約、主観 schema の意味、
> 予測の書き方) は **コードに置いてよい** — これはビーイングの OS であり、
> 世界が変わっても不変。
> **世界の風味** (何が見えるか・どう聞こえるかの内容: heartbeat の文言、
> 場所や物の描写、目的文) は **シナリオ / コンテンツ層のデータ** —
> provider 注入 (objective_text_provider が前例) で届ける。

このリトマス試験紙: 「**シナリオを砂漠の隊商都市に替えたとき、この文字列は
変わるべきか?**」— Yes ならデータ、No ならコード。
`_HEARTBEAT_PROSE` は Yes (隊商都市なら「市場の喧騒が続いている」) なので、
`heartbeat_prose_provider` としてシナリオ注入に直すのが一例。

---

## 3. 統合ロードマップ — Part I との合流

Part I (PR #460, C1-C8 / Phase 0-7) は**そのまま進める**。Part II は並走する
別トラックとして、依存関係だけ明示する:

```
Part I  (心):    Phase 0 (C8 metrics) → 1 (C1 Plan) → 2 (C2 Prediction) → 3 (C3 Surprise) → …
                                                                  │
Part II (存在):  P-1 Being 集約 (R1) ──────────────┐              │ C3 を流用
                 P-2 主観タイムライン (R2)          │              ▼
                 P-3 ドキュメント矛盾の訂正 (§1)    ├→ P-4 習慣レイヤー (R3) → P-5 Interview (R4)
                 P-0 風味/構造の原則 doc 化 (R5)    │
スケール:        Step 1 並列化 → Step 2 intent 吸収 (scaling roadmap、独立に着手可)
```

### フェーズ表

| Phase | 内容 | 規模 | 着手条件 / 備考 |
|---|---|---|---|
| **P-3** | design_decisions.md 判断 9 の「並列化済」記述を訂正 | 数行 | 即。事実と docs の一致は全判断の前提 |
| **P-0** | 「認知の構造 / 世界の風味」原則を design_decisions.md に追加 + 既存ハードコード棚卸し issue 化 | doc + 棚卸し | 即 |
| **Step 1-2** | scaling roadmap の並列化 + intent 吸収 (既存計画のまま有効) | ~500 行 | Part I Phase 1-2 の run が遅くて回らなくなる前に。litellm `acompletion` 化を含む |
| **P-1** | Being bounded context (集約 + repository + 全 memory store の being_id 化 + all-or-nothing snapshot/restore) | 大 (3-5 PR) | **Part I Phase 4 (C4 信念) より前が強く望ましい** — 信念・関係を run-scoped で作らないため |
| **P-2** | 主観タイムライン (occurred_at 一次化 + world_id 属性 + tick の属性格下げ棚卸し) | 中 (2 PR) | P-1 と同時期 |
| **P-4** | 習慣レイヤー (Habit 集約 + HabitMatcher + 熟慮からの習慣昇格 + C3 escalation 接続) | 大 (3-4 PR) | Part I C3/C4 安定後 (昇格メカニズムを共有するため) |
| **P-5** | Interview Composition (第二プロンプト合成 + 対話セッション adapter + 開示ポリシー) | 中 (2-3 PR) | P-1 (Being が世界から独立していること) + P-4 (リアルタイム応答性) 後。**ここが原点のビジョンの初回実証** |
| **P-6** | 村 run 評価環境 (5-10 体 / 店・畑・酒場 / シナリオ目標なし / society metrics で創発を観測) | シナリオ + metrics | Part I Phase 5 (ドライブ) + P-4 (習慣) 後が理想。「平穏に生活する人」は習慣がないと成立しない |

### マイルストーン (ビジョン言語で)

1. **M1「死ななくなる」** (P-1/P-2): run を止めてもエイダはエイダのまま。翌日続きから生きる
2. **M2「日常を生きる」** (P-4 + Part I Phase 5): 事件のない日は習慣で暮らし、LLM コストは事件量比例になる
3. **M3「語れる」** (P-5): 世界の外の人間に、自分の言葉で先週の嵐の話をする。**原点のビジョンの達成判定点**
4. **M4「社会が見える」** (P-6 + Part I 完走): 村で誰が何を始めるかを、誰も指示せずに見届ける

---

## 4. 議論したいポイント (research thread 形式)

| 優先 | 問い | 想定する分岐 |
|---|---|---|
| ⭐⭐⭐ | **Being 集約の粒度**: 記憶 store 群を Being 集約の「内部」にするか、「being_id で束ねた別 store 群」のままにするか | (a) 真の DDD 集約 (トランザクション境界も Being) / (b) being_id を共有キーにした store 連合 + all-or-nothing loader (軽い)。**起案者の推し: (b) から始めて必要なら (a)** — 記憶 store は書き込み頻度が高く、集約に閉じるとロック競合する |
| ⭐⭐⭐ | **習慣の表現形式**: 条件→行動列を構造化データにするか、自然言語 (LLM が読む) にするか | (a) 構造化 (cue 集合 + tool 列。機械 match 可能 = LLM ゼロ) / (b) 自然言語 + 軽量 LLM match (柔軟だが単価が残る) / (c) ハイブリッド (match は構造化 cue、内容は両方) |
| ⭐⭐ | **対話中の世界内の扱い**: detach (不在) か、睡眠扱いか、世界停止か | 物語整合性 vs 運用の単純さ。シナリオデータで選べる形 (ハードコードしない) が筋か |
| ⭐⭐ | **Step 1 並列化の時期**: Part I Phase 1-2 と前後どちらか | run が 1 回 40-120 分の現状で Phase gate を回す回数を考えると、先に入れる価値が高い |
| ⭐⭐ | **L4/L5 の永続化形式**: P-1 で SQLite に載せるとき、世代 deque をどう表現するか | append-only event log (再生で復元) / 最新 snapshot のみ。episodic が一次資料なので snapshot で十分という読みもある |
| ⭐ | **多言語/多風味**: R5 の provider 化を進めると、同一ビーイングが日本語世界と英語配信を跨ぐ可能性が出る。言語は Being の属性か、interface の属性か | 当面は日本語固定でよいが、構造は interface 属性に寄せておくのが安全 |

---

## 5. この計画が変えないこと

- **観測駆動 + ツールによる行為**という基本対称性 (含意 3)。Part II の全提案は
  この対称性の「適用範囲を世界の外へ広げる」ものであり、形を変えない
- **設計判断 1-12**。特に prefix cache 不変 (Interview Composition も独自の
  stable prefix を持つ)、ctor 注入、fail-fast、xfail-strict はそのまま適用
- **「エージェントの選択をスクリプトに書かない」**。習慣も信念も Being 自身の
  経験から昇格されるのであって、デザイナが注入する台本ではない
- **Part I の Phase 計画**。Part II は順序の依存 (P-1 を C4 より前に) を 1 点
  要求する以外、Part I を変更しない

---

更新日: 2026-06-13
担当: Motifman + Claude (Fable 5)
状態: **批判的レビュー + 計画 (議論待ち)** — §4 の決定後に各 P-x を PR 化
