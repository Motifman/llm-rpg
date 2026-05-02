# Episodic Memory — 実装計画

本文書は [episodic_memory_system_spec.md](./episodic_memory_system_spec.md) の仕様を、**既存コードに載せるための移行・実装順序**に落としたものである。詳細な Tool 引数設計や Chunker の議論のフルテキストは、必要に応じて [episodic_memory_reimplementation_plan.md](./episodic_memory_reimplementation_plan.md) を参照する。

## 1. 目的と非目標

- **目標**: 型付き cue・想起軸・（将来）リンク store により、Passive/Active 想起が **ゲーム由来 id** で安定し、Memory Context Pack へ拡張しやすい土台にする。
- **非目標（初期）**: グラフ DB、embedding 類似検索、全ペアリンク更新。

## 2. 現状コードの要点（2026 時点）

| 領域 | 主なモジュール |
|------|----------------|
| v2 主観エピソード | `SubjectiveEpisode`, `InMemorySubjectiveEpisodeStore`, `llm_json_episode_encoder.py` |
| Trace | `ActionExperienceTrace`, `ObservationExperienceTrace`, `agent_orchestrator._append_action_experience_trace` |
| Passive Recall | `passive_subjective_recall_composer.py`（cue を状況テキストに部分一致＋ recency） |
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

### 3.1 Git・ブランチ運用（方針）

記憶まわりでブランチが巨大化しやすいため、次を**この Plan 上の合意**として固定する。

1. **いま溜まっている変更**は、レビュー可能な単位で **main へマージして push する**（長寿命の巨大 feature ブランチを止める）。
2. **以降は機能単位ブランチ**にする。例: `feature/episodic-trace-spatial-fields`、`feature/episodic-rule-cues`、`feature/episodic-sqlite-index`。1 ブランチに複数ドメインを詰め込まない。
3. **コミットは小分け**にする。目安は「1 コミット＝レビューで説明できる 1 つの意図」（リネームだけ、テストだけ、ドキュメントだけ、なども分離してよい）。WIP をコミットに載せ続けない。
4. PR も **小さく**し、マージ後に次ブランチを切る。

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
| in-memory only の v2 store（本番寄り運用時） | deprecated（方針） | P4 の SQLite 本線へ |

---

## P0 — 空間まわりの命名・DTO リファクタ

**問題**: `ToolRuntimeTargetDto.location_area_id` がスポットグラフでは `sub_location_id` を指していた。`LocationAreaId`（タイル）と混同する。

**実施済み（2026）**

- `ToolRuntimeTargetDto`: **`tile_location_area_id`**（タイル）と **`sub_location_id`**（グラフ区画）に分離。スポットグラフ／タイル経路は各フィールドへ設定。
- `SubjectiveEpisode`: **`cues: Tuple[EpisodicCue, ...]`** を追加。`EpisodicCue(axis, value, source)` は `to_canonical()` で `axis:value` に変換。想起・重複判定は **`subjective_episode_index_strings(ep)`** で `cue_keys` とマージ。
- **移行方針**: レガシー文字列索引は当面 `cue_keys` のまま残し、ルール生成は `cues` に載せて統合関数で一本化する。

**オープン（P1）**

- `ToolRuntimeContextDto` に **`current_sub_location_id`**（任意）を追加するかは、trace コピー要件とあわせて判断する。

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
| trace への構造化位置コピー | 未着手 |
| ルールベース cue + validator 主導 | 未着手（Plan §3.2–3.3 に沿い LLM `cue_keys` を外していく） |
| 軸別 Passive Recall | 未着手 |
| `episode_cues` / `memory_links` | 未着手 |
| v2 と `PredictiveMemoryRetriever` の統合方針 | **ユーザ判断**（段階廃止 / 併存期間） |

---

## P1 — 構造化位置と `current_spot_id`

**問題（残件）**: 記憶 cue や trace 永続化のため、`ToolRuntimeContextDto` 由来の id を **ExperienceTrace にコピー**する処理がまだない。

**進捗**

1. ✅ `SpotGraphPlayerSnapshotDto` に **`current_spot_id: int`** を追加。`SpotGraphCurrentStateBuilder` が設定。`SpotGraphUiContextBuilder` が `ToolRuntimeContextDto.current_spot_id` に渡す。

**タスク（残り）**

2. `ActionExperienceTrace` / `ObservationExperienceTrace` に、仕様 §2.4 の構造化 location フィールドを**段階的に追加**（文字列 snapshot は維持）。
3. trace 保存処理（例: `agent_orchestrator._append_action_experience_trace`）で `tool_runtime_context` からコピーする。

