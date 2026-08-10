# 予測誤差統一設計 — 実装計画 (PR 分解・依存関係・検証戦略)

> 2026-07-05。次の 3 点セットを読めば実装に着手できることを目指す。
>
> 1. [prediction_error_unified_memory_design.md](./prediction_error_unified_memory_design.md) — 原理と 6 部品 + 無意識コンテキスト (本計画の親)
> 2. [semantic_learning_consolidation_design.md](./semantic_learning_consolidation_design.md) — 証拠台帳 + belief journal の詳細仕様
> 3. [prediction_error_correction_design.md](./prediction_error_correction_design.md) — 3 段のはしご (段0/段1) の詳細仕様
>
> ステータス: 計画ドラフト (ユーザーレビュー前)。
> 2026-07-08 追記: 全 flag ON の初回実走の分析は
> [unified_memory_full_run_analysis_2026-07-08.md](./unified_memory_full_run_analysis_2026-07-08.md)
> (実走を受けた次の改善は同メモ §6 の R1〜R8)。

## 0. 共通規約 (全 PR の DoD)

- **質感シナリオ pytest を 1 本以上**: LLM を呼ばず prompt / 構造を点検する
  テスト。前例は `tests/quality/test_prediction_v1.py` (prompt dump を
  `docs/quality_checks/*.prompt.txt` に再生成して構造 assert する形)
