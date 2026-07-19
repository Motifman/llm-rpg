# ドメインイベント配信の一元化リファクタリング計画 (改訂版 / codex 敵対的レビュー反映)

> 状態: **改訂ドラフト**。codex レビュー (2026-07-19) の CRITICAL/HIGH/MEDIUM/LOW を反映。

## スコープ (明示・重要)

本計画の対象は **spot_graph experiment runtime のドメインイベント配信**に限定する。
以下は別調査 / 別計画に切り出す (今回の射程外):

- SQLite write repo の `event_sink → add_events_from_aggregate` 経路
  (例 `sqlite_player_status_write_repository.py:67`)
- `UseItemService` が repo とは別に `unit_of_work.add_events_from_aggregate(item)` を
  直接呼ぶ経路 (`use_item_service.py:136-150`)

これらは spot_graph 実験ランタイムとは別のイベント配線を持つ「第3の経路」であり、
一緒に触ると爆発する。scope を絞る。

## 背景と問題 (現状の実測)

PR #746 で「in-memory repo が未 publish のドメインイベントを持ち越す」規約を repo 境界
(`InMemoryRepositoryBase._clone`) で drain して再放出バグ (実 run v3coop_stagnation_003 で
1 個の PlayerRevivedEvent が 46 tick / 141 観測に増幅) を**止血**した。根の問題は残る。

### dispatch は本質的に「3 相」ある (codex CRITICAL/HIGH 反映)

現状の配信は 3 種類の意味論が混在しており、一括 commit-then-dispatch はこれを壊す:

1. **同期ドメイン副作用 (sync side-effect) — 即時性が load-bearing**
   - needs_decay が HP0 で `PlayerDownedEvent` を publish → `PlayerDownedOutcomeHandler`
     が**同じ stage 内で即走る** (`spot_graph_needs_decay_stage_service.py:133-164`,
     `pipeline_event_publisher.py:86-105`, handler 登録 `world_runtime.py:3812-3819`)。
     その後 death_grace_stage が走る。commit 後 dispatch に寄せると
     death_grace が side handler より先に走り grace_timer/outcome_registry が 1 tick 遅れる。
   - revive も同型: `tend_to_player` の「revive → publish → grace cancel」の即時性が
     load-bearing (`spot_graph_tool_executor.py:1439-1460`)。
2. **観測 append + schedule — 後置してよい**
   - observation pipeline への配信、schedules_turn。
3. **非同期 post-commit handler**
   - `TransactionalScope` が commit 後に `publish_async_events` を呼ぶ
     (`transactional_scope.py:54-60`)。

→ 一元化は「commit 後に全部 dispatch」ではなく、**3 相を分解し、同期相の即時性を
tick stage 間の必要箇所で保つ契約**にしなければならない。

### 2 つの publisher は同名 port でも意味論が別物 (codex HIGH)
- `EventPublisher` port は `publish / publish_all / publish_async_events` しか要求しない
  (`domain/common/event_publisher.py:10-35`)。
- 本番 `PipelineEventPublisher`: transaction 外 publish 可 / `is_synchronous` 無視 /
  side handler を同期実行 / handler 例外を握って observation 継続
  (`pipeline_event_publisher.py:55-105`)。
- テスト `InMemoryEventPublisherWithUow`: publish は transaction 内限定 / sync・async 分離 /
  `publish_async_events` は post-commit (`in_memory_event_publisher_with_uow.py:50-137`)。
- → 単純に port を寄せると transaction 外の `_process_graph_events` / day_night callback が
  壊れる。**port 統一より先に 3 相の契約表**を作る。

### 本番で意図的に publish されない load-bearing なイベント (codex MEDIUM)
- 初回 spawn の `EntityEnteredSpotEvent` は `graph.clear_events()` で破棄され、encounter は
  直接 observe する設計 (`world_runtime.py:2744-2748,2875,3867-3874`)。
- → 「積まれたイベントは全部 dispatch」に寄せると初期 spawn が観測に流れ始め挙動が変わる。
  Stage 0 で「非 publish」を不変条件として固定する。

### 収集は repo-tracking では足りない (codex MEDIUM)
- repo の tracking は save 系からしか呼ばれない (`in_memory_repository_base.py:76-91`)。
- find→mutate→save しない経路、callback が直接作る非集約イベント
  (`TimeOfDayChangedEvent` 等)、`_process_graph_events` の直接回収
  (`world_runtime.py:902-906`) は拾えない。
- → **明示的 `DomainEventCollector` を operation context に注入**し、集約 event も手作り
  event も add する方式を第一候補とする (repo-UoW 結線は second)。

### dedup は event_id ベースではない (codex LOW)
- `InMemoryEventPublisherWithUow` の dedup はオブジェクト同一性/等価性ベース
  (`in_memory_event_publisher_with_uow.py:95-133`)、`PipelineEventPublisher` に dedup 無し。
- → 「**event_id ベースの operation-local dedup を新設**」と明記。

## 目標 (ベストプラクティスの姿)
- 集約はイベントを raise するだけ。呼び出し側は `get_events`/`clear_events` を触らない。
- dispatch は 3 相 (sync side-effect / observation / async post-commit) の契約に沿って、
  **同期相の即時性を保ったまま**単一の収集境界を通る。
- 本番とテストが同一の配信契約を通る。
- event_id ベースの operation-local 冪等 dispatch。

## 段階計画 (codex 提案の安全順を採用)

