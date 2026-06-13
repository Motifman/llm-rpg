# AI エージェント記憶アーキテクチャ調査 — 連続的存在と環境横断の設計に向けて

調査日: 2026-05-24
調査者: Claude (4並列リサーチエージェント)

## このレポートの読み方

このプロジェクト (`llm-rpg`) は AI エージェントを「ゲーム世界の中で連続的に存在する人物」として作ることを目指している。連続とは、ある時点のエージェントと時間が経った後のエージェントが**外から見て同じ存在として整合**することを指す。最終ビジョンは AI を「指示をこなすロボット」ではなく「人間と区別のつかない存在」として人間世界に接続することにある。

現状の実装は `docs/memory_system/episodic_memory_system_spec.md` にあるとおり、すでに Experience Trace → Subjective Episode → Cue Index → Associative Memory Graph → Reinterpretation → Semantic Promotion の階層を持つ。多くの市販/OSS の memory system よりも踏み込んでいる。

このレポートは 4 つの観点で外部知見を集約し、最後に**プロジェクトに直接効く優先度付きの提言**としてまとめている。

- 第1部: プロダクション/OSS の長期メモリ実装 (Mem0 / Letta / Graphiti / A-MEM / LangMem / cognee)
- 第2部: 学術系の連続的エージェント研究 (Generative Agents / Voyager / Concordia / Project Sid / A-MEM / Reflexion / MemGPT / Nemori)
- 第3部: 認知科学・哲学から見た「同じ人として連続する」とは
- 第4部: 環境抽象化と観測/行動の共通プロトコル設計
- 第5部: プロジェクトへの統合提言 (優先度付き 10 項目)

---

## 第1部: プロダクション/OSS の長期メモリ実装

### 1.1 Mem0 (`mem0ai/mem0`)

**コア**: 会話 → LLM 抽出 → vector + graph + SQLite 履歴。新事実は LLM 比較で `ADD/UPDATE/DELETE/NONE` に正規化。

**データモデル**:
- Memory: `{id, text, hash, embedding, metadata{user_id,agent_id,run_id}}`
- History row (SQLite): `(memory_id, event, old_value, new_value, timestamp)` ← 監査ログ
- Entity store: `linked_memory_ids[]`
- Graph store (Neo4j/Memgraph): `(src)-[rel]->(dst)`

**書き込みパス (9 phase)**: 直近 10 message を context に → 関連既存メモリを検索 → **整数 ID にマップしてからプロンプトへ** (UUID 直渡しはハルシネーション源) → fact 抽出 → md5 で重複排除 → **update プロンプト**で各新事実を ADD/UPDATE/DELETE/NONE 判定 → embed → vector store。

**時間性**: `created_at/updated_at` と history table のみ。bi-temporal なし。事実は上書き、過去版は監査ログ。

**示唆**: 整数 ID マッピングは Reinterpretation で LLM に既存 Episode を提示する時にそのまま使える。上書きモデルはプロジェクトの「Trace 不変」原則に逆らうので、抽出パイプライン全体は移植せず、ID マッピングのテクニックだけ拾う。

参照: `mem0/configs/prompts.py` の `DEFAULT_UPDATE_MEMORY_PROMPT` / `mem0/memory/main.py` の `_add_to_vector_store`。

---

### 1.2 Letta (旧 MemGPT) (`letta-ai/letta`)

**コア**: OS のページングのアナロジー。LLM が自分自身の context window を編集する tool を持つ。

**データモデル**:
- **Core Memory** (in-context, system prompt 内): `Memory.blocks: List[Block]`。各 Block は `(label, value, limit, read_only)`。典型: `persona` / `human`。
- **Archival Memory** (out-of-context, vector): 長期事実 + tag。
- **Recall Memory** (out-of-context, message DB): 過去会話の全文。BM25+semantic hybrid。
- **FileBlock**: ファイル添付を Block 化。
- **Agent File (`.af`)**: persona / human / archival / tool 設定をシリアライズ。**Letta agent をクロスフレームワークで持ち出せる先行例**。

**self-editing tool**: `core_memory_append`, `core_memory_replace`, `archival_memory_insert`, `memory_rethink`, `conversation_search`。受動抽出パイプラインを持たず、LLM が「核に昇格すべき」と自己判断する設計。

**Context 管理**: token 閾値超で `summarize_messages_inplace`。Sleep-time agent がバックグラウンドで block を整理する。

**示唆**:
- `persona` Block の発想 = アイデンティティの常駐基盤として、NPC ごとに `persona` / `core_values` / `current_concerns` の 3 Block を持たせると人格 drift を構造的に抑えられる。
- `.af` は「自己だけを環境から切り離す」ベストプラクティス。プロジェクトの `AgentSelf` portable 化のフォーマット参考に直結。
- LLM 自身が記憶階層管理 tool を呼ぶ設計は、NPC が「意識的に思い出そうとする / 心に刻む」を意味のある game action として表現できる。

---

### 1.3 Zep / Graphiti (`getzep/graphiti`)

**コア**: temporal knowledge graph。エピソード取り込みごとに増分でエンティティ/リレーションを抽出し、矛盾は edge を**削除せず invalidate**。「今真の事実」と「過去 t 時点で真だった事実」両方をクエリ可能。

**データモデル**:
- **EpisodicNode**: `type ∈ {text, message, json}`, `content`, `reference_time`, `valid_at`
- **EntityNode**: 抽出エンティティ。summary が episode 越しに進化。
- **EntityEdge**: `(src, rel, dst, fact_text, valid_at, invalid_at, created_at, expired_at, episodes[])` の **bi-temporal**。
  - `valid_at / invalid_at`: 現実世界で事実が真だった期間
  - `created_at / expired_at`: グラフ上の登録/失効時刻 (システム時間)
- **EpisodicEdge (MENTIONS)**: provenance を保持。

**書き込み**: `extract_nodes` → `resolve_extracted_nodes` (既存と UUID 解決) → `extract_edges` (LLM、REFERENCE_TIME で相対表現を解決) → `resolve_extracted_edges` (`duplicate_facts` と `contradicted_facts` を idx で返す) → 矛盾した既存 edge は `invalid_at = new edge の valid_at` でマーク → MENTIONS edge を張る。