- **snapshot 追従 (checklist #27)**: per-Being store を足す PR は同一 PR 内で
  `BeingMemorySnapshotService.EXPECTED_PAYLOAD_KEYS`
  (`application/being/being_memory_snapshot_service.py:203-215`) への key 追加、
  capture / restore、**実験スクリプトの stub
  (`scripts/run_scenario_experiment.py` の `_wiring_stub_from_world_runtime`)
  への追従**まで含める (memory_full_003 で stub 追従漏れが実際に起きた)
- **trace イベント**: 新しい判断・書き込みには `TraceEventKind`
  (`application/trace/events.py:21`) に定数を足し payload を残す
- **feature flag**: 新機構は env フラグで default OFF
  (`application/llm/wiring/feature_flags.py` の既存パターンに倣う)
- **ドメイン例外**: `domain/` 配下は各コンテキストのドメイン例外を使う
- 1 PR = 1 目的、200〜400 行目安。旧計画との名前対応は下表に固定する

### 旧計画との対応

| 本計画 | 旧名 | 出典 |
|---|---|---|
| U0 | PR-A (段0 N 件台帳) | 3 段のはしご |
| U1 | PR-B (PredictionOutcome) | 3 段のはしご |
| U2 | PR-1 (BeliefEvidence) | 新設計 |
| U3 | PR-2 (belief journal + 固着パス) | 新設計 |
| U4 | PR-3 (attribution ledger) + 部品 3 | 新設計 + 統一設計 |
| U5 | PR-4 (MEMO_DISTILL) | 新設計 |
| U6 | PR-5 (STRUCTURED_FAILURE + salience) | 新設計 |
| U7 | 部品 §4 (無意識コンテキスト) | 統一設計 |
| U8 | 部品 2 (誤差ゲート付き符号化) | 統一設計 |
| U9 | 部品 5 (想起の信用割り当て) + PR-D (段1 誤差入口) | 統一設計 + 3 段のはしご |
| U10 | 部品 6 (pending prediction) | 統一設計 |

旧 PR-C (escape_game への共有配線) は本計画のスコープ外とする。検証は
`make experiment-with-snapshot` の full 経路で行うため必須ではない。
旧 PR-E (段2) は U3 に置き換え。

## 1. PR 一覧・依存 DAG・不確実性の見取り図

| PR | 内容 | 依存 | 規模目安 | snapshot | 不確実性 |
|---|---|---|---|---|---|
| U0 | 段0 台帳の N 件化 + 未解決予測の器 | なし | 小 | ○ (schema bump) | **低** |
| U1 | prediction_context_id / PredictionOutcome | なし | 小〜中 | △ | **中** |
| U2 | BeliefEvidence VO + buffer + PREDICTION_ERROR 転記 | なし | 中 | ○ (新 store) | **低〜中** |
| U3 | belief journal + 固着 coordinator + 4 軸索引 | U2 | **大 (分割前提)** | ○ (journal 化) | **高 (本体)** |
| U4 | attribution ledger + contradict/revise + CONFIRMATION | U1, U3 | 中 | ○ (新 store) | 中 |
| U5 | MEMO_DISTILL | U3 | 小 | △ | 低〜中 |
| U6 | STRUCTURED_FAILURE + salience | U3 | 小〜中 | × | 中 |
| U7 | 無意識コンテキスト → chunk 補完 | U3 | 小 | × | **中〜高 (質の検証)** |
| U8 | 誤差ゲート付き符号化 (境界 + 解像度) | U6 | 小 | × | 中 |
| U9 | 想起の信用割り当て + 誤差駆動再解釈 + ranking boost | U1 | 中 | △ | 中〜高 |
| U10 | pending prediction (解決 cue・再浮上・清算) | U0, U2 | 中 | ○ (新 store) | **高** |

```
並行レーン (git worktree 運用は memory_feature_workflow.md 準拠)

レーン1 (台帳):   U0 ──────────────► U10 ◄─┐
レーン2 (帰属):   U1 ──┬───────► U9        │
レーン3 (belief): U2 ──┴► U3 ─┬► U4        │
                              ├► U5        │
                              ├► U6 ──► U8 │
                              ├► U7        │
                              └────────────┘ (U10 は U2 にも依存)
```

- **第 1 波 (完全並行可)**: U0 / U1 / U2
- **第 2 波**: U3 (単独。本体なので集中投下)
- **第 3 波 (並行可)**: U4 / U5 / U6 / U7 / U9
- **第 4 波**: U8 / U10

## 2. 各 PR 詳細

### U0 — 段0 台帳の N 件化 + 未解決予測の器

**できるようになること**: 直近 1 件しか見えなかった【前回の予測と実際】が
直近 N 件 (まず 3) の台帳になり、「まだ結果が出ていない予測」も保持される。

- 触る場所:
  - `application/llm/services/prompt_builder.py:109-165`
    `build_prediction_feedback_text` — 最新 1 件 → N 件ループ + 総文字数 cap
    (まず 900 字)。「結果待ち」の予測は `- 予測 (結果待ち): …` 行で出す
  - `application/llm/services/action_result_store.py` —
    `ActionResultEntry` に `resolution_state` 相当は**足さない**。「後続観測が
    まだ無い最新 entry」を結果待ちとみなす表示ロジックで済ませる (器を
    増やさない。U10 で本物の PendingPrediction を別 store に作る)
  - `application/being/world_subsystems/short_term_memory_codec.py` —
    表示ロジックのみなら bump 不要。entry にフィールドを足す場合のみ
    `_AR_SCHEMA_VERSION` bump + fixtures 更新
- テスト (LLM 無し): 3 件表示 / cap 超過の切り詰め / 結果待ち行 /
  `docs/quality_checks/prediction_v1_*.prompt.txt` の再生成差分レビュー
- **不確実性 (低)**: N と cap の最終値は実 run を見て調整前提。
  volatile section なのでプレフィックスキャッシュへの影響は小さいが、
  section が長くなると【直近の出来事】と情報が重複する — 重複が
  うるさければ行内 `[予測:]` (`chunk_encoding.py:44-65`) 側を削る判断が
  後で要るかもしれない

### U1 — prediction_context_id / PredictionOutcome (信用割り当ての土台)

**できるようになること**: 「どのプロンプト (何が in-context だったか) で
立てた予測が、どう外れたか」を 1 つの id で貫通して追える。

- 触る場所:
  - `application/llm/services/prompt_builder.py` — build ごとに id (uuid) を
    発行し、返り値 or 付随 DTO に載せる。【関連する記憶】に載せた
    episode_id 群・【関連する学び】に載せた belief (semantic entry) id 群を
    id に紐づけて記録
  - `application/llm/services/action_result_store.py` —
    `ActionResultEntry.prediction_context_id: Optional[str]` を追加
    (`short_term_memory_codec.py` bump)
  - recall_buffer (`EpisodicRecallObservation`) にも同 id を追加
    (`domain/memory/episodic/value_object/episodic_recall_observation.py`)
  - `TraceEventKind.PREDICTION_OUTCOME` を追加し、chunk 補完が
    `prediction_error` を確定した時点で outcome を trace に残す
- 記録する in-context 集合は「id のリスト」だけの軽い ledger でよい
  (per-Being store にするのは U4。U1 では turn-scope の受け渡しと
  entry への焼き込みまで)
- テスト: no-tool ターン / 例外経路 / 再スケジュールで id が混線しない
  こと (設計メモが名指しした崩れ方をそのままテストリストにする)
- **不確実性 (中)**: 1 prompt = 1 行動が崩れる経路 (ツール不発・複数
  prompt) での id の寿命定義。「prompt build 時に発行し、次の
  `ActionResultRecorder.record` (`action_result_recorder.py:47`) が
  consume する」を不変条件にし、consume されず次の build が来たら
  破棄 + trace NOTE、が現時点の推奨

### U2 — BeliefEvidence VO + evidence buffer + PREDICTION_ERROR 転記

**できるようになること**: 学習の素材 (どんな誤差がどれだけ流れているか)
が観測可能になる。semantic の挙動は一切変わらない。

- 触る場所:
  - 新規 `domain/memory/semantic/value_object/belief_evidence.py` —
    新設計どおりのフィールド。`source_kind` は
    `PREDICTION_ERROR | STRUCTURED_FAILURE | MEMO_DISTILL | FAMILIARITY |
    CONFIRMATION | PENDING_RESOLUTION` を**最初から enum に予約**
    (転記の配線は各後続 PR)
  - 新規 evidence buffer repository (interface は
    `domain/memory/semantic/repository/`、実装はインメモリ +
    `infrastructure/repository/sqlite_semantic_memory_store.py` に相乗りか
    別ファイル)
  - 転記フック: chunk 主観補完の完了点。同期経路は
    `episodic_chunk_coordinator.py:392-405` 直後、非同期経路は
    scheduler の上書き完了点 (`EPISODIC_SUBJECTIVE_*` trace を出している
    箇所) に置く。`prediction_error` が非 None なら evidence 化
  - `cue_signature` は決定論生成: `tool:<tool_name>` +
    (あれば) `spot:<場所>` / `player:<相手>`。素材は
    `ChunkEncodingInput` と `build_situation_episodic_cues`
    (`episodic_cue_rules.py:108-172`) が既に持つ値を再利用し、
    **新しい抽出ロジックを発明しない**
  - `TraceEventKind.BELIEF_EVIDENCE` 追加
  - snapshot: `EXPECTED_PAYLOAD_KEYS` に `belief_evidence_buffer` 追加 +
    codec + 実験 stub 追従
- テスト: 転記条件 (None → 積まない) / cue_signature の決定論性 /
  snapshot round-trip / 同期・非同期両経路
- **不確実性 (低〜中)**: 非同期補完だと evidence の発生 tick が行動から
  数 tick 遅れる。固着パス (U3) は周期 batch なので実害は小さい、と
  いう見込みの確認は M1 の trace で行う

### U3 — belief journal + 固着 coordinator + 4 軸索引 【本体・最重要】

**できるようになること**: 学びが「運任せに生まれ、直せない」から
「誤差が溜まれば必ず固着し、訂正できる」に変わる (新設計 S1/S4/S7)。

- 触る場所:
  - `domain/memory/semantic/` — `SemanticMemoryEntry`
    (`semantic_memory_entry.py:15-33`) を journal 対応に拡張:
    `belief_id` / `status (active|superseded|inactive)` / `supersedes` /
    `support_evidence_ids` / `contradict_evidence_ids` を追加。
    `SemanticMemoryRepository` (`semantic_memory_repository.py:23`) に
    supersede / status 更新の操作を追加。**既存の追記 API は残し、想起側
    (`semantic_passive_recall_service.py`) は active のみ読むフィルタを足す**
  - 新規 `application/llm/services/belief_consolidation_coordinator.py` —
    `episodic_reinterpretation_coordinator.py` を型紙に (turn_interval 10 /
    batch 8 / 失敗時は buffer に残して次周期)。呼び出しは同じ
    `after_turn_completed` 系のフック (`runtime_manager.py:779` 近傍) に併設
  - shortlist 索引: belief の `tags` + evidence の `cue_signature` の
    一致で top-5 を決定論選択。軸の語彙は `tool: / spot: / player: / self:`
    の 4 軸で固定 (統一設計 部品 4)
  - LLM プロンプト: 新設計の decisions JSON
    (create / strengthen / revise / contradict / discard)。
    `SemanticGistService._SYSTEM_PROMPT` (`semantic_gist_service.py:33-62`)
    の資産 (50 字命題・固有名詞・importance 基準) を引き継いで**吸収する**。
    ただし **U3b では gist service を削除しない** (実装時の判断): flag OFF の
    並存期間ではクラスタ昇格が gist service を経由し得るため、削除すると OFF
    経路が壊れる。プロンプト資産のコピーに留め、gist service 本体の削除は
    flag を default ON にしクラスタ昇格の直書きを撤去する後片付け PR に回す
  - `EpisodicSemanticClusterPromotionService`
    (`episodic_semantic_cluster_promotion.py`) — クラスタ検出部を
    FAMILIARITY evidence の生成に転用し、store 直書きと
    recall_count ゲート (:43-45) を廃止
  - confidence: `f(支持件数, 反証件数, 経過時間)` のルール関数に置換
    (機械値 `0.4+0.1n` :301 を廃止)
  - `TraceEventKind.BELIEF_CONSOLIDATION` 追加
  - flag: `BELIEF_CONSOLIDATION_ENABLED` (default OFF。OFF のとき現行
    クラスタ昇格が動き続ける並存期間を作る)
- **分割案 (400 行を超えるとき)**: U3a = journal 化 (store + 想起フィルタ +
  supersede 操作、LLM なし) / U3b = 固着 coordinator + プロンプト +
  クラスタ昇格の転用
- テスト: journal 遷移 (create→strengthen→revise→contradict→inactive) /
  shortlist の決定論性 / batch 内同型 evidence の畳み込み (LLM は stub) /
  active のみ想起 / snapshot round-trip
- **不確実性 (高)**: (a) 固着 LLM の判定品質 — strengthen と create の
  境界、batch 内畳み込みが安定するか。**ここだけは実 LLM 検証を
  プロンプト単体 replay (§3 参照) で先に回す**。(b) confidence 関数の形
  (初期値・反証の重み) は暫定でよい、と割り切る。(c) 並存期間の
  二重書き込み防止 (flag ON のときクラスタ昇格の直書きを確実に止める)

### U4 — attribution ledger + contradict/revise 配線 + CONFIRMATION

**できるようになること**: 「学びを信じて行動して外れた」が反証に、
「信じて行動して当たった」が支持になる (S3 + 統一設計 部品 3)。

- **実装時の設計変更 (逸脱)**: 当初は新規 per-Being store (attribution
  ledger) を作る計画だったが、**新 store は作らなかった**。U1 が確立した
  「recorder が turn-scope ledger から consume して `ActionResultEntry` に
  焼く」経路をそのまま延長し、in-context belief_ids を
  `ActionResultEntry.in_context_belief_ids` に載せて chunk 転記点
  (`encoding_input.action_results`) まで運び、`BeliefEvidence.in_context_belief_ids`
  へ添付する形にした。転記は chunk 補完の直後に起きるため、action が
  短期記憶に居る間に belief_ids を読めば per-Being store は不要で、
  snapshot #27 追従の静かな失敗リスクを増やさずに済む (U9 も
  recall→prediction_context_id の U1 紐付けを使うので store 不要)。
