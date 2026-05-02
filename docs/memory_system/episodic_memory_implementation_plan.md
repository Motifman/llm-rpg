# Episodic Memory — 実装計画

本文書は [episodic_memory_system_spec.md](./episodic_memory_system_spec.md) の仕様を、**既存コードに載せるための移行・実装順序**に落としたものである。詳細な Tool 引数設計や Chunker の議論のフルテキストは、必要に応じて [episodic_memory_reimplementation_plan.md](./episodic_memory_reimplementation_plan.md) を参照する。

**作業手続き（Git・レビュー・ブロッキング・worktree）**は [memory_feature_workflow.md](./memory_feature_workflow.md) に分離した。記憶関連の実装・マージでは**毎回そちらを開いてから**着手する。**フェーズ完了時は同ファイル §5 に従い、本計画（査読表・各 P セクション等）を更新したうえでコミットする**。

## 1. 目的と非目標

- **目標**: 型付き cue・想起軸・（将来）リンク store により、Passive/Active 想起が **ゲーム由来 id** で安定し、Memory Context Pack へ拡張しやすい土台にする。
- **非目標（初期）**: グラフ DB、embedding 類似検索、全ペアリンク更新。

## 2. 現状コードの要点（2026 時点）

| 領域 | 主なモジュール |
|------|----------------|
| v2 主観エピソード | `SubjectiveEpisode`, `InMemorySubjectiveEpisodeStore`, **`SqliteSubjectiveEpisodeStore`**（`episode_cues` / `memory_links`）, `llm_json_episode_encoder.py` |
| Trace | `ActionExperienceTrace`, `ObservationExperienceTrace`, `agent_orchestrator._append_action_experience_trace` |
| Passive Recall | `passive_subjective_recall_composer.py`＋`passive_subjective_recall_retrieval.py`（状況文・**runtime canonical**・エピソード索引の和集合、`pick_debug` 任意） |
| エンコーディング文脈 | `episode_encoding_context_provider.py`（`current_goals` ← Working Memory） |
| UI / 現在地 | `ui_context_builder.py`（タイル）, `spot_graph_ui_context_builder.py`（**`current_spot_id` ← snapshot**） |
| レガシー episodic | `RuleBasedMemoryExtractor`, `EpisodeMemoryEntry`, `DefaultPredictiveMemoryRetriever` |

## 3. フェーズ概要

```text
P0 命名・DTO（空間・target フィールド）の是正
P1 trace / runtime context に構造化位置・spot id を確実に載せる
P2 ルールベース cue 抽出 + `SubjectiveEpisode.cues` / `cue_keys` の統合（索引は `subjective_episode_index_strings`）
P3 Passive Recall の軸別候補（和集合 + 二次スコア）
P4 memory_links + episode_cues の永続化（**すぐ SQLite を本線にするなら in-memory 迂回せず SQLite 実装から始める**）
P5 Memory Context Pack 型の導入（Reflection/Recall の入力統一）
```

並行してよいもの: レガシー `EpisodeMemoryEntry` / `PredictiveMemoryRetriever` は**段階的に縮小**し、Passive/Active 想起とエンコードの**真のソースは v2 `SubjectiveEpisode`** とする（レガシー schema の SQLite は別系統のまま）。

### 3.1 作業手続き・Git・レビュー・ブランチ（参照）

ブランチ運用・コミット規約・**GitHub CLI（`gh`）による PR 必須**・**サブエージェントレビュー（Composer 2・利用者の実行許可を待たず起動／見過ごせない変更がある場合は Approve 禁止）**・**ブロッキングとブランチの見方**・worktree・並列戦略は **[memory_feature_workflow.md](./memory_feature_workflow.md)** に集約した。

---

### 3.2 空間系 cue の推奨案（LLM や旧仕様に引っ張られない）

**方針**: 空間の索引は **ゲーム由来 id のみ**、**ルールが `EpisodicCue` に書く**。LLM の自由記述や `place_label:` 類は **索引にしない**（観測テキスト・プロンプト用にとどめる）。

**推奨する axis（canonical 文字列・全体で固定）**

| axis | 意味 | value の中身 | 主な入力元（ルール側） |
|------|------|----------------|------------------------|
| `place_spot` | スポットノード | 十進文字列の `spot_id` | `ToolRuntimeContextDto.current_spot_id`、trace コピー後は trace |
| `tile_area` | タイル世界の区画 | 十進文字列の `LocationAreaId` | `current_area_ids` / `tile_location_area_id` 系 |
| `sub_loc` | スポットグラフ内区画 | 十進文字列の `SubLocationId` | `sub_location_id`、`current_sub_location_id`（導入時） |