**時間性**: 調査対象の中で**最も精緻**。bi-temporal が完全に第一級。

**示唆**: **Semantic Promotion 層に bi-temporal を導入する価値が極めて高い**。「過去のあの時点では NPC A は B を友人だと思っていた」を Cue として復元できる = まさに人物の時間的整合の核。削除せず invalidate するルールは Reinterpretation と相性が良い (古い解釈は invalid だが Trace としては残る)。

参照: `graphiti_core/utils/maintenance/edge_operations.py` L254-565、`graphiti_core/prompts/{extract_edges,dedupe_edges}.py`。

---

### 1.4 A-MEM (`WujiangXu/AgenticMemory`, NeurIPS 2025)

**コア**: Zettelkasten 発想。各 memory note が自律的に他ノートにリンクを張り、**新規ノート追加が既存ノートの context/tags を書き換える** (memory evolution)。

**データモデル (MemoryNote)**:
```
content, id, keywords[], links[], context (1文要約),
tags[], category, timestamp, last_accessed,
importance_score, retrieval_count, evolution_history[]
```

**書き込み (`add_note` → `process_memory`)**:
1. `analyze_content`: LLM が keywords / context / tags を JSON 抽出
2. `find_related_memories(k=5)`: vector 近傍
3. **Evolution prompt**: 「Should this memory be evolved? What actions (`strengthen`, `update_neighbor`)? If update_neighbor, you can update context and tags of these memories.」
4. LLM JSON で `suggested_connections`, `new_context_neighborhood[]`, `new_tags_neighborhood[]` を適用 → **隣接ノートのメタデータが書き換わる**

**示唆**: **Reinterpretation 層の参照実装としてほぼそのまま流用可能**。新規 Episode が cue で既存を引き、LLM に「strengthen / update_neighbor」相当をやらせる。

**ただし重要な制約**: A-MEM は neighbors を**物理的に書き換える**。プロジェクトでは「主観的に書き換わるが Experience Trace は不変」を守るため、**上書きではなく派生 Subjective Episode を発行**する派生に留めるべき。`evolution_history[]` を Subjective Episode の version 管理に流用するのが筋。

---

### 1.5 LangGraph / LangMem

**コア**: 記憶を semantic / episodic / procedural の三類型に整理。LangGraph `BaseStore` 上に namespace 階層 (org→user→ctx) で配置。hot-path / background (`ReflectionExecutor`) を分離。

**型別**:
- **Semantic**: `collection` (無制限事実) と `profile` (単一 JSON document update)
- **Episodic**: `(situation, thought_process, outcome, why_it_worked)` で few-shot に直接使える形
- **Procedural**: **agent の system prompt そのもの**。`create_prompt_optimizer()` がフィードバックから書き換える

**示唆**: 「procedural memory = system prompt の自己編集」という発想が強力。プロジェクトでは Semantic Promotion 層に Letta `persona` Block を入れ、procedural skill (Voyager 流) を別 tier で持つと三層分類が綺麗に揃う。

---

### 1.6 cognee (`topoteretes/cognee`)

**コア**: ECL (Extract-Cognify-Load) パイプライン。文書 → chunk → entity/relation → KnowledgeGraph + Vector を**同一 DataPoint** で扱う。`remember / recall / forget / improve` の 4 操作 API。

**注目データ**:
- **Event**: `name, description, time_from: Timestamp, time_to: Timestamp, location`
- **Timestamp**: year/month/day/hour/minute/second をフィールド分解。欠損時は LLM が部分指定可能 ← 相対時間/曖昧時間を吸収

**示唆**: ゲーム内時間 (Day3 18:00) や曖昧表現 ("先週") を扱う際、cognee の Timestamp 分解構造が便利。

---

### 1.7 横断比較

| 項目 | Mem0 | Letta | Graphiti | A-MEM | LangMem | cognee |
|---|---|---|---|---|---|---|
| 抽出方式 | LLM パイプライン | **LLM 自身が tool で書く** | LLM (node/edge 抽出+解決) | LLM (note+evolution) | LLM manager/reflector | LLM タスクチェイン |
| Conflict 解決 | ADD/UPDATE/DELETE/NONE | LLM が `core_memory_replace` | `duplicate+contradicted` を invalidate | strengthen/update_neighbor | schema-driven 上書き | DataPoint update |
| 時間モデル | created/updated + 履歴 | message timestamp | **bi-temporal** | timestamp + evolution_history | なし | structured Interval + ontology_valid_at |
| 既存記憶の書換 | UPDATE | 自己編集 | **invalidate (削除しない)** | **neighbors を書き換える** | UPDATE | DataPoint update |
| 自己アイデンティティ | なし | **persona Block** | なし | なし | procedural memory | なし |

**結論**: プロジェクトの方向性 (Trace 不変 + 主観連続性) は OSS 主流の「最新事実上書き」モデルに逆らう **正しい方向**。最も親和性が高いのは Graphiti (invalidate) + A-MEM (evolution) + Letta (persona) のハイブリッド。

---

## 第2部: 学術系の連続的エージェント研究

### 2.1 Generative Agents (Park et al. 2023, Stanford Smallville)

論文: arXiv:2304.03442 / 実装: `joonspk-research/generative_agents`

**3 層**: Memory Stream (append-only 自然文+timestamp+importance+embedding) / Reflection (high-level insight ツリー、重要度合計 150 超で発火) / Planning (day→hour→5-15min)。

**retrieval スコア** (実装で α=1):
```
score = α_recency · 0.995^(hours) + α_importance · LLM(1-10) + α_relevance · cosine
```
すべて min-max 正規化で [0,1]。

**Reflection の再帰**: 反省は memory stream に再投入され、reflection-of-reflection の木構造ができる。

**示唆**:
- importance を LLM (1-10) でつける単純さは現プロジェクトでも採用価値あり。Reflection / Reinterpretation の発火閾値が単純化する。
- recency 0.995^h は最小の忘却モデル。プロジェクトの sliding_window と並列の長期 retrieval スコアに使える。
- **Reflection の再帰ツリー化**: 現 Reinterpretation 層を reflection-of-reflection を許す構造にすれば、信念体系が自然と階層化される。