- 触る場所:
  - `ActionResultEntry.in_context_belief_ids` (recorder が U1 ledger の
    belief_ids を焼く。short_term_memory_codec schema v5)。~~新規 per-Being store~~
  - 転記 2 本 (ルールのみ、LLM なし):
    - PREDICTION_ERROR evidence に当時 in-context だった belief_id を添付 →
      固着パスの shortlist に必ず載せる
    - `prediction_error` が None かつ in-context belief があった →
      CONFIRMATION evidence (belief への支持)
  - confidence 再計算に CONFIRMATION を算入
  - snapshot: `attribution_ledger` key 追加 + stub 追従
- テスト: 添付の正しさ / CONFIRMATION の転記条件 (in-context belief 無し
  なら積まない = 水増しガード) / ledger の容量上限
- **不確実性 (中)**: 「in-context だった」は「その belief を使って予測した」
  の近似にすぎない (因果は取れない)。まず近似で入れ、固着パスの LLM に
  最終判断 (strengthen を棄却する自由) を残す。CONFIRMATION の暴走
  (何もしないターンの的中で confidence が伸びる) は「world-action の
  expected_result があるターンのみ」で絞る

### U5 — MEMO_DISTILL

- 触る場所: `memo_done` / memo 溢れの経路 (`TraceEventKind.MEMO_DONE` を
  出している箇所) から memo 本文を**無条件で** MEMO_DISTILL evidence に
  転記。discard 済み memo の再判定防止の記録 (evidence buffer 側に
  signature を残す)