**受け入れ条件**

- スポットグラフ run で `ToolRuntimeContextDto.current_spot_id` が非 null（該当セッションで spot が決まる場合）。✅
- 単体テストで trace に期待する spot / sub_loc / area が残る。（trace 改修後に要求）

---

## P2 — ルールベース cue 抽出

**タスク**

1. 新モジュール（例: `application/llm/services/episodic_cue_extraction.py`）に集約:
   - 入力: `ActionExperienceTrace` | `ObservationExperienceTrace` | 現在の `ToolRuntimeContextDto` 断片
   - 出力: **`EpisodicCue` の列**（保存時は `SubjectiveEpisode.cues`）。必要なら移行期に併せて正規化 `tuple[str, ...]` を `cue_keys` にも複写する。
2. ドメインから取れる **object 型・カテゴリ**（`SpotObject` 等）を可能な範囲で `object_category:` / `object_type:` に載せる。
3. `LlmJsonEpisodeEncoder` / reflection: **索引用 `cue_keys` を LLM に書かせない**（Plan §3.3）。空間 cue は §3.2 の axis だけルールが埋める。

**受け入れ条件**

- 同一 trace から決定論的に同じ cue 列が得られる（テストで固定）。
- Validator（prefix・長さ上限・個数上限）を通す。

---

## P3 — Passive Recall: 軸別候補

**タスク**

1. `PassiveSubjectiveRecallComposer` を分割:
   - **TemporalRetriever**: `list_recent` + tick 窓（利用可能なら）
   - **CueOverlapRetriever**: 現在状況から生成した **SituationCueSet**（P2 と同じ抽出器）と episode の cue 交差
   - **GoalOverlapRetriever**: 現状のトークン一致を維持しつつ、将来的に `goal:` key へ
2. 各 retriever が id 集合を返し、**和集合 → 重複カウントまたは二次スコア**で並べ替え。
3. `situation_text` への cue の生文字列依存を弱める（可能なら）。

**受け入れ条件**

- 既存テストを更新・追加し、回 regress しない。
- デバッグ用に「どの軸が候補に効いたか」をログまたはテストで見える化（任意だが推奨）。

---

## P4 — `episode_cues` / `memory_links`

**タスク**

1. 仕様 §2.5 のテーブル相当を **SQLite で実装**する（`agent_id` スコープ）。検証用の in-memory は短命のフィクスチャに留める。
2. SubjectiveEpisode 保存時に index を更新。全件走査禁止（cue → episode_id 限定制）。
3. リンク種: 初期は `temporal`, `spatial`（cue 重なり）, `co_recalled` 程度。

---

## P5 — Memory Context Pack

**タスク**

1. `MemoryContextPack` dataclass（保存しない）を `application/llm/contracts` に追加。
2. Passive Recall / Memory Reflection の入力を、可能な範囲で Pack 組み立てに寄せる。
3. 仕様 §2.7 のフィールドを段階的に埋める。

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

---

## 11. 設計のフォーク（整理済み／残論点）

**整理済み（2026）**

1. **`ToolRuntimeTargetDto` の空間 id**: `tile_location_area_id` と `sub_location_id` に分離済み。
2. **型付き cue**: `EpisodicCue` + `SubjectiveEpisode.cues`。索引マージは `subjective_episode_index_strings`。単一 `cue_keys` への統合は行わない。
3. **空間系 prefix 語彙**（例: `tile_area:` / `sub_loc:`）: **主に空間軸**の名前空間。全 cue の唯一の総称規約ではない（仕様 §2.3）。
4. **v2 優先**: 新機能・想起の主対象は **`SubjectiveEpisode`**。レガシー episodic は段階縮小。
6. **Git 運用**: **小分けコミット・機能単位ブランチ**（巨大ブランチは一度まとめてマージ push 後に転換）。詳細は **§3.1**。

- `PredictiveMemoryRetriever` の**具体的な廃止順序・併存期間**（利用箇所の置換見積もり）。
- `ToolRuntimeContextDto.current_sub_location_id` の要否（P1 trace 設計とセット）。

---

## 10. 参照

- 仕様: [episodic_memory_system_spec.md](./episodic_memory_system_spec.md)
- 詳細議事録・Tool schema 長文: [episodic_memory_reimplementation_plan.md](./episodic_memory_reimplementation_plan.md)