### 2.2 Voyager (NVIDIA 2023, Minecraft)

**コア**: 経験を**実行可能 JS 関数**として skill library に蓄積する生涯学習エージェント。`function name → (docstring, code, embedding(docstring))`。

**示唆**: 「Bob は釣りができる人」を文章ではなく**行動ポリシー断片**として保存できる。プロジェクトでは Semantic Promotion の隣に **Procedural Skill Library** を別 tier で立てる価値が高い。

### 2.3 Concordia (DeepMind 2023)

**コア**: **Game Master + Entity-Component agent**。世界更新と物理整合性判定は GM (LLM) が司る。各 agent は Component の合成で、各 component が "現在の質問に対する context 断片" を返し、最終 act component が統合。

**示唆**:
- **GM 役割分離**: 世界の客観事実は世界側、NPC は subjective stream のみ持つ。**外部入力 (YouTube/チャット) を「世界観測」の同一プロトコルに乗せる目標は、この分離があると無理なく成立する**。GM = 観測プロトコル変換器の位置づけ。
- Component 構成は現 memory 多階層を**機能別 component**として再パッケージする視点を与える。

### 2.4 Project Sid / PIANO (Altera 2024)

**コア**: 500-1000+ エージェントの Minecraft 文明。**Cognitive Controller (CC) という single narrow channel** に複数モジュール出力を集約 → 下流条件付け。「口では和平、身体で攻撃」を防ぐ。

**示唆**: **CC (narrow bottleneck) はこのプロジェクトに最も重要な示唆の一つ**。多階層 memory が独立に出力候補を出すと人格が分裂する。単一の "意図 stream" を通して下流に流す bottleneck を入れる価値が極めて高い。

### 2.5 AI Town (a16z)

Generative Agents の Convex/TypeScript 再実装。**会話終了 → GPT 要約 → embedding → Convex vector DB**。Convex の reactive query で他クライアントへ自動伝播するのは、外部 UI 統一プロトコルと相性が良い。

### 2.6 A-MEM (Xu et al. 2025) ※第1部と重複

### 2.7 Reflexion (Shinn et al. 2023)

**コア**: 外部 feedback → LLM の self-critique → episodic buffer → 次試行 prompt に注入。

**示唆**: NPC の「あの時 Alice を信じて裏切られた → 今後は警戒する」を**形式知化**するのに直接適用可能。Semantic Promotion で「失敗の教訓」を独立 tier にすべし (Voyager の skill が成功側、Reflexion の reflection が失敗側)。

### 2.8 MemGPT (Letta 前身) ※第1部と重複

### 2.9 Episodic Memory is the Missing Piece (arXiv 2502.06975)

LLM agent の episodic memory の必要 5 性質: long-term storage / explicit reasoning / **single-shot learning** / **instance-specific** / **contextual (when/where/why)**。In-Context / External / Parametric の hybrid を提案。

**示唆**: プロジェクトの trace → episode → semantic は hybrid 路線。**Parametric consolidation (NPC ごとに LoRA で episode を焼き込む)** は未実装なら強い差別化要素。長期的には「文字通り神経が形作られる」連続性が手に入る。

### 2.10 Nemori (2025, arXiv 2508.03341)

認知科学着想の 2 原理: **Event Segmentation** (対話 stream を意味的 episode に自律分割) + **Predict-Calibrate** (FEP 由来、予測誤差から学ぶ)。Full Context より 88% 少ないトークンで上回る性能。

**示唆**:
- **Event Segmentation** は現 `chunk_boundary` 設計に直結。境界決定を「予測誤差ピーク」で行うのは脳科学的にも妥当性が高い。
- Predict-Calibrate は spec の `expected` / `prediction_error` フィールドとドンピシャ。

### 2.11 Character.AI の実態 (arXiv 2511.10652)

商用最大手の現状: session buffer + summary embedding のみで**真の長期記憶なし**、persona description で「一貫性の錯覚」を演出。

**示唆**: **人格核の頑健さ > 記憶の完全性** という優先順位は、商用で十分機能していることを示す重要なベースライン。プロジェクトでも `persona` Block (Letta 流) を不動の幹に据えるのは妥当。

---

## 第3部: 認知科学・哲学から見た「同じ人として連続する」

### 3.1 記憶階層 (Tulving / Schacter)

- Tulving: **episodic** (時間-場所付き) と **semantic** (脱文脈化知識) を分離。episodic の本質は **autonoetic consciousness** (自己が時間軸を旅する自覚)。
- Schacter の **Constructive Memory Framework**: 記憶は録画ではなく**再構成**。**過去想起と未来シミュレーションは同じ回路**。
- **Seven Sins of Memory** (transience, absent-mindedness, blocking, misattribution, suggestibility, bias, persistence) は適応的機能の副作用。**バグではなく仕様**。

**実装ヒント**:
- `EpisodeKind = OBSERVED | RECALLED | SIMULATED_FUTURE | SIMULATED_COUNTERFACTUAL` を first-class にし、Cue index は kind を跨いで張る。「明日また会う約束」と「昨日会った思い出」が同じ associative graph で繋がる。
- **Procedural promotion** を Semantic Promotion とは別に持つ (繰り返した行動が手続き化され、いちいち episode を引かなくなる)。
- **Personal semantic** (=「私は猫が好き」) と **general semantic** (=「猫は哺乳類」) を分離。前者は narrative identity の素材。

### 3.2 Narrative Identity (McAdams)

「自分がどうやって今の自分になりつつあるかを説明するために内面化された、進化し続ける物語」。構成要素: high/low/turning points、redemption と contamination シーケンス、agency と communion テーマ。

**Self-defining memories** (Singer): 鮮明・繰返し想起・感情強・現在の関心とリンク・他記憶と接続する記憶群がアイデンティティの骨格。