- テスト: 転記 / 再判定防止 / discard 判定は U3 の固着パスに任せる
  (このPRに LLM 変更なし)
- **不確実性 (低〜中)**: discard の質は固着 LLM 依存 (M2 で観測)。
  memo 本文が固有名詞を欠いて一般化不能なケースは discard されるのが
  正しい挙動、と仕様に明記

### U6 — STRUCTURED_FAILURE + salience

- 触る場所:
  - `tool_call_loop_guard.py` の cross_tick_failure トラッカーから、同一
    (tool, fingerprint, error_code) の閾値反復で STRUCTURED_FAILURE
    evidence を転記 (実験 S5「gather は使えない」を確実に拾う)
  - `episodic_chunk_subjective_fields.py:24-59` の JSON スキーマに
    `salience: "low"|"high"` を追加 (`_SYSTEM_EPISODE_SUBJECTIVE_JSON` の
    指示 + parse + `SubjectiveEpisode` へのフィールド追加)。
    high の定義文言は「このキャラにとって予測が大きく外れた /
    初めての重大事」— **判定基準の文言が U7 の無意識コンテキストと
    噛み合って初めて意味を持つ**点に注意
  - ルール側: salience=high の evidence は件数閾値なしで次回固着パスに
    必ず載せる (S2 一撃学習)