- **同時成立**: 同一エピソードに `tile_area` と `sub_loc` が両方載ってよい（二系統ワールドの切り替え・ハイブリッドに対応）。想起は **いずれかと交差**すれば候補に入る、など P3 で調整する。
- **座標 `coord:`** は、タイルで「区画より細かい一致」が要る場合のみ**後追し**で足す。初期は `tile_area` + `place_spot` で足りることが多い。
- **`to_canonical()`** は既存どおり `axis:value`。prefix の見た目より **axis 列と値の意味**をソース・オブ・トゥルースにする。

**やらない方がいいこと**

- LLM に「場所の cue を JSON で返させる」こと（表記ゆれと id 欠落の両方が出る）。
- 索引に **自然言語ラベル**（地下倉庫、北の広場）だけを載せること。ラベルは `observed` や UI 向けに残し、マッチは id 軸で行う。

---

### 3.3 `cue_keys` と LLM：段階的にやめる

旧仕様の「`schema_hint` 補助だけ LLM」より一段はっきりさせる。**本線の索引は `cues`（ルール＋将来の検証済み hybrid）**とする。

**フェーズ案（コードと一緒にトラッキング表を更新）**

1. **今**: Passive/Recall は `subjective_episode_index_strings` で **`cue_keys` ∪ `cues`**。既存データ用に `cue_keys` はフィールドとして残す。
2. **直後**: `LlmJsonEpisodeEncoder` / reflection JSON から **`cue_keys` の生成要求を外す**（プロンプト・schema から削除または deprecated コメント）。空配列で保存してよい。
3. **移行後**: ルール抽出が揃ったら、**新規保存は `cues` のみ**を正とし、`cue_keys` は読み取り互換のためだけに残す期間を設ける。
4. **最終**: 永続層・API で `cue_keys` を削除するか、内部のシリアライズ専用に閉じる（表に「廃止済み」と書く）。

LLM に残してよいのは **主観フィールド**（`interpreted` 等）に限定し、「検索キー生成」は担当させない。

---

### 3.4 廃止・置換の一覧（生きた表）

「いつ消すか分からなくなる」のを防ぐため、**削ったらこの表を更新する**。状態: `active` / `deprecated` / `removed`。

| 対象 | 状態 | 置換・注意 |
|------|------|------------|
| `ToolRuntimeTargetDto.location_area_id`（旧） | removed（コード上） | `tile_location_area_id` / `sub_location_id` |
| LLM 生成の `SubjectiveEpisode.cue_keys` | deprecated（目標） | `cues`（ルール）。索引は `subjective_episode_index_strings` から `cues` 主軸へ |
| フィールド `cue_keys`（DTO） | active（互換） | 上記フェーズ完了まで残す → 最終 removed または内部のみ |
| レガシー `EpisodeMemoryEntry` / `PredictiveMemoryRetriever` | deprecated（方針） | v2 `SubjectiveEpisode` + Passive Recall。削減順は別タスクで行を追加 |
| in-memory only の v2 store（本番寄り運用時） | deprecated（方針） | **`SqliteSubjectiveEpisodeStore` が main に存在**。既定配線は当面 `InMemorySubjectiveEpisodeStore`（`wiring`）。本番で SQLite に切り替えるときは同 I/F で注入 |

---

## P0 — 空間まわりの命名・DTO リファクタ

**問題**: `ToolRuntimeTargetDto.location_area_id` がスポットグラフでは `sub_location_id` を指していた。`LocationAreaId`（タイル）と混同する。

**実施済み（2026）**

- `ToolRuntimeTargetDto`: **`tile_location_area_id`**（タイル）と **`sub_location_id`**（グラフ区画）に分離。スポットグラフ／タイル経路は各フィールドへ設定。
- `SubjectiveEpisode`: **`cues: Tuple[EpisodicCue, ...]`** を追加。`EpisodicCue(axis, value, source)` は `to_canonical()` で `axis:value` に変換。想起・重複判定は **`subjective_episode_index_strings(ep)`** で `cue_keys` とマージ。
- **移行方針**: レガシー文字列索引は当面 `cue_keys` のまま残し、ルール生成は `cues` に載せて統合関数で一本化する。
- `ToolRuntimeContextDto.current_sub_location_id`（任意）は **P1 で追加済み**（スポットグラフ UI が `is_current` のサブロケーションから設定）。