**実装提案 — `LifeStoryDigest` 集約**:
```python
nuclear_episodes: list[EpisodeId]    # self-defining memories の参照 (容量 ~7±2)
themes: dict[ThemeKey, float]        # agency, communion, redemption, contamination
imago: list[Persona]                 # 「人格化された自己役割」(戦士、賢者…) RPG と相性◎
current_chapter_summary: str         # LLM が定期に書き直す
```

**Chapter boundary detection** (ヒューリスティック): 直近 N 回の prediction_error 累積が閾値超 / imago 変化 / 重要 NPC 関係反転 → digest 再生成。

prompt 構築時にエピソード 30 件を流すより、`current_chapter_summary` + nuclear episodes 数件 + cue ヒット数件の方が一貫性が高く効率も良い。

### 3.3 Consolidation & Reconsolidation (Nadel, Moscovitch, Nader, Sara) ★最重要

- **Multiple Trace Theory** (Nadel & Moscovitch 1997): episodic 記憶は何年経っても海馬依存のまま、想起のたびに新しい trace が生成される。
- **Reconsolidation** (Nader 2000, Sara): 記憶を想起するとそれは一時的に **labile** 状態になり、再保存時に書き換えられる。**書き換えのトリガは prediction error**。PE が無いと labile 化しない = 書き換わらない。
- **Sleep-dependent consolidation**: SWS で hippocampal replay → cortical integration。REM で感情・関連付け処理。

**プロジェクトの spec とドンピシャ**。Reinterpretation はまさに reconsolidation。**ただし PE トリガを明示せよ**。「想起された」だけで書き換えるのではなく、「想起 + 現在の文脈との不一致」がある時だけ書き換える。

**実装ヒント**:
- `RecallEvent(episode_id, recalled_at, context_cues, surface_form, divergence_score)` を保存。
- **Labile window**: recall した episode は次の N tick だけ書き込み可能。それ以外は immutable。
- **Update gate**:
  ```
  if recall.divergence_score > θ_PE:
      enter_labile()
      reinterpretation(episode, current_context) -> new_episode_version
  else:
      strengthen_trace_only()  # 内容は変えず想起容易性だけ上げる
  ```
- **Sleep tick** (ゲーム内就寝イベント):
  1. その日の高サリエンス episode を replay
  2. associative graph に edge 追加
  3. semantic promotion 候補を昇格
  4. low-salience を transience 減衰
  5. dream-like 再結合で **counterfactual / future episode** を生成

**Anchor episode (書換禁止) を確保せよ**: 想起のたびに記憶を書き換えると drift が止まらない。self-defining memory に相当する少数は immutable に。Parfit 的 Relation R の骨。

### 3.4 Predictive Processing / Active Inference (Friston) ★spec の中核と同型

- **Free Energy Principle**: 内部モデルと感覚入力の差 (≒ 予測誤差) を最小化することで秩序を保つ。
- **Active Inference**: 行動は「予測誤差を減らすために環境を変えるアクション」。
- **EFE (Expected Free Energy)**: epistemic value (情報利得) と pragmatic value (目標到達) のトレードオフ = 好奇心と目的志向の両立。

**実装ヒント**:
- `BeliefState` を明示化: `world_beliefs: dict[Entity, ConfidenceDistribution]`, `self_beliefs`, `other_beliefs[npc_id]`。LLM の暗黙推論ではなく明示表現を持ち回す。一貫性が劇的に上がる。
- 各 turn: predict → observe → PE → episode 化 + belief 更新 (high PE) / 流す (low PE)。
- **Chunk boundary** = PE が閾値超の瞬間 (Nemori と整合)。
- **Curiosity drive**: expected information gain で重み付け。「冒険心ある人物」「保守的人物」は precision parameter の違いで表現。

### 3.5 Self-Model Theory (Metzinger)

- 「自己」は実体ではなく **Phenomenal Self-Model (PSM)**。**Transparent** であることが鍵。
- **Minimal Self** (前反省的、身体所有感) と **Narrative Self** (時間を跨ぐ物語的自己) を分離。

**実装提案**:
- `MinimalSelfModel`: body state, current location, owned items, immediate capabilities, current affect。**毎 tick 更新、絶対参照可能、system prompt に固定**。
- `NarrativeSelfModel`: LifeStoryDigest を指す。**低頻度更新**。
- これだけで「自分が誰かは確実に知っているが、過去は揺らぐ」という人間的な構成になる。

### 3.6 Theory of Mind / Mentalizing

- 脳内ネットワーク: TPJ, mPFC, precuneus。**rTPJ は他者ごとに spatially distinct representation**。
- DeepMind の Machine Theory of Mind: 他エージェント行動から mental state を予測する学習モデル。

**実装ヒント**:
- `OtherModel(npc_id)`: traits / relationship / last_known_state / shared_episode_ids / `predicted_response(action)`。
- **agent-specific スロット**で分離しないと、NPC A の記憶が B にリークして「人を見間違える」現象。
- LLM は素朴に「相手も自分と同じ情報を知っている」と仮定しがち (false belief 課題に失敗)。**explicit knowledge state of other** を prompt に明示。

### 3.7 Diachronic Identity (Locke, Parfit)

- Locke: memory criterion. Reid の批判で破綻。
- **Parfit**: psychological continuity を **Relation R** (overlapping chains of psychological connections) で再定義。直接 connection は非推移的だが**連鎖**は推移的。
- 「同一人格」は程度問題。重要なのは Relation R の保持。

**実装ヒント — Continuity Score**:
```
C(t1, t2) = w1·trait_overlap + w2·relationship_overlap + w3·skill_overlap
          + w4·narrative_thread_overlap + w5·recent_episode_chain
```
これを長期エージェントの監視メトリクスに。古い episode は forget してよいが、**semantic / narrative / skill / relationship に足跡を残してから捨てる**。これが overlapping chains。

### 3.8 Embodied Cognition (Varela, Thompson, Clark)

- 4E cognition: Embodied / Embedded / Extended / Enactive。
- Clark の **Extended Mind**: ノート、スマホ、メモは認知システムの一部。

**示唆**:
- プロジェクトの `world_graph` `player` `item` は extended mind 的「自己の延長」として活用できる。
- **環境への痕跡** (置いた物、書いたメモ、NPC との関係) は内部メモリを圧迫しない外部メモリ。**memo feature と整合**。
- 外部入力をゲーム観測と同プロトコルで扱う計画は extended mind そのもの。方向は正しい。