- テスト: parse 失敗時 low 扱い / high の優先搭載 / loop_guard 転記条件
- **不確実性 (中)**: salience=high の乱発 / 出し渋りは実 LLM でしか
  分からない (§3 の replay + M2)。乱発対策の縮退 = 「1 周期に high を
  上限 k 件しか採らない」ルール cap を最初から入れておく

### U7 — 無意識コンテキスト → chunk 補完 (最優先の適用先)

**できるようになること**: `prediction_error` / `salience` の判定が
「誰にとっても同じ驚き」から「このキャラにとっての驚き」になる。

- **実装時の設計変更**: provider は `episodic_chunk_coordinator` ではなく
  **`EpisodicChunkSubjectiveFieldsService` に直接注入**した (同期/非同期
  両 scheduler 経路が呼ぶ唯一のメソッド `merge_llm_subjective_fields` が
  そこにあり、coordinator/scheduler の 3 点配線が不要になるため)。
  シグネチャも `Callable[[int, Sequence[EpisodicCue]], str]` にし、chunk 草案の
  cues を渡して cue 一致 relevance を計算できるようにした (取得失敗は空文字に縮退)。
- 触る場所:
  - `episodic_chunk_subjective_fields.py` に `unconscious_context_provider` /
    `unconscious_context_enabled` を注入 (flag OFF で prompt byte 一致)
  - provider の中身 (wiring 側 `episodic_stack.py` / `_shared_builders`):
    cue 一致 active belief top-K (confidence 付き、5 件 cap) +
    (RollingSummary 使用時のみ) L5 `self_image` / `world_view`。
    belief 取得は `SemanticPassiveRecallService`
    (`semantic_passive_recall_service.py:135-190`) を再利用
  - `episodic_chunk_subjective_fields.py:255-264` の user_sections に
    「## いまの自分 (信念と自己像)」section を追加。system プロンプトに
    「信念に照らして、何が想定内で何が想定外だったかを判定する。
    ただし事実 (ルール草案) は改変しない」を追記