**受け入れ条件**

- スポットグラフ／タイルのどちらでも「今いる区画 id」が型と名前で区別できる。✅
- `spot_graph_resolver` / movement / UI context builder / 関連テストが通過。✅

---

## 2.1 査読サマリ（仕様・計画 vs コード）

中立査読で洗い出した主なギャップ（**ドキュメントに「既にある」と読めないよう注意**）:

| 項目 | 状態 |
|------|------|
| P0: DTO 空間フィールド分離 + `EpisodicCue` | **対応済み**（2026） |
| `SpotGraphPlayerSnapshotDto.current_spot_id` + runtime への伝播 | **対応済み**（2026、P1 の一部） |
| trace への構造化位置コピー | **一部対応**（2026、`ActionExperienceTrace.context_*`・`ObservationExperienceTrace.context_*`、orchestrator / `spot_id_value`） |
| ルールベース cue + validator 主導 | **一部対応**（2026、`episodic_cue_extraction`・エンコード時 `cues`・LLM `cue_keys` 廃止） |
| 軸別 Passive Recall | **一部対応**（2026、上記 + **`ToolRuntimeContextDto` 由来の状況側 canonical** とエピソード索引の突合・`compose_user_block(runtime_context=)`） |
| `episode_cues` / `memory_links` | **対応済み**（2026、`SqliteSubjectiveEpisodeStore`, `subjective_episode_sqlite_codec.py`, `tests/.../test_sqlite_subjective_episode_store.py`） |
| Memory Context Pack（§2.7 契約） | **一部**（2026、`MemoryContextPack` + recall 用最小 assembly + テスト） |
| v2 と `PredictiveMemoryRetriever` の統合方針 | **ユーザ判断**（段階廃止 / 併存期間） |

---

## P1 — 構造化位置と `current_spot_id`

**問題（残件）**: 記憶 cue や trace 永続化のため、`ToolRuntimeContextDto` 由来の id を **ExperienceTrace にコピー**する。文字列 `*_snapshot` だけでは索引・デバッグで id が失われる。

**進捗**

1. ✅ `SpotGraphPlayerSnapshotDto` に **`current_spot_id: int`** を追加。`SpotGraphCurrentStateBuilder` が設定。`SpotGraphUiContextBuilder` が `ToolRuntimeContextDto.current_spot_id` に渡す。
2. ✅ `ToolRuntimeContextDto.current_sub_location_id`（任意）。スナップショットの `sub_locations` で **is_current** の id を UI ビルダが設定。
3. ✅ `ActionExperienceTrace` / `ObservationExperienceTrace` に **`context_spot_id` / `context_tile_area_ids` / `context_sub_location_id` / `context_x|y|z`** を追加。観測側は **structured の `spot_id_value`** から最低限 `context_spot_id` を埋める。
4. ✅ **観測 vs 行動の非対称（P1）**: `ObservationTraceRecorder.record(..., runtime_context=)` と `IObservationContextBuffer.append(..., runtime_context=)` を追加。`create_llm_agent_wiring` / `create_spot_graph_wiring` は `ObservationAppender(runtime_context_provider=...)` で **UI ビルダと同系の** `ToolRuntimeContextDto` を観測時に供給。`context_spot_id` は structured 優先、無ければ runtime。`context_sub_location_id` / 座標は runtime 由来。**`context_tile_area_ids` は観測 trace にまだ載せない**（`current_area_ids` はコピーしない）。

**タスク（残り）**

- SQLite / 長期 store のシリアライズで新フィールドを欠かさない（該当ストア実装を確認）。
- 観測 trace の **`context_tile_area_ids`**: 意図的に未設定（タイル `current_area_ids` を観測に載せる要件が決まり次第）。

**受け入れ条件**

- スポットグラフ run で `ToolRuntimeContextDto.current_spot_id` が非 null（該当セッションで spot が決まる場合）。✅
- 単体テストで trace に期待する spot / sub_loc / area が残る。✅（オーケストレータ・UI・観測 recorder の代表ケース）

---

## P2 — ルールベース cue 抽出

**タスク**