### 3.9 Forgetting as Feature (Bjork)

- **storage strength** (長期保持力) と **retrieval strength** (今アクセスしやすいか) を分離。忘却 = retrieval 低下のみ、storage は残る。再想起時に storage がさらに強化。
- **Desirable Difficulty**: 想起にコストがかかる方が storage を伸ばす (spacing, testing, interleaving)。
- **Retrieval-Induced Forgetting**: 関連項目を想起すると競合項目は抑制される。

**実装ヒント**:
- 各 episode に二変数: `storage_strength` (想起で増加、ほぼ減らない) + `retrieval_strength` (時間減衰、想起回復、競合想起で抑制)。
- 検索 score: `α · cue_match · retrieval_strength + β · narrative_link + γ · current_goal_relevance`。
- **vector store の単純 top-k は forgetting curve を実装していない = 永遠の若さ状態**。retrieval_strength を必ず掛けること。
- **Forget budget**: 1日 1000 観測あっても long-term に行くのは 10-50。残りは semantic / skill / relationship 統計に集約して捨てる。

### 3.10 設計判断への警告

- **沈黙の正当性**: 人間は常に観測 → episode 化しているわけではない。**低 PE な観測は episode 化しないで流す**。これを実装しないと unnatural。
- **無自覚な習慣**: procedural promotion 後の行動は episode を作らない。
- **嘘・自己欺瞞・confabulation**: Schacter の misattribution は人間性の証。**完全な事実整合性を目指さない方が人間らしい**。LLM の hallucination はバグではなく feature の場面がある (self-defining memory の再構成時など)。

---

## 第4部: 環境抽象化と観測/行動の共通プロトコル

### 4.1 比較表: 観測/行動の抽象化と portability

| システム | observation 抽象 | action 抽象 | identity portability | 共通プロトコル化の度合い |
|---|---|---|---|---|
| **MCP** (Anthropic) | resources + tool 戻り値 (content parts) | tools (JSON Schema) | 環境=サーバ、agent=ホスト。無状態 | **非常に高い** (環境がプラグイン) |
| **A2A** (Google) | Message = Parts[] (text/file/data) | Task (lifecycle 付き) | Agent Card で外形宣言 | 高い (agent ↔ agent) |
| **Letta** | message + tool result | tool call (memory edit 内蔵) | **`.af` で persona/archival/tool を export** | 中。memory portable |
| **Concordia** | Component の pre_observe/post_observe | Component の pre_act/post_act | Entity = Components の合成 | 中 |
| **OpenAI Computer Use** | screenshot + 直前 action 結果 | click/type/scroll の bounded GUI | session 単位 | 低 (PC 操作専用) |
| **OpenHands** | `Observation` 型階層 (CmdOutput, Browser, FileEdit...) | `Action` 型階層 | event stream 切り離し可、`step(state)→action` 純関数 | **高い** (型階層で対称化) |
| **Generative Agents** | memory_stream への自然文 | 自然文 → simulator 解釈 | retrieval 普遍 | 低 (1 環境専用) |
| **Voyager** | Minecraft state + last error | JS skill function | **skill library が portable** | 中 |
| **Gymnasium/PettingZoo** | observation_space (Box/Dict) | action_space | Env と完全分離 | 高い (RL de-facto) |
| **Soar / ACT-R** | sensory buffer → working memory | motor buffer → 環境 | **chunk/production が環境非依存** | **非常に高い** (古典的答え) |

**読み取り**: 両端は MCP (環境=プラグイン) と Letta `.af` (agent=シリアライズ可能、環境=ホスト)。Concordia と OpenHands が中間で event stream/component 境界を明示。観測/行動を**対称な type 階層**にしたのは OpenHands が最良の参考。cue 正規化+環境非依存 = Soar/ACT-R が事実上の答えだが、production rule の硬さを LLM 時代に持ち込みすぎない注意。

### 4.2 共通スキーマ案

**Observation envelope**:
```python
Observation := {
  observation_id : str
  occurred_at    : datetime                # wallclock
  env_time_label : str?                    # "Day3 18:00", "0:23:11 in video"
  source : {
    env_id      : str                      # "ai_rpg_world", "slack:T123", "youtube"
    surface     : str                      # "spot_graph", "channel:#dev", "video_player"
    actor_role  : "self" | "other" | "system" | "world" | "self_reflection"
    actor_ref   : EntityRef?
  }
  modality   : "text" | "vision" | "audio" | "structured" | "self_state"
  category   : "self_only" | "social" | "environment" | "self_reflection"
  content : { prose: str, structured: dict, media: MediaRef[] }
  cues       : Cue[]                       # §4.4 の正規化済み
  salience   : Salience                    # Park 流 recency × importance × relevance
  refs : { causes: id[], related_action_id: str?, grouping_key: str? }
  control : { schedules_turn, breaks_movement, ttl_hint }
}
```

現 `ObservationOutput` (`application/observation/contracts/dtos.py`) との対応: `prose / structured / observation_category / schedules_turn / breaks_movement` はそのまま流せる。新規追加が必要なのは `source`, `cues`, `salience`, `refs`, `modality`, `media`。

**Action intent**:
```python
ActionIntent := {
  action_id, issued_at, agent_ref,
  verb         : str                       # env-agnostic ("speak", "move", "watch", "reply")
  target_refs  : EntityRef[]
  bindings     : dict                      # JSON Schema 付き
  env_hint     : { env_id, tool_name, raw_args }?
  cognitive_state : { intent_text, expected_outcome, why, felt }
}
```

ポイント: **verb と bindings を環境非依存に保ち、`env_hint` が「どの MCP/tool に着地したか」だけを記録**。

### 4.3 EntityRef による環境 ID と認知概念のブリッジ