- テスト: provider 注入時に prompt に section が載る / 未注入で従来と
  同一 (後方互換) / belief 5 件 cap / stub completion port で
  messages の中身を assert
- **不確実性 (中〜高)**: 確証バイアスの度合い。belief を見せると
  `prediction_error` が「信念に合う出来事を無視」する方向に倒れる
  可能性がある。構造ガード (`_assert_rule_fields_unchanged` :316) で
  事実は守られるが、**主観の質は実 LLM の A/B (§3 replay: 同じ chunk 素材を
  コンテキスト有無で 2 回流して比較) で必ず見る**。ここが崩れる場合の
  縮退 = belief を「参考。ただし観測を優先せよ」と明示する文言調整

### U8 — 誤差ゲート付き符号化 (境界 + 解像度)

- 触る場所:
  - 2a: `application/llm/chunk_boundary/rules.py:155-278` に 1 条項追加 —
    bucket 内 action に「成功予測 (expected_result あり) → success=False」
    または error_code 付き失敗があれば境界候補 (優先度は
    scene_boundary と観測件数の間)。判定素材は `ActionResultEntry` に
    全部ある
  - 2b: `_SYSTEM_EPISODE_SUBJECTIVE_JSON` (`episodic_chunk_subjective_fields.py:40-51`)
    の recall_text 長指示を salience 連動に — high: 250〜450 字 (現行) /
    low: 80〜150 字。**LLM は salience を自分で判定してから長さを選ぶ**
    (同一呼び出し内で完結、追加呼び出しなし)
- テスト: 2a の境界発火 (質感シナリオ: 罠 chunk が平凡な行動と
  分離される) / 2b は prompt 指示の存在を assert (長さ自体は実 LLM 検証)
- **不確実性 (中)**: 2a でチャンクが細かくなりすぎる → チャンク数 +X% を
  M2 run で計測し、閾値 (「失敗 1 件で即切る」か「2 件で切る」か) を調整。
  2b で低 salience 記憶が痩せて再解釈の素材を失う → 原本 observed は
  不変なので再解釈 (journal) で復元可能、が逃げ道

### U9 — 想起の信用割り当て + 誤差駆動再解釈 + ranking boost

**できるようになること**: 「この記憶を思い出したのに外れた / 思い出した
から当たった」が想起ランキングに還流し、想起自体が較正される (部品 5)。

