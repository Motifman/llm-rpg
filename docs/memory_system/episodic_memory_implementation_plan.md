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
| Passive Recall | `passive_subjective_recall_composer.py`＋`passive_subjective_recall_retrieval.py`。**スコア軸**（temporal / cue / goal / importance）は実装済みだが、**候補エピソード集合は `list_recent(max_scan)` のみ**（仕様 §8 の「軸ごとに候補を取り和集合」**未達**）。`pick_debug` で軸寄与を可視化可能。 |
| エンコーディング文脈 | `episode_encoding_context_provider.py`（`current_goals` ← Working Memory） |
| UI / 現在地 | `ui_context_builder.py`（タイル）, `spot_graph_ui_context_builder.py`（**`current_spot_id` ← snapshot**） |
| レガシー episodic | `RuleBasedMemoryExtractor`, `EpisodeMemoryEntry`, `DefaultPredictiveMemoryRetriever` |

## 2.1 仕様 §8（想起軸・和集合）と現実装の乖離（重要）

[episodic_memory_system_spec.md §8](./episodic_memory_system_spec.md#8-想起軸recall-axisと索引キー) の方針は次である。

- **想起軸**（個体一致・型、空間、**時間的近傍**、骨格 event、目的…）は **同等に並列**で扱う想定。
- 各軸で **一定件数の候補エピソード ID を取得**し、**和集合にマージ**したうえで、必要なら **二次スコア**で並べ替える。

**現状コード（v2 初期実装に引きずられた部分）**はこれと一致していない。

| 仕様の意図 | 現状 |
|------------|------|
| 軸ごとに別ソースから候補 ID を取る | **単一ソース**: `ISubjectiveEpisodeStore.list_recent(player_id, max_scan)` のみ。時間軸は **「このリストの順位・`created_at` からのスコア項」**として扱われ、**別軸の候補集合としては分離されていない**。 |
| cue 逆引き（`episode_cues`） | `SqliteSubjectiveEpisodeStore` に **逆引き API**（`list_episode_ids_by_cue_keys`）とテーブルがあるが、**Passive 本線からは未使用**（テストでのみ使用）。 |
| リンク（`memory_links`）による近傍 | **保存・テストはあるが**、Passive が **リンクを読んで候補を広げる**処理は未配線。 |
| InMemory store | **`ISubjectiveEpisodeStore` 契約に cue 逆引きはない**。InMemory 実装にも **cue→episode_id の索引はない**。 |

したがって **「list_recent で候補を先に絞る」こと自体が仕様の和集合方針に反する**（ユーザ指摘どおり）。次の実装フェーズでは **Passive 専用の候補集約**（各軸 K 件 → 和集合 → スコア）へ差し替える。

**能動想起**（`SubjectiveMemoryRecallExecutor` 等）は **本ロードマップでは後回し**（別途スコープ）。現状こちらも `list_recent` ベースである点は Passive と同型の制限がある。

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
| 軸別 Passive Recall（§8・和集合） | **未達**（2026）。**スコア軸**は `passive_subjective_recall_retrieval` にあるが、**候補集合は `list_recent` のみ**。cue 逆引き・リンク近傍・「時間軸＝別候補ソース」は **未分離**。 |
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
4. **観測 vs 行動の非対称（P1 スコープ）**: 観測経路は `ToolRuntimeContextDto` を持たないため、`ObservationExperienceTrace` の **`context_spot_id` 以外の `context_*` は None**。`tile_area` / `sub_loc` / 座標を観測 trace に載せるには recorder へ runtime を渡す等の**別タスク**（上記「残り」参照）。

**タスク（残り）**

- SQLite / 長期 store のシリアライズで新フィールドを欠かさない（該当ストア実装を確認）。
- **観測 trace への runtime**: `ObservationTraceRecordingBuffer` / `ObservationAppender`（`runtime_context_provider`）/`ObservationTraceRecorder.record(..., runtime_context=)` は **実装済み**。計画本文の「未検討」は **旧記述**。**残るのは「全ゲーム経路で provider が常に付くか」の網羅確認**（テストで担保するなら本項を ✅ に更新する）。

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

- `IEpisodeEncoder.encode` に `encoding_runtime` を渡す拡張は **実施済み**（`EpisodeEncodingProcessor` が `encoding_runtime_snapshot` を渡す）。
- **Passive と状況テキスト**: cue **ヒット判定**は `episode_index_key_matches_situation` 等で、状況・目標文から **トークン化**（英数字識別子＋**日本語連続文字**）し、エピソード索引文字列と照合する。**索引側**は `subjective_episode_index_strings`＝**`cue_keys` の各要素**と **`cues` の `to_canonical()`** の和集合。`cue_keys` は **「日本語専用」ではない**（仕様 §2.3 のとおり **`entity:alice` / `object:old_box`** のような **正規化キー**が想定。LLM が長文や表記ゆれで入れたレガシー行はマッチしにくい）。**SituationCueSet**（状況用ルール cue）が未だと、**状況がプレーン日本語だけ・runtime canonical が弱いターン**では **cue 軸が弱くなり得る**。別案として「状況を無理に文章トークンに頼らず、**構造化オブジェクトから canonical cue だけを増やす**」のは仕様「Prompt 生成元オブジェクトからの Cue 生成」と整合。**全文を embedding に丸ごと載せ替える**話は仕様 §8.3 と同趣旨で、**cue の役割（検証可能なゲーム由来索引）とトレードオフ**があるため、計画では **まず構造化→canonical** を優先し、ベクトル類似は **非目標**（§1）としておく。

**受け入れ条件**

- 同一 trace から決定論的に同じ cue 列が得られる（テストで固定）。✅
- Validator（長さ上限・個数上限）を通す。✅

**Stub / テスト**

- ✅ `StubEpisodeEncoder` も同じ `episodic_cues_from_traces` で `cues` を付与（`cue_keys` は空）。

---

## P3 — Passive Recall: 軸別候補（仕様 §8 整合へ再定義）

**現状（2026）**

- **軸別スコア**（temporal / cue / importance / goal）は `passive_subjective_recall_retrieval.py` に実装済み。
- **候補エピソード集合**は **`list_recent(max_scan)` の単一窓のみ**であり、仕様 §8 の **「軸ごとに候補を取り、和集合にマージ」** とは **一致しない**（§2.2 参照）。**時間的近傍**は「別軸の候補ソース」ではなく **スコア内の temporal 項**に留まっている。

**タスク（これから）**

1. **候補集合の再設計（最優先）**
   - **時間軸**: 例）`created_at` 順の上位 **K_t** 件（専用取得。`list_recent` に名を借りず、同じ並びでも **軸独立**として扱う）。
   - **cue 軸**: 状況＋ runtime から得た canonical key 集合で **`episode_cues` 逆引き**（Sqlite。InMemory には **同契約の索引メソッド追加**か、Passive 専用アダプタで **読み取り時に線形スキャン**の暫定を許容するかを決める）。
   - **リンク軸**（任意・段階）: `memory_links` から **近傍 episode_id** を **K_l** 件。
   - 上記 ID を **和集合**し、上限 `max_candidates` で切ってから、既存の **二次スコア**（または軽量化）を適用。
2. ⏳ **SituationCueSet**（状況テキスト＋構造化入力からのルール cue）：未。P2 で拡張した抽出器と共有する。
3. ✅ **Runtime 側 canonical**（`passive_recall_situation_cues`）、`compose_user_block(..., runtime_context=)` は既存。

**受け入れ条件（更新）**

- 和集合ベースの候補生成の **単体テスト**（各軸が少なくとも「この軸だけなら古いエピソードが拾える」ことを再現）。
- 既存 regress。✅
- `PassiveRecallPickDebug`（可視化）継続。✅

**受動想起の可視化（把握用）**

- **`include_pick_debug=True`** の `PassiveRecallComposeResult.pick_debug` で、各採用行の **軸寄与**を見られる。
- 追加で「候補集合がどの軸から何件来たか」をログ／demo に出すのは **次コミット**で可（本ドキュメント更新のみのコミットでは触れない）。

---

## 12. レガシー経路の縮小ロードマップ（エピソード記憶／プロンプト）

**方針**: 本実装計画の **v2 主観エピソード＋§8 和集合 Passive** 以外の **エピソード記憶をプロンプトへ載せる経路**は段階で外す。削除は **専用ブランチ**で行い、**git 履歴に残る**（revert 可能）。**消していいか不明なモジュールは削除前に確認**する。

| 段階 | 内容 | 備考 |
|------|------|------|
| **0** | 本更新（乖離の文書化）＋ **`PassiveRecallPickDebug` 運用**で実態把握 | コード削除なし。**実装変更用ブランチ例**: `refactor/episodic-passive-recall-union`（命名は任意・PR 小さく） |
| **1** | Passive の **候補＝和集合** 実装（§2.2 / P3） | InMemory／Sqlite の I/F 調整を含む |
| **2** | **`DefaultPromptBuilder` から `IPredictiveMemoryRetriever` をオフ可能**にする（設定 or 削除）。`current_beliefs` 相当のレガシー episodic 流入を止める | 長期事実・法律など **非エピソード**は別判断 |
| **3** | **`memory_query` の `episodic` 変数**の縮小／無効化（ツール全体は別用途があれば維持） | 能動想起ツールは **後回し**（ユーザ方針） |
| **4** | P5：`MemoryContextPack` → **プロンプトへの短いブロック変換**の一本化 | reflection 経路と共有 |

**能動想起**（`SubjectiveMemoryRecallExecutor` 等）の拡張は **本ロードマップではスコープ外**（後日）。

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

- アプリ配線（`create_llm_agent_wiring` / `spot_graph_wiring`）での **`SqliteSubjectiveEpisodeStore` 既定化**や DB パス設定（環境変数等）は未。必要になったときに注入で差し替え。

**受け入れ条件**

- SQLite 上で put → cue 逆引き → 期待リンク、および `ISubjectiveEpisodeStore` 契約を満たす。✅（テスト・コード）

---

## P5 — Memory Context Pack

**意図**（仕様 §2.7）: **想起・再解釈・能動検索のたびに、その場で組み立てる作業用パッケージ**（永続化しない）。`focus`・近傍・`co_recalled`・状況・目標などを **Reflection / プロンプト組み立ての入力をそろえる**ための束ね。現状は **契約＋最小 assembly のみ**；**プロンプトへの文字列化は未配線**（`assemble_memory_context_pack_for_recall_turn` は未使用）。

**タスク**

1. ✅ `MemoryContextPack` dataclass（保存しない）を `application/llm/contracts/memory_context_pack.py` に追加。§2.7 相当フィールド＋`__post_init__` 検証。v1 は近傍・共想起を **episode_id 列**で表現。
2. ⏳ Passive Recall / Memory Reflection の **プロンプト経路への Pack 注入**は未。当面は `memory_context_pack_assembly.assemble_memory_context_pack_for_recall_turn` で既存断片から組み立て可能。
3. ⏳ temporal / associative のリンク解決・semantic / identity の実データは段階的に拡張。

**参照実装（2026）**

- 型: `memory_context_pack.py`
- 組み立て: `application/llm/services/memory_context_pack_assembly.py`
- テスト: `tests/application/llm/test_memory_context_pack.py`

---

## 7. 能動想起（スコープ外・後回し）

- ユーザ方針: **能動想起は一旦後回し**。既存 `memory_query` / `SubjectiveMemoryRecallExecutor` 等は **本計画の直近スコープに含めない**（§12 の段階 3 は **エピソード変数の縮小**が主目的。ツール全体の再設計は別タスク）。

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
- P3 で **§8 和集合ベースの候補生成** が入り、説明可能な想起になる（**現状は未達**）。
- **P4** で v2 主観エピソードの SQLite（`episode_cues` / `memory_links`）が **main に存在**し、マルチ `agent_id` で分離検証済み。✅（2026）

---

## 11. 設計のフォーク（整理済み／残論点）

**整理済み（2026）**

1. **`ToolRuntimeTargetDto` の空間 id**: `tile_location_area_id` と `sub_location_id` に分離済み。
2. **型付き cue**: `EpisodicCue` + `SubjectiveEpisode.cues`。索引マージは `subjective_episode_index_strings`。単一 `cue_keys` への統合は行わない。
3. **空間系 prefix 語彙**（例: `tile_area:` / `sub_loc:`）: **主に空間軸**の名前空間。全 cue の唯一の総称規約ではない（仕様 §2.3）。
4. **v2 優先**: 新機能・想起の主対象は **`SubjectiveEpisode`**。レガシー episodic は段階縮小。
5. **P4 永続化**: **`SqliteSubjectiveEpisodeStore` を main に導入済み**（レガシー `episode_memories` とは別 schema）。既定配線の差し替えは別タスク。
6. **Git 運用**: **小分けコミット・機能単位ブランチ・メッセージに「なぜ」**（巨大ブランチは一度まとめてマージ push 後に転換）。手続きの詳細は **[memory_feature_workflow.md](./memory_feature_workflow.md)**。

**残論点**

- `PredictiveMemoryRetriever` の**具体的な廃止順序・併存期間**（利用箇所の置換見積もり）。

---

## 10. 参照

- 作業手続き・完了後の計画更新（Git・レビュー・ブロッキング・§5）: [memory_feature_workflow.md](./memory_feature_workflow.md)
- 仕様: [episodic_memory_system_spec.md](./episodic_memory_system_spec.md)
- 詳細議事録・Tool schema 長文: [episodic_memory_reimplementation_plan.md](./episodic_memory_reimplementation_plan.md)