1. ✅ モジュール `application/llm/services/episodic_cue_extraction.py`：入力 `ActionExperienceTrace` | `ObservationExperienceTrace` | 任意の `ToolRuntimeContextDto` 断片（`episodic_cues_from_traces(..., runtime=)`）。出力 **`EpisodicCue` の列**（長さ・件数上限）。空間軸 `place_spot` / `tile_area` / `sub_loc`、`action`（ツール名）、観測の `observation_kind`、structured の id、`object_type` / `object_category`（runtime target）など。
2. ✅ ドメイン由来 id の範囲で object 系・空間系をルール化（P1 の trace `context_*` と整合）。
3. ✅ `LlmJsonEpisodeEncoder`：索引用 **`cue_keys` を LLM に要求しない**（JSON schema では任意）。**保存時 `cue_keys` は空・`cues` は encode 直後にルールで上書き**。
4. ✅ `_traces_digest` は現状どおり要約のみ（`context_*` 非掲載）。空間 id は trace 本体の `context_*` から抽出器が読む。

**残り（参考）**

- `IEpisodeEncoder.encode` に `ToolRuntimeContextDto` を渡す拡張で、trace に無い `current_*` を常時マージしやすくする。
- **Passive Recall** は現状 `situation_text` への部分一致が中心のため、エピソード側が **`cues` の canonical（`axis:value`）** 中心になると、日本語のみの旧 `cue_keys` より状況文との一致が取りにくい場合がある。**P3** の SituationCueSet（同一抽出器）で揃える想定。

**受け入れ条件**

- 同一 trace から決定論的に同じ cue 列が得られる（テストで固定）。✅
- Validator（長さ上限・個数上限）を通す。✅

**Stub / テスト**

- ✅ `StubEpisodeEncoder` も同じ `episodic_cues_from_traces` で `cues` を付与（`cue_keys` は空）。

---

## P3 — Passive Recall: 軸別候補

**タスク**

1. `PassiveSubjectiveRecallComposer` を分割:
   - ✅ **軸別スコア**は `passive_subjective_recall_retrieval.py` に切り出し（temporal / cue / importance / goal）。`list_recent` 順は temporal 補正に反映。
   - ⏳ **SituationCueSet**（状況テキストのみからのルール抽出）は未。
   - ✅ **Situation 側 canonical（runtime）**: `passive_recall_situation_cues` と `IPassiveSubjectiveRecallComposer.compose_user_block(..., runtime_context=)`。`DefaultPromptBuilder` が `LlmUiContextDto.tool_runtime_context` を渡す。エピソード索引との交差は従来の状況文マッチと**和集合**。
   - ✅ **Goal 軸**: 現行の目標トークンと本文一致を維持（将来 `goal:` 接頭辞へ）。
2. ⏳ 複数 retriever が episode_id 集合を返すパイプは未。現状は **線形スキャン + 合成スコア**で並べ替え。
3. ✅ canonical `axis:value` の **値部分**が状況に含まれれば cue ヒット（日本語 `cue_keys` だけに依存しない）。

**受け入れ条件**

- 既存テストを更新・追加し、回 regress しない。✅
- デバッグ用に軸別寄与を見える化: `PassiveRecallPickDebug` + `include_pick_debug=True`。✅

---

## P4 — `episode_cues` / `memory_links`

**タスク**

1. ✅ 仕様 §2.5 のテーブル相当を **SQLite で実装**（`agent_id` = `PlayerId.value` スコープ）。マイグレーション namespace: `subjective-episode-v2`。レガシー `episode_memories` とは別系統。
2. ✅ `put` 時に `episode_cues` を `subjective_episode_index_strings` で整合更新。候補取得は **cue → episode_id の逆引き**に限定（全件スキャン禁止の意図に沿う）。
3. ✅ リンク種: `temporal`, `spatial`（cue 重なり）, `co_recalled`。保存時に局所スコアで上位のみ `memory_links` へ。

**実施済み（2026）**

- 実装: `src/ai_rpg_world/infrastructure/llm/sqlite_subjective_episode_store.py`, `subjective_episode_sqlite_codec.py`
- テスト: `tests/application/llm/test_sqlite_subjective_episode_store.py`（マルチ `agent_id` 分離・索引・リンク・掃除を含む）

**残り・任意**

- ✅ **オプトイン配線（2026）**: `create_llm_agent_wiring` / `create_spot_graph_wiring` は既定のまま `InMemorySubjectiveEpisodeStore`。環境変数 `SUBJECTIVE_EPISODE_DB_PATH` または引数 `subjective_episode_sqlite_path` / `subjective_episode_store` で `SqliteSubjectiveEpisodeStore` に切り替え可能（`.env.example`・`wiring/__init__.py` モジュールドキュメント参照）。**既定を SQLite に変える変更はしない**（本番での明示設定が前提）。