- 触る場所:
  - U1 の紐付け (recall→prediction_context_id) を使い、`prediction_error`
    確定時に当時の in-context episode 群を判定
  - 外れ: `episodic_reinterpretation_coordinator.py` に誤差専用入口を追加
    (旧 PR-D)。generic 再解釈と混ぜず、「これらから X を予測したが Y
    だった」を明示する専用 batch item 種別として同じ周期に相乗り
  - 的中: episode の想起価値 boost。実装は
    [recall_ranking_failure_boost_design.md](./recall_ranking_failure_boost_design.md)
    の路線と統合 — `multi_cue_score` (`episodic_passive_recall_retrieval.py:389-456`)
    への加点項として入れる
- テスト: 外れ時に専用 batch item が積まれる / 的中 boost の加点 /
  habituation ペナルティとの合成順序
- **不確実性 (中〜高)**: boost の副作用 — 「当たる記憶」が固定化して
  想起の多様性が死ぬ (habituation と綱引きになる)。boost は小さく
  (まず +0.5 相当) 始め、M3 で recall 分布 (distinct episode 数) を
  現行 run と比較する。悪化したら boost を confidence 経由 (belief 側)
  だけに縮退し、episodic boost は捨てる

### U10 — pending prediction (約束・遅延予測)

**できるようになること**: 「木の下で会う約束」が場所・時刻・相手で
再浮上し、履行 / 破棄が人物 belief に清算される (シナリオ 4, 補3)。

- 触る場所:
  - 新規 per-Being store: `PendingPrediction` = {text, 解決 cue
    (spot / player / tick 範囲のいずれか複数), 発生 episode_id,
    created_tick, expires_tick}。容量上限 (まず 8) + 期限失効
  - 抽出: chunk 補完 JSON に `pending_prediction` (nullable object) を
    1 フィールド追加 — 「この chunk に、将来の特定の時・場所・相手に
    ついての約束や見込みが含まれるなら書く」。**新規 LLM 呼び出しなし**
  - 再浮上: prompt build 時、`build_situation_episodic_cues` の cue と
    解決 cue の一致 + tick 範囲到来で【保留中の予測】section に出す
    (挿入位置は【前回の予測と実際】の隣、
    `context_format_strategy.py:226-231` に併設)。件数 cap 2
  - 清算: 再浮上した pending は次の chunk 補完で「果たされたか」を
    判定させ (これも同乗フィールド)、PENDING_RESOLUTION evidence
    (果たされた → 対象 player belief への支持 / 破られた → 反証) に転記。
    判定つかず期限切れは静かに失効 (人間でも忘れられた約束は消える)
  - snapshot: `pending_predictions` key + stub 追従。
    flag: `PENDING_PREDICTION_ENABLED` default OFF
- テスト: 抽出フィールドの parse / cue 一致の再浮上 / 期限失効 /
  cap / snapshot round-trip / 質感シナリオ (約束 → 経過 → 同じ場所で
  section が出る、を LLM stub で)
- **不確実性 (高)**: (a) 抽出品質 — LLM が約束を拾えるか / 何でも
  約束扱いする乱発。replay 検証 + 「相手か場所か時刻が特定できない
  ものは書かない」の指示で絞る。(b) 解決 cue の粒度 (「夕方」を tick
  範囲にどう写像するか — 世界時刻の語彙が要る。まず tick 幅指定に
  限定し、自然言語時刻は非スコープと明記)。(c) 二者間の共有はしない —
  各自の主観記憶に独立に残るのが仕様 (すれ違いも人間らしさ)。
  ここは設計判断として PR 本文に明記する

## 3. 実 LLM テスト戦略 — コストを抑える 4 層

基準コスト: full run (survival_island_v2 / 140 tick / 4 人) =
LLM 約 400 呼び出し / 約 8.5 分 (DeepSeek V4 Flash)。これを「1 full」と
数える。

| 層 | 手段 | LLM コスト | 使いどころ |
|---|---|---|---|
| L0 | 質感シナリオ pytest (prompt dump + 構造 assert) | **0** | 全 PR の DoD。`tests/quality/test_prediction_v1.py` パターン |
| L1 | stub completion port の unit / integration | **0** | 呼び出しに何が渡ったか (無意識コンテキスト等) と、応答の parse・縮退 |
| L2 | **プロンプト単体 replay** (下記) | 数十 call | 固着パス (U3)・salience (U6)・無意識コンテキスト A/B (U7)・pending 抽出 (U10) のプロンプト品質 |
| L3 | 実験 run | mini 1/6 full〜 | 機能の合成でしか出ない挙動。マイルストーンのみ |