```python
@dataclass(frozen=True)
class EntityRef:
    cognitive_id : str                     # "person:ent:alice", "place:ent:tavern-greenoak"
    kind         : Literal["person","place","object","organization","artifact","abstract","self"]
    display_name : str
    aliases      : tuple[str, ...] = ()
    env_bindings : tuple["EnvBinding", ...] = ()

@dataclass(frozen=True)
class EnvBinding:
    env_id      : str
    local_id    : str                      # "spot_id:12"
    confidence  : float
    last_seen_at: datetime
```

環境ごとに `CognitiveResolver` (Protocol) を実装し、ローカル ID を `EntityRef` に解決する。

### 4.4 Cue 3 段階レベル化

現 `EpisodicCue(axis, value, source)` は良い土台。ただし `value` に `spot:12` を直接入れると portability を壊す。**3 段階 (情報を捨てずに昇格できる)**:

```python
class CueLevel(str, Enum):
    RAW       = "raw"        # 環境固有: place:spot:12
    LINKED    = "linked"     # EntityRef 解決済: place:ent:tavern-greenoak
    ABSTRACT  = "abstract"   # 型のみ: place:tavern, schema:negotiation_failed

@dataclass(frozen=True)
class Cue:
    axis       : CueAxis
    value      : str
    level      : CueLevel
    env_id     : str | None                # RAW のみ必須
    source     : EpisodicCueSource
    confidence : float = 1.0
```

**正規化規則**:
1. ObservationFormatter は raw cue を必ず付ける (情報失わない)
2. `CognitiveResolver` が pipeline 末尾で linked cue 付与 (失敗なら raw だけ残す)
3. Reflection / episode encoding 時に abstract cue 付与 (LLM 由来、`source=REFLECTION`)
4. Recall は **abstract → linked → raw** 順で試す。**別環境では abstract と linked が橋になる**

### 4.5 AgentSelf / EnvAttachment 分離

```
AgentSelf (portable, .af 相当, シリアライズ可):
  ├ identity         : AgentIdentity
  ├ persona          : AgentPersonaDto                 # 既存をそのまま
  ├ memory_blocks    : { core, human_models, world_models }   # Letta 流
  ├ episodic         : SubjectiveEpisode[]             # ただし location 抽象化
  ├ semantic         : SemanticMemoryEntry[]
  ├ skill_library    : Skill[]                         # Voyager 流
  └ entity_dossier   : { cognitive_id → EntityRef + 観察履歴 }

EnvAttachment (per env, 都度生成・破棄可):
  ├ env_id, surface_handles
  ├ env_bindings     : EnvBinding[]                    # cognitive_id ↔ local_id
  ├ observation_pipeline : 環境固有 formatter チェイン
  ├ action_adapter   : verb → tool_name 解決
  └ runtime_state    : 環境固有の一時状態
```

**境界**: `AgentSelf` に `spot_id` を入れない。`SubjectiveEpisode.location` を 2 分割:

```python
@dataclass(frozen=True)
class EpisodeLocationRef:
    cognitive_id : str | None              # "place:ent:tavern-greenoak"
    kind         : Literal["place","virtual_room","video_segment","email_thread","unknown"]

@dataclass(frozen=True)
class EpisodeLocationEnvHint:
    env_id        : str
    local_payload : dict                   # spot_id / channel_id / video_url:start
```

### 4.6 環境切替時の連続性

連続性の単位は「直近 N 観測」ではなく「現在の goal / felt / what_i_am_doing」 = Letta の core block 相当。

- **Closing observation** を自己投入: `"私は spot:12 から離れる。直前まで alice と会話していた。"`
- **Opening observation** を自己投入: `"私は slack に入る。最後の Slack 観察は 3 時間前、#dev で bob が質問していた。"`
- これらは `source.actor_role = "self_reflection"` / `category = "self_reflection"` (現 `ObservationCategory` を拡張)。
- Park 流 retrieval を agent identity 軸で実行し、env を跨いでも salience 上位 episode を常に context に積む。

### 4.7 具体的フロー: 「ゲームで育てた記憶を Slack/YouTube で活用」

例: ゲームで `place:ent:tavern-greenoak` の `person:ent:alice` と `schema:trust_violated` を経験。後日 Slack `#offtopic` で `@alice-cosplay` が話題に。

1. **ゲーム時**: chunk_boundary が trigger → `SubjectiveEpisode(who=("alice",), what="aliceに金を持ち逃げされた", felt="怒り・恥", cues=[entity:alice, place:tavern-greenoak, outcome:betrayed, schema:trust_violated])`。reflection で abstract cue `schema:trust_violated`, `entity_class:thief` を付与し semantic に格上げ。

2. **Slack 観察時**: `SlackEnvAdapter` が message を受信、`@alice` を `EntityLinker` に渡す → `slack:U123` を既知 `EntityRef(cognitive_id="person:ent:alice")` に紐付け試行 (confidence=0.4)。pipeline 抜けるときに recall: `entity:alice` と `schema:trust_violated` がヒット。LLM prompt に「過去に同名の人物にこういう経験 (信頼性 0.4)」が注入される。

3. **YouTube 視聴時**: 字幕チャンクを `Observation(modality="audio", media=[...])` で投入。字幕 "betray" → abstract cue `schema:trust_violated` が直接マッチ → recall。「視聴中の動画と過去の経験を結びつけて感想を述べる」が自然発火。

**設計の含意**: 環境依存 cue は記録しつつ、**recall は abstract cue 軸でやる**。Park 流 retrieval の relevance を cue overlap で計算する時に abstract cue を含めれば、cross-env で勝手に橋がかかる。

### 4.8 推奨レイヤー構成

```
┌─────────────────────────────────────────────────────────────────┐
│  AgentSelf (portable; serializable .af-like)                    │
└─────────────────────────────────────────────────────────────────┘
            ▲                                  ▲
            │ ObservationEnvelope              │ ActionIntent
            ▼                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  Cognition Layer (env-agnostic)                                 │
│  CueNormalizer / EntityLinker / SalienceScorer / ReAct loop     │
└─────────────────────────────────────────────────────────────────┘
            ▲                                  ▲
            ▼                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│  Env Adapters                                                   │
│  ai_rpg_world / slack / youtube / email / mcp_bridge            │
└─────────────────────────────────────────────────────────────────┘
```