**受け入れ条件**

- SQLite 上で put → cue 逆引き → 期待リンク、および `ISubjectiveEpisodeStore` 契約を満たす。✅（テスト・コード）

---

## P5 — Memory Context Pack

**タスク**

1. ✅ `MemoryContextPack` dataclass（保存しない）を `application/llm/contracts/memory_context_pack.py` に追加。§2.7 相当フィールド＋`__post_init__` 検証。v1 は近傍・共想起を **episode_id 列**で表現。
2. ⏳ Passive Recall / Memory Reflection の **プロンプト経路への Pack 注入**は未。当面は `memory_context_pack_assembly.assemble_memory_context_pack_for_recall_turn` で既存断片から組み立て可能。
3. ⏳ temporal / associative のリンク解決・semantic / identity の実データは段階的に拡張。

**参照実装（2026）**

- 型: `memory_context_pack.py`
- 組み立て: `application/llm/services/memory_context_pack_assembly.py`
- テスト: `tests/application/llm/test_memory_context_pack.py`

---

## 7. 能動想起（低優先）

- 既存 `memory_query` / 主観検索 tool の拡張で、「この episode に関連」を明示的に取りに行く経路は **P3 以降**でよい。

---

## 8. リスク・依存

- **二世界（タイル / スポットグラフ）**: cue の prefix を混ぜないこと（P0/P1）。
- **Working Memory の質**: goal 軸は WM が貧しいと弱い → 将来、TODO/quest からの `goal:` 供給を検討。

---

## 9. 完了の定義（マイルストーン M1）

- **P1（runtime）**: スポットグラフで `ToolRuntimeContextDto.current_spot_id` がスナップショットと一致する。✅（2026）
- **P1（trace）**: spot / sub_loc / area が `ActionExperienceTrace` 等に**永続**される。
- P0 + P1 trace が完了し、spot graph で spot id が **trace に残る**状態を M1 の完了とする。
- P2 で代表シナリオ（罠箱・移動）に対し決定論的 cue が得られる。
- P3 で軸別候補マージが入り、従来より説明可能な想起になる。
- **P4** で v2 主観エピソードの SQLite（`episode_cues` / `memory_links`）が **main に存在**し、マルチ `agent_id` で分離検証済み。✅（2026）

---

## 11. 設計のフォーク（整理済み／残論点）

**整理済み（2026）**

1. **`ToolRuntimeTargetDto` の空間 id**: `tile_location_area_id` と `sub_location_id` に分離済み。
2. **型付き cue**: `EpisodicCue` + `SubjectiveEpisode.cues`。索引マージは `subjective_episode_index_strings`。単一 `cue_keys` への統合は行わない。
3. **空間系 prefix 語彙**（例: `tile_area:` / `sub_loc:`）: **主に空間軸**の名前空間。全 cue の唯一の総称規約ではない（仕様 §2.3）。
4. **v2 優先**: 新機能・想起の主対象は **`SubjectiveEpisode`**。レガシー episodic は段階縮小。
5. **P4 永続化**: **`SqliteSubjectiveEpisodeStore` を main に導入済み**（レガシー `episode_memories` とは別 schema）。既定配線は `InMemorySubjectiveEpisodeStore`；**オプトイン**で `SUBJECTIVE_EPISODE_DB_PATH` 等により SQLite へ切替可能。
6. **Git 運用**: **小分けコミット・機能単位ブランチ・メッセージに「なぜ」**（巨大ブランチは一度まとめてマージ push 後に転換）。手続きの詳細は **[memory_feature_workflow.md](./memory_feature_workflow.md)**。

**残論点**

- `PredictiveMemoryRetriever` の**具体的な廃止順序・併存期間**（利用箇所の置換見積もり）。

---

## 10. 参照

- 作業手続き・完了後の計画更新（Git・レビュー・ブロッキング・§5）: [memory_feature_workflow.md](./memory_feature_workflow.md)
- 仕様: [episodic_memory_system_spec.md](./episodic_memory_system_spec.md)
- 詳細議事録・Tool schema 長文: [episodic_memory_reimplementation_plan.md](./episodic_memory_reimplementation_plan.md)