### L2: プロンプト単体 replay (本計画の主力節約手段)

既存 run の `trace.jsonl` (memory_full_003 等) から素材を抽出し、
**対象のバックグラウンド LLM 1 種だけ**をオフラインで呼ぶ使い捨て
スクリプト (`scripts/` に置く)。full run を回さずにプロンプトを回せる。

- 固着パス: 003 の trace から prediction_error 群を evidence 形式に
  変換して batch 8 件 × 数バッチ → decisions の質 (畳み込み・discard) を
  目視。**1 反復 ≈ 5〜10 call** (full run の 1/50)
- salience / 無意識コンテキスト: 同一 chunk 素材でコンテキスト
  有り / 無しの 2 回流し、prediction_error と salience の差を比較
  (A/B)。**1 素材 2 call**
- プロンプト文言の調整はこの層で収束させてから L3 に行く

### L3: 実験 run のマイルストーン (full 相当は合計 ~4 回で済ませる)

mini 構成 = `MAX_WORLD_TICKS=40 WORKERS=2` (≈ 60〜70 call ≈ 1.5 分 ≈
1/6 full)。`make experiment-resume` (snapshot 再開) で前半をスキップし
学習後半だけ観測する再利用も使う。

| 節目 | タイミング | 構成 | 見るもの (trace で機械的に数える) |
|---|---|---|---|
| M1 | U2 完了後 | **追加 run 不要** — U2 は LLM 挙動不変なので、開発中の任意の run 1 本の trace で `BELIEF_EVIDENCE` の流量 (件数 / 人、cue_signature 分布) を確認 | evidence が 4 人全員に流れているか |
| M2 | U3 + U6 完了後 | mini ×2 + full ×1 | 学び件数 / 人 (4 人全員 ≥1)、同型教訓の重複 0 (S7)、一撃学習 (S2)、`BELIEF_CONSOLIDATION` の decisions 内訳、チャンク数の変化率 (U8 準備) |
| M3 | U4 / U7 / U9 完了後 | full ×1 | contradict / CONFIRMATION の発生、confidence の分布、recall 多様性 (U9 副作用)、prediction_error の質の変化 (U7 A/B は L2 で済ませておく) |
| M4 | 全 PR 後 | full ×1 (140 tick) + 統一設計 §6 シナリオ表の総点検 | 約束シナリオ (U10) は survival に無ければ専用の小シナリオ (`data/scenarios/` に 2 人・20 tick の約束 rig) を 1 本作る — mini 以下のコスト |

run 結果の分析は `/trace-analysis <run_dir>` を使う。

## 4. 不確実性の総括と全体の逃げ道

**高 (プロンプト品質に賭けている場所)**: U3 固着 LLM / U7 確証バイアス /
U10 約束抽出。いずれも L2 replay で run 前に収束させる。共通の縮退は
「LLM 失敗・低品質時は evidence を buffer に残して次周期」(新設計の
既定) で、**決定論 fallback で belief を作らない**。

**中 (パラメータ調整が残る場所)**: U1 id の寿命 / U6 salience 乱発 /
U8 境界の感度 / U9 boost 副作用。いずれも定数 1 つの調整で効きを
変えられる形にしておく (cap・閾値・加点量)。

**低 (機械的)**: U0 / U2 / U5。snapshot 追従の作業漏れだけが敵
(checklist #27 と起動時 fail-fast が防波堤)。

計画全体の逃げ道: 全機構が feature flag default OFF なので、どの PR も
main に入れて良い。実験は flag の組で新旧を A/B でき、破滅的な
リグレッションは「flag を戻す」で止まる。