**`mcp_bridge` adapter を 1 本書けば、Slack/Gmail/Drive/Notion 等の既存 MCP server を一気に吸収できる**。これが最も実装コスト対効果が良い。

---

## 第5部: プロジェクトへの統合提言 (優先度付き)

このプロジェクトの spec を読んだ上で、4 観点から「効きそう × 実装コスト合理」で優先順位を付ける。

### 即座に効く (Quick wins)

**P1. PE-gated reconsolidation を明示する** ★★★
- Reinterpretation は「想起された」ではなく「想起 + 期待との不一致」で発火させる。これが無いと記憶が wandering して安定しない。
- 出典: Nader (2000), Sara (reconsolidation)、Nemori (Predict-Calibrate)
- 実装: `RecallEvent.divergence_score` を保存し、閾値超のみ labile window を開く

**P2. Anchor Episode (書換禁止フラグ) を確保する** ★★★
- self-defining memory に相当する少数の episode を immutable に。Parfit 的 Relation R の骨。
- 実装: `SubjectiveEpisode.is_anchor: bool`、anchor 化のトリガは importance + 想起頻度

**P3. importance を LLM (1-10) で採点する** ★★
- Park 流。Reflection / Reinterpretation の発火閾値が単純化する。
- 実装: trace → episode 化時に importance prompt を 1 回実行 (cheap)

**P4. storage_strength と retrieval_strength を分離する** ★★
- Bjork。単一スコアにすると vector store の「永遠の若さ問題」が起きる。
- 実装: episode に二変数、retrieval score に `retrieval_strength` を必ず掛ける

**P5. 沈黙の正当性 — 低 PE 観測は episode 化しない** ★★
- 「なんでもないことを覚えている」unnatural さを排除。
- 実装: chunk_boundary の発火条件に PE 閾値を組み込む

### 中期で効く (Architectural)

**P6. Cognitive Controller (PIANO 流) narrow bottleneck を入れる** ★★★
- 多階層 memory が独立に context を出し、最後に single intent stream に統合してから行動生成。人格分裂を構造的に防ぐ。
- 実装: 既存の prompt builder の前段に「複数 component の出力 → CC で 1 stream に集約」レイヤーを挟む

**P7. Bi-temporal Semantic Promotion (Graphiti 流)** ★★★
- `(valid_at, invalid_at, created_at, expired_at)` の 4-tuple。「過去のあの時点では NPC A は B を友人だと思っていた」を Cue として復元可能 = 連続性の核。
- 削除せず invalidate するルールは Reinterpretation と相性◎ (古い解釈は invalid だが Trace としては残る)。
- 実装: `SemanticMemoryEntry` に 4 timestamp を追加、矛盾検出は `dedupe_edges` prompt を参考

**P8. A-MEM 流 evolution を Reinterpretation の参照実装に** ★★
- evolution_system_prompt をそのまま流用できる。ただし「上書きではなく派生 Episode を発行」する派生に留めて Trace 不変を守る。
- 実装: `application/llm/ports/episodic_reinterpretation_completion_port.py` の中で A-MEM の prompt を参考に refactor

**P9. AgentSelf / EnvAttachment 境界を引く (環境抽象化の根)** ★★★
- `SubjectiveEpisode.location` を `EpisodeLocationRef + EpisodeLocationEnvHint` に分割。`AgentSelf` に `spot_id` を入れない。
- これが**外部入力をゲーム観測と同じプロトコルで扱う目標の前提**。
- 実装: 第4部 §4.5 参照。マイグレーションは機械的に可能

**P10. Cue を 3 段階レベル化 (RAW / LINKED / ABSTRACT)** ★★★
- 環境依存 cue は記録しつつ、recall は abstract 軸で。これで cross-env の橋がかかる。
- 実装: 第4部 §4.4 参照。既存 `EpisodicCue` に `level` フィールドを追加するだけで段階導入可

### Identity 層の追加

**P11. MinimalSelfModel + NarrativeSelfModel を分離** ★★
- Metzinger。前者は毎 tick 更新+system prompt 固定、後者は低頻度更新。
- 「自分が誰かは確実に知っているが、過去は揺らぐ」という人間的構成を最小コストで実現。

**P12. LifeStoryDigest 集約 (McAdams)** ★★
- `nuclear_episodes` / `themes` / `imago` / `current_chapter_summary`。chapter boundary で再生成。
- 30 件 episode 流すより `chapter_summary` + nuclear 数件の方が一貫性も効率も上。

**P13. Letta 流 persona/core_values/current_concerns の 3 Block** ★
- LLM 自身が tool で書き換えられる core memory。**人格 drift を構造的に抑える**。
- Character.AI の「persona 固定 + 記憶弱め」が商用で機能している事実を踏まえ、頑健な核を持つことの重要度は高い。

**P14. Other-model を agent-specific スロットで分離** ★★
- rTPJ 知見。NPC ごとに分離した belief slot、PE トリガで更新。
- LLM に **explicit knowledge state of other** を明示すると false belief 課題改善。

### 行動と未来の取り扱い

**P15. EpisodeKind を OBSERVED/RECALLED/SIMULATED_FUTURE/SIMULATED_COUNTERFACTUAL に拡張** ★★
- Schacter: 過去想起と未来シミュレーションは同じ回路。
- 「明日また会う約束」と「昨日会った思い出」が同じ associative graph で繋がる = prospective memory の自然実装。

**P16. Procedural Skill Library を独立 tier に (Voyager + Reflexion)** ★
- 成功体験 (Voyager 的 skill) と失敗教訓 (Reflexion 的 reflection) を別 tier で保持。
- 「Bob は釣りができる」を文章ではなく行動ポリシー断片として。

**P17. BeliefState を明示化 (Active Inference)** ★★
- `world_beliefs / self_beliefs / other_beliefs` を LLM の暗黙推論ではなく明示表現として持ち回す。
- 性格の一貫性が劇的に上がる。

### 運用と長期

**P18. Sleep tick (consolidation pass)** ★
- ゲーム内就寝イベントで replay → consolidation → forgetting → dream-like simulation。
- 1日分の episode をその場で処理せず batch で扱う。Park の reflection 発火 (importance 合計 150) と統合可。