### Stage 0a — 機械的棚卸し表 (何も変えない・最初にやる) ✅ 完了 (2026-07-20)
- 成果物: [domain_event_dispatch_stage0a_inventory.md](./domain_event_dispatch_stage0a_inventory.md)
- `publish` / `publish_all` / `get_events` / `clear_events` /
  `add_events_from_aggregate` / `graph.clear_events` を spot_graph runtime scope で全列挙し、
  「イベント種別 × 発行元 file:line × タイミング × 集約回収/生成 × save 順序 ×
  同期 side handler (load-bearing 判定) × schedules_turn × 相 × ガード/破棄」の
  **20 サイト表**にした。codex 指摘の数え落とし (harvest / item_transfer / exploration /
  conversation / tool_executor 内の複数経路 / spawn 破棄) を全数収録。
- **確定した要点**: 相 ① (即時性 load-bearing) は 6 サイトに集中 (A1/A2/A3/B2/C1 downed→grace,
  B5 revive→cancel, B3/U2 ConsumableUsed→効果適用)。その場生成イベントが 9 サイトあり
  repo-tracking では拾えない (→ 明示 Collector 必須)。回収→clear→save の順序が 3 派に分裂。
- これが Stage 3 の移行チェックリスト (相 ② 先行 / 相 ① 最後) になる。

### Stage 0b — 特性化テスト (順序不変条件を固定) ✅ 完了 (2026-07-20)
- 成果物 (テスト追加のみ、プロダクトコード無変更、14 件 GREEN):
  - `tests/application/world_graph/test_spot_graph_simulation_stage_order.py`
    — 14 tick stage + post-tick hook (graph_event_flusher → heartbeat → llm_turn_trigger)
    の実行順序を厳密等価で固定。needs_decay→status_effects、outcome_resolution→death_grace
    の load-bearing ペアも個別に固定。
  - `tests/application/world_runtime/test_pipeline_event_publisher_dispatch_contract.py`
    — `_dispatch` の契約を固定: side handler は observation より先に同期実行 / 登録順 /
    型フィルタ / 例外は log して継続 (後続と observation を止めない) / 実 handler 配線で
    downed→grace 登録・revive→grace 解除が publish から戻った時点で成立。
- カバレッジの由来:
  - **downed→grace 登録 / revive→grace 解除**: 上記 dispatch 契約テスト (即時性の機構) +
    既存の stage→publisher テスト (MagicMock) + handler 単体テストの合成で固定。
  - **ConsumableUsed→効果適用**: 既存 handler 単体テスト (同期反映を厚く担保) +
    dispatch 契約テスト (任意 side handler が observation 前に同期実行) の合成で固定。
  - **post hook 順序 / tick stage 順序**: stage_order テストで直接固定。
- **保留 (意図的)**: 初期 spawn `EntityEnteredSpotEvent` の **非 publish は否定的
  アサーションを今は書かない**。現状 `graph.clear_events()` (`world_runtime.py:2875`) が
  publisher 構築より前に events を破棄するため物理的に publisher へ届かず、既存
  `test_encounter_memory_integration.py` の spawn→encounter_memory 記録テストで肯定側は
  カバー済み。否定側は重い実 runtime 構築が要るため、Stage 2 で `DomainEventCollector`
  spy を入れる段で安価に書ける。そこで追加する。

### Stage 1 — dispatch 意味論の 3 相分解と契約化 (port 統一ではない)
- dispatch を「同期ドメイン副作用 / 観測 append+schedule / 非同期 post-commit」に分解し、
  それぞれの契約 (実行タイミング / 例外方針 / 順序) を明文化・型化。
- 2 publisher の差 (transaction 外可否 / 例外握り) をこの契約の上で吸収する設計にする。

### Stage 2 — 明示的 DomainEventCollector の導入 (1 サービス先行)
- operation context に `DomainEventCollector` を注入。集約 event + 手作り非集約 event を
  add し、オペレーション境界で 3 相契約に沿って dispatch。
- **最初は side handler 順序依存が少ない `item_transfer` から**。Stage 0b で publish 集合と
  順序が完全一致することを確認。needs_decay / status_effects / revive は後回し。

### Stage 3 — emission サイトの手動 drain 撤去
- Stage 0a の棚卸し表を 1 行ずつ消す形で、各サイトを「mutate + save だけ」へ移行。
- 順序依存の重い needs_decay / revive は最後、Stage 0b の順序不変条件で厳重にガード。

### Stage 4 — repo の identity/clone 是正 (優先度中・後回し可)
- deepcopy-everything の `_clone` を identity map + 明示 clone に。#746 の drain 不変条件は維持。

### Stage 5 — 死んだ経路 / 冗長ガードの除去
- テスト専用に分岐していた UoW 収集経路の二重性、#746 の A 冗長ガード等を整理。

## リスク (慎重に扱うべき点)
- **同期 side handler の即時性** (downed→grace, revive→cancel) を絶対に壊さない。Stage 0b が命綱。
- 2 publisher の例外方針差 (Pipeline は握る / InMemory は伝播)。
- 非集約イベント (TimeOfDayChangedEvent 等) と find-no-save 経路の収集漏れ。
- 意図的非 publish イベント (spawn) の挙動維持。
- snapshot / save (Issue #470)、並列ターン (`LLM_TURN_PARALLEL_WORKERS`) 下の一貫性。

## 進め方の原則
- 1 PR = 1 stage (または 1 サービス移行)。200〜400 行目安。
- Stage 0 を回帰網として全段で緑を維持。behavior-preserving を最優先。
- 挙動を変える箇所 (spawn 観測化など) は独立 PR に分け、trace で先に可視化。
