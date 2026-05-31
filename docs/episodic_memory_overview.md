# エピソード記憶パイプライン総括 (第20-23回実験を踏まえた現状設計)

このドキュメントは、`沈黙の禁書庫` シナリオで episodic memory を実走検証
した第20-23回実験 (Issue #295 / #311 / #325 / #328) を通じて整備した、
現行のエピソード記憶パイプラインの**設計・配線・運用知見**をまとめたものです。

「これから別シナリオに同じ paradigm を持っていきたい」「新規開発者がパイプライン
全体を把握したい」場合の最初の参照点です。

---

## 1. 設計の出発点と原則

### 1.1 目的

LLM エージェントが**過去の体験を主観的に思い出して**意思決定に活かせるようにする。
重要なのは「データベース検索」ではなく **emergent な記憶想起**:

- 観測の prose に「書架A」と書かれていれば、過去に書架A を訪ねたエピソードが
  自然に prompt に滲み出る
- 「カイトが○○へ去っていった」観測を見れば、「カイトはあそこにいるかも」と
  追跡行動が emergent に発生する

### 1.2 守る原則

| 原則 | 効果 |
|---|---|
| **ハードコードな pathfinding を避ける** | LLM の自発的な判断を尊重する。「目的地まで N tick」のような決定論的な探索パスは入れない |
| **観測 prose を一次情報とする** | 構造化データ (cue) は補助、文章は LLM が読む本体 |
| **scene 境界を認知科学に合わせる** | working memory / event segmentation theory の値域に揃える |
| **非同期で LLM 補完する** | ゲーム tick を止めない (#310 Pattern A) |
| **失敗で死なない** | LLM 失敗時はテンプレフォールバック、scheduler 失敗時は draft が残る |

---

## 2. 全体アーキテクチャ

### 2.1 コンポーネント図

```
                  ┌────────────────────────────────────────┐
                  │           LLM Agent (per player)        │
                  │  inner_thought + tool call → action    │
                  └──────────────┬─────────────────────────┘
                                 │ tool dispatch
                                 ▼
┌──────────────────────────────────────────────────────────┐
│ EscapeGameRuntime (do_move / do_speech / do_wait / ...)  │
│                                                            │
│ ┌─────────────────────────────────────────────────────┐  │
│ │ _record_action_result(scene_boundary, tool_name, ...)│  │
│ │   ├─→ ActionResultStore.append                       │  │
│ │   └─→ chunk_coordinator.after_action_recorded         │  │
│ └─────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
                                 │
                                 ▼
            ┌────────────────────────────────────────────┐
            │ EpisodicChunkCoordinator                    │
            │  1. observation_buffer.drain → sliding_window │
            │  2. bucket に最新 action 追加              │
            │  3. decide_chunk_boundary(...)               │
            │     ├─ MIN/MAX/TEMPORAL_GAP/scene_boundary   │
            │     └─ category_shift / salient(breaks_movement) / count │
            │  4. close 判定なら ChunkEpisodeDraftBuilder.build  │
            │     └─ draft.recall_text = テンプレ既定値 (#305) │
            │  5. episode_store.put(draft)  ← 即書き         │
            │  6. subjective_completion_scheduler.submit(draft) │
            │     ← 非ブロッキング (#310)                  │
            └────────────────────────────────────────────┘
                                 │
                ┌────────────────┴────────────────┐
                ▼                                  ▼
  ┌─────────────────────────────┐  ┌────────────────────────────────┐
  │ ThreadPoolScheduler          │  │ Recall path                     │
  │  (worker thread)              │  │  prompt_builder.build_full_prompt │
  │  ↓                            │  │  ↓                              │
  │  EpisodicChunkSubjectiveFields │  │  retrieve passive recall         │
  │  Service.merge_llm_subjective  │  │  ↓                              │
  │  ↓ LLM 呼び出し (~10s)         │  │  cue-based + free-text matcher  │
  │  ↓                            │  │  ↓                              │
  │  store.put(merged) で          │  │  recall_text を system prompt の │
  │  同 episode_id を上書き       │  │  「過去の記憶」セクションに注入 │
  └─────────────────────────────┘  └────────────────────────────────┘
```

### 2.2 主要レイヤと責務

| レイヤ | 主要クラス | 責務 |
|---|---|---|
| Domain | (なし — 純粋なルールのみ) | — |
| Application / write | `EpisodicChunkCoordinator` | chunk 境界判定 + draft 生成 + 上書き完了の orchestration |
| Application / write | `ChunkEpisodeDraftBuilder` | テンプレ既定値で draft を組み立て |
| Application / write | `EpisodicChunkSubjectiveFieldsService` | LLM で `interpreted` / `recall_text` を生成 |
| Application / scheduler | `ThreadPoolEpisodicSubjectiveScheduler` | 非同期 LLM 呼び出し + 失敗フォールバック |
| Application / read | `EpisodicPassiveRecallRetrievalService` | situation cues から episode を引く |
| Application / read | `WorldNounMatcher` | observation 自由文から固有名詞 cue を抽出 |
| Infrastructure | `InMemorySubjectiveEpisodeStore` (thread-safe) | episode 永続層 (将来 SQLite に差し替え可能) |
| Trace | `JsonlTraceRecorder` + `TraceEventKind.EPISODIC_*` | Viewer / 分析用 |

---

## 3. データフロー

### 3.1 chunk write 経路 (action → episode 保存)

1. LLM が tool call → `do_move(player_id, dest)` 等 が走る
2. `_record_action_result(tool_name, success, scene_boundary, occurred_tick)` を呼ぶ
3. action_result_store にエントリ追加 (tz-aware UTC で記録 #318)
4. `chunk_coordinator.after_action_recorded(player_id)` を呼ぶ
5. observation buffer から drain → sliding_window に反映
6. bucket (per-player) に最新 action 追加
7. `decide_chunk_boundary` で **#4. 境界判定** (詳細は §4)
8. close → `ChunkEpisodeDraftBuilder.build()` で draft 生成
   - `observed` = 統一タイムラインの bullet 連結
   - `recall_text` = `observed` の最初の非空行 (テンプレ既定値、#305)
   - `cues` = `place_spot` / `entity` / `object` / `action:tool_name` / `outcome:success|failure_*`
9. `episode_store.put(draft)` で **即** 書き込み (recall でテンプレが乗る #305)
10. `scheduler.submit(draft)` で LLM 補完を裏に投入 (非ブロッキング #310)
11. worker thread が `service.merge_llm_subjective_fields(draft)` を実行
12. 完了時 `store.put(merged)` で同じ `episode_id` を上書き
13. `EPISODIC_SUBJECTIVE_FILLED` trace に記録

### 3.2 recall 経路 (prompt 生成時)

1. `prompt_builder.build_full_prompt(player_id)` が呼ばれる
2. `build_situation_episodic_cues(runtime_context, observation_structured, observation_prose, noun_matcher)`
   で **状況 cues** を組み立て:
   - 現在 spot / sub_location / object → `place_spot:N` / `object:obj_N`
   - 直近観測 structured → `entity:actor:N` / `place_spot:N` 等
   - **自由文 prose** → `WorldNounMatcher` (Aho-Corasick) で固有名詞を cue 化
3. `passive_recall.retrieve(player_id, situation_cues)` で episodes を検索
4. 結果を `_join_passive_recall_texts` で連結 (LLM 上書き優先、テンプレ次)
5. system prompt の「過去の記憶」セクションに注入
6. `EPISODIC_RECALL` trace に candidates と source_axes を記録

### 3.3 shutdown 経路 (#326)

1. ゲーム終了で `_drive_scenario` が終わる
2. `runtime.shutdown(timeout=30.0)` を呼ぶ
3. `scheduler.shutdown(timeout)` が ThreadPool の pending を drain
4. worker thread が終わるまで wait (timeout=30s)
5. `recorder.close()` で trace ファイルを閉じる
6. **defense-in-depth**: 残余 worker が close 後に record を呼んでも silently drop
   + `record_dropped_after_close` カウンタで観測可能

---

## 4. チャンク境界条件 (cognitive science 根拠)

### 4.1 設計指針

人間のエピソード記憶は連続体験を以下の変化点で区切る (Zacks et al. Event
Segmentation Theory):

| 変化軸 | ゲーム world に対応 |
|---|---|
| 空間 | spot 遷移 ("doorway effect") |
| 時間 | 長時間 wait / heartbeat |
| 登場人物 | 新しい actor 登場 |
| 目標 | action_result.success の極性反転 |
| 対象 | structured object_id 変化 |

**チャンク粒度**: scene-level (1-3 分、action 5-10 件相当) を狙う。
working memory 限界 (Miller 7±2) を上限に。

### 4.2 現行の閾値 (`chunk_boundary/rules.py`)

```python
OBSERVATION_COUNT_CLOSE_THRESHOLD = 5     # scene 級の自然な観測数
MIN_ACTIONS_FOR_CLOSE             = 3     # 単発 action は episode に値しない
MAX_ACTIONS_FOR_CLOSE             = 7     # working memory 上限
TEMPORAL_GAP_TICKS_FOR_CLOSE      = 8     # 時間断絶 = 別 scene
```

### 4.3 判定順 (`decide_chunk_boundary`)

```
1. INSUFFICIENT_ACTIONS (0件)  → HOLD
2. SEGMENT_EXPLICIT             → 即クローズ (最優先)
3. MAX_ACTIONS_REACHED          → 強制クローズ
4. TEMPORAL_GAP                 → 強制クローズ
5. MIN_ACTIONS_NOT_MET          → 強制 HOLD (← micro-event 防止)
6. SCENE_BOUNDARY_ACTION        → クローズ (doorway effect)
7. CATEGORY_SHIFT / STRUCTURED_KEYS_CHANGED → クローズ
8. OBSERVATION_SALIENT (breaks_movement のみ) → クローズ
9. OBSERVATION_COUNT_THRESHOLD (5件) → クローズ
10. HOLD_ACCUMULATING (蓄積継続)
```

### 4.4 `scene_boundary` フラグ

`ActionResultEntry.scene_boundary: bool` を caller が立てる。現状の用途:

- `do_move` 成功 (= spot 遷移) → `True`
- それ以外 → `False`

将来は `do_interact` (重要な扉開け等) にも伝搬する余地あり。

### 4.5 `schedules_turn` を **意図的に salient から除外**

第21回実験で「`schedules_turn=True` の観測が来るたび chunk が閉じる」過剰
発火を観測。`schedules_turn` は「LLM ターン投入トリガ」であって認知的な
scene 境界とは別概念。現実装では `breaks_movement` のみが SALIENT 判定に
寄与する。

---

## 5. 設定可能なパラメータ

### 5.1 環境変数

| 変数 | 既定 | 説明 |
|---|---|---|
| `LLM_EPISODIC_ENABLED` | unset (= off) | episodic pipeline 全体の on/off |
| `LLM_EPISODIC_SUBJECTIVE_ENABLED` | **on** (#308) | LLM 主観文付与の on/off。明示的 off は `0`/`false`/`no`/`off` |
| `LLM_CLIENT` | `stub` | `litellm` のときだけ subjective service が実 LLM を叩く (`stub` だと silent skip) |
| `LLM_MODEL` | (環境依存) | LiteLLM 経由のモデル名 |

### 5.2 コード内チューニング定数 (`chunk_boundary/rules.py`)

```python
OBSERVATION_COUNT_CLOSE_THRESHOLD = 5
MIN_ACTIONS_FOR_CLOSE             = 3
MAX_ACTIONS_FOR_CLOSE             = 7
TEMPORAL_GAP_TICKS_FOR_CLOSE      = 8
```

### 5.3 Scheduler の挙動 (`escape_episodic_wiring.py`)

```python
ThreadPoolEpisodicSubjectiveScheduler(
    max_workers=1,           # LLM API の RPS 制限考慮、安全側
    max_queue_size=100,      # in-flight + pending の上限
)
runtime.shutdown(timeout=30.0)  # subjective_filled p95 = 13.4s の 2x 余裕
```

---

## 6. 観測可能性 (Trace Event)

### 6.1 新規追加した trace kind

| Kind | 発火タイミング | payload (主要) |
|---|---|---|
| `EPISODIC_CHUNK_WRITTEN` | chunk_coordinator が境界を閉じ store に書いた瞬間 | `episode_id`, `boundary_reason`, `cues`, `recall_text_snippet`, `action_count`, `observation_count` |
| `EPISODIC_RECALL` | prompt build 時に passive recall を実行 | `situation_cues`, `candidate_count`, `candidates[].source_axes`, `recall_text_snippet` |
| `EPISODIC_SUBJECTIVE_FILLED` | scheduler worker が LLM 補完を完了し store を上書き | `episode_id`, `latency_ms`, `recall_text_snippet` |
| `EPISODIC_SUBJECTIVE_FAILED` | LLM 呼び出し失敗 / parse 失敗 (draft のまま) | `episode_id`, `error_code` |
| `EPISODIC_SUBJECTIVE_DROPPED` | キュー満杯 or shutdown 後 submit で drop | `episode_id`, `reason` ("queue_full"/"shutdown"), `queue_size` |

### 6.2 Viewer での見方

- Viewer タイムラインで `episodic_chunk_written` (黄緑) と `episodic_recall` (黄色) が密集 → 健全
- `recall_text_snippet` が空 → テンプレ未埋め or LLM 補完未配線
- `subjective_failed` が多い → LLM API 不調 / プロンプト破綻
- `subjective_dropped (reason: shutdown)` → runtime.shutdown timeout が短い
- `post-close record drops` log INFO 行 → drain timeout 再検討

---

## 7. 試験戦略

### 7.1 単体テスト

- `tests/application/llm/chunk_boundary/test_episodic_chunk_boundary_rules.py` (26 件)
- `tests/application/llm/test_episodic_chunk_subjective_fields.py` (template / LLM merge)
- `tests/application/llm/services/test_episodic_subjective_completion_schedulers.py`
  (Inline / ThreadPool / shutdown / dedupe / dropped trace)
- `tests/application/llm/services/test_episodic_trace_emission.py` (trace event 内容)
- `tests/application/trace/test_recorder.py` (close-race を ThreadPool で実再現)

### 7.2 統合テスト (smoke)

- `tests/integration/test_escape_game_episodic_smoke.py`
  - 配線スイッチ (LLM_EPISODIC_ENABLED / SUBJECTIVE_ENABLED)
  - chunk write の最小シナリオ (3 action + scene_boundary)
  - LLM stub による上書き e2e
  - 非同期 scheduler 経由 e2e

- `tests/integration/test_escape_game_episodic_recall_harness.py`
  - 過去 episode → place_spot cue → recall 検索
  - structured cue 経路
  - 自由文 (noun_matcher) 経路

### 7.3 ドライランシミュレータ

`scripts/episodic_chunk_simulation.py` で trace.jsonl から複数の境界
ポリシーを当てた chunk 数 / 平均サイズを比較できる。パラメータ調整の
事前検証用。

### 7.4 実走実験

`scripts/run_scenario_experiment.py` で trace.jsonl + Viewer HTML + 報告 md を生成。

---

## 8. 実験的に得た知見 (第20-23回)

### 8.1 第20回 (Issue #295) — blocker 発覚

- `TypeError: can't compare offset-naive and offset-aware datetimes` で
  48/50 件の chunk write が失敗 → エピソード記憶仮説の検証不可
- `recall_text_snippet` が全件空 (LLM 補完未配線)
- `outcome:success` / `action:unknown_tool` が全 episode にあるノイズ

→ datetime tz 統一 (#300/#302/#309) + テンプレ既定値 (#305) + 配線
  (#307/#308) + 非同期化 (#309/#310) で順次解消

### 8.2 第21回 (Issue #311) — 残課題発見

- `recall_text` が現在形・意志形と混在
- 「カイトがこのスポットを去った」観測に方向情報がない
- chunk 平均 act/chunk が 3.4 = micro-event 級 (scene-level に届かず)
- `schedules_turn=True` 過剰発火が chunk 短化の主因
- datetime tz 回帰 21 件 (#300 取りこぼし)

→ 過去形 prompt (#314) + 方向観測 (#316) + datetime tz 根本修正 (#318) +
  chunk 境界 認知科学化 (#323)

### 8.3 第22回 (Issue #325) — chunk 粒度問題部分達成

- shutdown race が 2 件継続 (`recorder is already closed`)
- chunk 粒度はまだ 3.7 act/chunk (escape_game の部屋構造に依存)

→ shutdown race 修正 (#326) で完全解消。chunk 粒度は escape_game の
  特性として受容 (cognitive science の 5-10 は日常生活基準で、狭い
  部屋を頻繁に移動する puzzle ゲームでは 3-4 でも自然)

### 8.4 第23回 (Issue #328) — 卒業

- `recorder closed` = 0、`post-close drops` = 0 (完璧な drain)
- subjective_filled / chunk = 17/17 (100%)
- recall_text 非空 17/17 (100%)
- ON wall time 224s = OFF 320s より高速 (1 run のため非決定性あり)
- 追跡行動 / 記憶参照ともに閾値クリア

→ **沈黙の禁書庫シナリオでの episodic memory 検証 卒業**

### 8.5 学んだメタ知見

1. **観測 trace の充実が後追いデバッグの命綱** — `subjective_filled` / `failed`
   / `dropped` がなければ第22-23回の課題特定はできなかった
2. **Pattern A (Fire-and-forget) は非同期化の素直な解** — game tick を
   止めず、失敗時もテンプレが残るので壊れない
3. **認知科学の数字は「日常生活」前提** — ゲームの特性で 30-50% ズレる
   ことがある。シミュレータで事前検証してから本実装
4. **silent failure を defensive に握りつぶしすぎない** — 観測可能化が
   問題発見の前提。WARN + counter で「期待される race」と「異常」を分離
5. **trace event 設計を本実装と平行で書く** — payload schema を decide
   する段階で「何を見たいか」が定まり、実装の責務分割が明確になる

---

## 9. 次のシナリオへの移行ポイント

### 9.1 別シナリオに pipeline を持っていくときの必須項目

1. **scenario 構造から固有名詞 matcher を組み立てる**
   - 現状: `build_scenario_noun_matcher` (spot 名 + character 名)
   - 拡張余地: world_object / item 名も拾えるように

2. **runtime に `scene_boundary` 経路を生やす**
   - `_record_action_result(scene_boundary=True)` を呼ぶ箇所を決める
   - 最低限 spot 遷移成功 (= `do_move`)

3. **`runtime.shutdown(timeout)` 経路の確保**
   - scheduler の drain hook

4. **observation pipeline が方向情報を出している**
   - `entity_left_spot` / `entity_entered_spot` に `to_spot_id_value` /
     `from_spot_id_value` / `connection_name`

5. **persona_block_provider の組み立て**
   - 各 player_id → persona text の dict を作る

### 9.2 共通化済み (PR #330)

`src/ai_rpg_world/application/llm/wiring/episodic_stack.py` に汎用 builder を
配置済み:

```python
from ai_rpg_world.application.llm.wiring.episodic_stack import (
    EpisodicStack,
    build_episodic_stack,           # 推奨 (シナリオ非依存)
    build_scenario_noun_matcher,
    is_episodic_enabled,
    is_episodic_subjective_enabled,
)
```

`demos/escape_game/escape_episodic_wiring.py` は後方互換のための薄い shim
(旧 `EscapeEpisodicStack` / `build_escape_episodic_stack` 名で alias) のみ
残しているので、新規シナリオは application 層を直接 import する。

別シナリオに繋ぐときの典型コード:

```python
from ai_rpg_world.application.llm.wiring.episodic_stack import (
    build_episodic_stack, is_episodic_enabled,
)

if is_episodic_enabled():
    runtime._episodic_stack = build_episodic_stack(
        scenario=scenario,            # player_spawns を持つ任意の object
        graph=spot_graph,             # _spots を持つ任意の object
        observation_buffer=...,
        sliding_window_memory=...,
        action_result_store=...,
        trace_recorder_provider=lambda: runtime._trace_recorder,
        current_tick_provider=runtime.current_tick,
        subjective_completion_scheduler=...,  # 任意 (非同期 LLM 補完)
        persona_block_provider=lambda pid: ...,
        episode_store=shared_store,           # scheduler と共有する場合
    )
```

`runtime` 側は:

- `_record_action_result(scene_boundary=True)` を移動成功時に呼ぶ
- `shutdown(timeout=30.0)` を runtime に生やして scheduler drain 経路を作る
- `set_trace_recorder` で trace を後から差し込む経路にする

---

## 10. ファイル位置リファレンス

### 主要ソース

```
src/ai_rpg_world/application/llm/
├── chunk_boundary/rules.py                   # boundary 判定
├── contracts/
│   ├── dtos.py                                # ActionResultEntry (scene_boundary, occurred_tick)
│   ├── episodic_memory.py                    # SubjectiveEpisode, EpisodicCue
│   ├── episodic_subjective_scheduler_port.py # IEpisodicSubjectiveCompletionScheduler
│   └── episodic_chunk_subjective_llm_port.py # IEpisodicChunkSubjectiveCompletionPort
└── services/
    ├── action_result_store.py                # store + scene_boundary 伝搬
    ├── chunk_episode_draft_builder.py        # テンプレ既定値
    ├── episodic_chunk_coordinator.py         # orchestration
    ├── episodic_chunk_subjective_fields.py   # system prompt + template fallback
    ├── episodic_cue_rules.py                 # cue 構築 (place/entity/object/action/outcome)
    ├── episodic_passive_recall_retrieval.py  # recall 検索
    ├── episodic_subjective_completion_schedulers.py  # Inline / ThreadPool
    ├── in_memory_subjective_episode_store.py # thread-safe store
    └── world_noun_matcher.py                  # Aho-Corasick による cue 抽出
```

### シナリオ非依存 wiring (PR #330)

```
src/ai_rpg_world/application/llm/wiring/
└── episodic_stack.py                          # build_episodic_stack (シナリオ非依存)
                                               #  + EpisodicStack dataclass
                                               #  + build_scenario_noun_matcher
                                               #  + is_episodic_enabled / _subjective_enabled
```

### escape_game 固有 wiring

```
demos/escape_game/
├── escape_episodic_wiring.py                 # 後方互換 shim (旧 alias のみ)
├── escape_game_runtime.py                    # _record_action_result, shutdown
└── ...
```

### Trace / 観測 / 試験

```
src/ai_rpg_world/application/trace/
├── events.py                                  # TraceEventKind.EPISODIC_*
└── recorder.py                                # JsonlTraceRecorder (close-race 対応)

scripts/
├── episodic_chunk_simulation.py              # ドライランシミュレータ
└── run_scenario_experiment.py                 # 実走 + shutdown drain

tests/
├── application/llm/chunk_boundary/test_episodic_chunk_boundary_rules.py
├── application/llm/services/test_episodic_subjective_completion_schedulers.py
├── application/llm/services/test_episodic_trace_emission.py
├── application/llm/test_episodic_chunk_subjective_fields.py
├── application/trace/test_recorder.py
├── integration/test_escape_game_episodic_smoke.py
└── integration/test_escape_game_episodic_recall_harness.py
```

### 関連実験 Issue

| Issue | 内容 |
|---|---|
| #295 | 第20回 第八走 (blocker 発覚) |
| #311 | 第21回 第九走 (主要 4 課題発見) |
| #325 | 第22回 第十走 (chunk 粒度部分達成) |
| #328 | 第23回 第十一走 (shutdown race 解消 + 卒業) |

---

## 11. 改訂履歴

- 2026-06-01: 初版 (第23回実験での卒業判定を踏まえ、現状設計を総括)
- 2026-06-01: PR #330 共通化リファクタを反映 (§9.2 / §10 のファイル位置更新)
- 2026-06-01: PR #331 で survival_island / survival_island_v2 への配線検証 smoke test を追加。`build_episodic_stack` がシナリオ非依存で動くことを実証 (8 件の wire 確認テスト)