**P19. Continuity Score を監視メトリクスとして実装** ★
- Parfit を運用に落とす。長期セッションでの identity drift を自動検知。
- 閾値超で人手レビュー or 自動 anchor 追加。

**P20. (長期野望) Parametric Consolidation** ★★★ — ただし実装コスト高
- 長く生きた NPC ごとに小型 LoRA で episode を焼き込む。「文字通り神経が形作られる」連続性。
- 業務 AI では過剰だが「人間と区別つかない存在」目標の本命。
- 出典: Episodic Memory is the Missing Piece (arXiv 2502.06975)

### 環境拡張のロードマップ

**Phase 0** (非破壊): `cognition/` パッケージを新設、`ObservationEnvelope`/`ActionIntent`/`EntityRef`/`Cue (level付き)` を導入。既存 `ObservationOutput` は `from_legacy()` でブリッジ。`EpisodeLocation` を 2 分割。

**Phase 1**: `CognitiveResolver` Protocol + `SpotGraphEntityLinker` 実装。Cue を 3 段階化。

**Phase 2**: `application/observation/services/observation_pipeline.py` を `EnvObservationAdapter` 化。`LlmAgentTurnRunner` を env_id 引数受け取り化。

**Phase 3**: `AgentSelfSerializer` (`.af` 互換 JSON) を実装。

**Phase 4**: `mcp_bridge` env adapter で外部世界 (Slack/Gmail/Drive/Notion) を一気に接続。

**Phase 5**: Skill Library を verb + bindings に分離 (Voyager 流)。

---

## 参照

### プロダクション実装
- [mem0](https://github.com/mem0ai/mem0)
- [Letta](https://github.com/letta-ai/letta) / [Memory docs](https://docs.letta.com/concepts/memory) / [Agent File](https://github.com/letta-ai/agent-file)
- [Graphiti](https://github.com/getzep/graphiti)
- [A-MEM](https://github.com/WujiangXu/AgenticMemory) / [paper](https://arxiv.org/abs/2502.12110)
- [LangMem](https://langchain-ai.github.io/langmem/concepts/conceptual_guide/)
- [cognee](https://github.com/topoteretes/cognee)

### 学術
- [Generative Agents](https://arxiv.org/abs/2304.03442) / [code](https://github.com/joonspk-research/generative_agents)
- [Voyager](https://arxiv.org/abs/2305.16291) / [code](https://github.com/MineDojo/Voyager)
- [Concordia](https://arxiv.org/abs/2312.03664) / [code](https://github.com/google-deepmind/concordia)
- [Project Sid / PIANO](https://arxiv.org/abs/2411.00114) / [code](https://github.com/altera-al/project-sid)
- [Reflexion](https://arxiv.org/abs/2303.11366)
- [MemGPT](https://arxiv.org/abs/2310.08560)
- [Episodic Memory is the Missing Piece](https://arxiv.org/abs/2502.06975)
- [Nemori](https://arxiv.org/abs/2508.03341)
- [AI Town](https://github.com/a16z-infra/ai-town)
- [Character.AI Cognitively-Inspired Episodic Memory](https://arxiv.org/pdf/2511.10652)

### 認知科学
- [Tulving - Elements of Episodic Memory (40 year review)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11449159/)
- [Schacter - Constructive episodic simulation](https://pmc.ncbi.nlm.nih.gov/articles/PMC6402953/)
- [Schacter - Seven sins update](https://bpb-us-e1.wpmucdn.com/sites.harvard.edu/dist/3/137/files/2022/10/The-seven-sins-of-memory-an-update.pdf)
- [McAdams - Narrative Identity](https://journals.sagepub.com/doi/10.1177/0276236618756704)
- [Memory consolidation review](https://pmc.ncbi.nlm.nih.gov/articles/PMC4526749/)
- [Reconsolidation update (Sara)](https://pmc.ncbi.nlm.nih.gov/articles/PMC5605913/)
- [PE demarcates reconsolidation transition](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4201815/)
- [Active Inference: Process Theory](https://activeinference.github.io/papers/process_theory.pdf)
- [Metzinger - Being No One](https://www.researchgate.net/publication/267209451_Being_No_One_The_Self-Model_Theory_of_Subjectivity)
- [Limanowski & Friston - Minimal self-models & FEP](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3770917/)
- [Theory of Mind: A Neural Prediction Problem](https://pmc.ncbi.nlm.nih.gov/articles/PMC4041537/)
- [Machine Theory of Mind (Rabinowitz)](https://arxiv.org/pdf/1802.07740)
- [Personal Identity and Ethics (SEP)](https://plato.stanford.edu/entries/identity-ethics/)
- [Parfit on personal identity (Speaks)](https://jspeaks.site/courses/20208/parfit-personal-identity.pdf)
- [Embodied Cognition (SEP)](https://plato.stanford.edu/entries/embodied-cognition/)
- [Bjork Lab](https://bjorklab.psych.ucla.edu/research/)

### プロトコル
- [Model Context Protocol](https://modelcontextprotocol.io/specification/2025-06-18/client/elicitation)
- [A2A Protocol](https://a2a-protocol.org/latest/) / [repo](https://github.com/a2aproject/A2A)
- [OpenHands paper](https://arxiv.org/html/2407.16741v3)
- [ReAct](https://arxiv.org/pdf/2210.03629)
- [Gymnasium](https://gymnasium.farama.org/api/env/)
- [MineDojo](https://docs.minedojo.org/sections/core_api/obs_space.html)
- [Soar Introduction](https://arxiv.org/pdf/2205.03854)
- [Examining Identity Drift in LLM Agents](https://arxiv.org/pdf/2412.00804)

### プロジェクト内主要ファイル
- `docs/memory_system/episodic_memory_system_spec.md` — 現状仕様
- `src/ai_rpg_world/application/observation/contracts/dtos.py`
- `src/ai_rpg_world/application/llm/contracts/episodic_memory.py`
- `src/ai_rpg_world/application/llm/contracts/chunk_encoding.py`
- `src/ai_rpg_world/application/llm/contracts/persona.py`
