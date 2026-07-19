# Stage 0a — ドメインイベント配信サイトの機械的棚卸し表

> 状態: **完了 (コード変更ゼロ)**。日付: 2026-07-20。
> 親計画: [domain_event_dispatch_refactor_plan.md](./domain_event_dispatch_refactor_plan.md)
> 方法: `publish` / `publish_all` / `get_events` / `clear_events` /
> `add_events_from_aggregate` / `graph.clear_events` を全 grep し、
> code-explorer 3 並列で各サイトを実コード精読して埋めた。推測は明示する。

## スコープ

対象は **spot_graph experiment runtime** のドメインイベント配信のみ。
以下は「第3の経路」として射程外 (別調査):

- SQLite write repo の `event_sink → add_events_from_aggregate` (13 repo)。
  これらは `_register_aggregate` / codec の `clear_events` を含め、実験ランタイム
  (in-memory + PipelineEventPublisher) とは別の配線。
- `UseItemService`。ただし後述 U 行に「両経路併存の構造」だけ記録する
  (spot_graph runtime の LLM ツール `_use_item` とイベント種別が重なるため)。

## dispatch サイト一覧 (20 サイト)

「相」= 親計画の 3 相分類:
**①同期副作用 (即時性 load-bearing)** / **②観測 append + schedule** / **③非同期 post-commit**。
すべて最終的に `PipelineEventPublisher._dispatch` (side handler 同期 → observation) を通るため、
相は「そのイベントに load-bearing な同期 side handler が付くか」で決まる。

### A. tick パイプライン系

| ID | 発行元 file:line (メソッド) | イベント種別 | タイミング | 集約回収 / 生成 | save 順序 | 同期 side handler (load-bearing?) | schedules_turn | 相 | ガード / 破棄 |
|---|---|---|---|---|---|---|---|---|---|
| A1 | `spot_graph_needs_decay_stage_service.py:164` (run) | `PlayerDownedEvent` (飢餓/疲労で HP0) | tick stage #8 (needs_decay) | status を回収 (138/155) → clear (139/156) | 回収→clear、save は repo 側 | `PlayerDownedOutcomeHandler` (outcome 更新 + **grace_timer 登録**) + 条件付 `PlayerDownedStateCollapseEvidenceHandler`。登録 `world_runtime.py:3812-3819` / `4862-4868`。**即時性 load-bearing** | あり | ① | `publisher is not None` |
| A2 | `status_effects_tick_stage_service.py:101` (run) | `PlayerDownedEvent` (継続ダメージで HP0) | tick stage #9 (status_effects) | status を回収 (96) → clear (97) | 同上 | A1 と同一 handler。**load-bearing** | あり | ① | `publisher is not None` |
| A3 | `spot_attack_orchestrator.py:245` (`_flush_player_events`) | `PlayerDownedEvent` (モンスター攻撃で HP0) | tick stage #11 (monster_behavior) | player を回収 (242) → clear (243) | graph は save(227) 後に別経路 | A1 と同一 handler。**load-bearing** | あり | ① | `publisher is not None` (240 no-op) |
| A4 | `world_runtime.py:906` (`_process_graph_events`) | graph 集約の全種別: `EntityEnteredSpotEvent` / `MonsterAppearedAtSpotEvent` / `MonsterLeftSpotEvent` / `MonsterAttackedPlayerInSpotEvent` / `SpotSoundHeardEvent` 等 | **post-tick hook #1 (graph_event_flusher, commit 後)**。speech/interaction からも直接呼ばれる | graph を回収 (902) → clear (903) | commit 後 | `EntityEnteredSpotEvent`→`SpotArrivalEncounterHandler` (登録 3893-3896)。ただし spawn では発火しない (A6 参照) | 種別依存 | ②(一部 side handler 有) | `speech_publisher is None` で回収前に return |
| A5 | `world_runtime.py:3966` (`_on_phase_changed`) | `TimeOfDayChangedEvent` | tick stage #7 (day_night) の phase 変化 callback | その場生成 | save なし | なし | なし | ② | try/except で例外握り (ゲームループ継続) |
| A6 | `world_runtime.py:2875` (`graph.clear_events()`) | `EntityEnteredSpotEvent` / `MonsterAppearedAtSpotEvent` (初回 spawn) | シナリオ起動時 (runtime 構築の前段) | — | save(2876) 直前に破棄 | — | — | — | **意図的破棄**。publisher/appender 未構築のため。代わりに `InMemoryEncounterMemory` へ直接 observe。この非 publish は挙動として load-bearing |

### B. LLM ツール実行系 (`spot_graph_tool_executor.py`)

| ID | 発行元 file:line (メソッド) | イベント種別 | タイミング | 集約回収 / 生成 | save 順序 | 同期 side handler (load-bearing?) | schedules_turn | 相 | ガード / 破棄 |
|---|---|---|---|---|---|---|---|---|---|
| B1 | `:709` (`_use_item`) | `ItemUsedEvent` + `ItemBrokenEvent`(破損時) | LLM ツール `spot_graph_use_item` | item_instance を回収 (706) → clear (707) | **回収→clear→save** (717/721) | 未確認 (推測: なし) | 未確認 | ② | `instance_events and publisher is not None` |
| B2 | `:757` (`_use_item` 腐敗食) | `PlayerDownedEvent` (腐敗食で HP0) | 同 (`is_spoiled` 分岐) | status を回収 (754) → clear (755) | **save(745)→回収→publish** (逆順) | A1 と同一 handler。**load-bearing** | あり | ① | `publisher is not None` + `status_events` の二重 |
| B3 | `:775` (`_use_item` 新鮮) | `ConsumableUsedEvent` | 同 (新鮮分岐) | その場生成 | save 概念なし | `ConsumableEffectHandler` (HP/MP 回復等を適用。登録 `world_runtime.py:3860-3863`)。**load-bearing** | なし | ① | `publisher is not None and consume_effect is not None` |
| B4 | `:886` (`_maybe_register_sync_prepare`) | `SpotPlayerPreparedActionEvent` | LLM ツール `spot_graph_prepare_action` | その場生成 (group ごと) | save なし | 未確認 (推測: なし、演出観測) | なし (デフォルト) | ② | 冒頭 `publisher is None or repo is None: return` |
| B5 | `:1460` (`_tend_to_player`) | `PlayerRevivedEvent` | LLM ツール `spot_graph_tend_to_player` | target を回収 (1453) → clear (1454) | **回収→clear→save** (1455) | `PlayerRevivedOutcomeHandler` (**grace_timer.cancel**。登録相当)。**即時性が load-bearing**: 遅延させると grace 満了で DEAD 確定するレース (コメント明記) | あり | ① | `publisher is not None` + `if events` |

### C. アプリケーションサービス系

| ID | 発行元 file:line (メソッド) | イベント種別 | タイミング | 集約回収 / 生成 | save 順序 | 同期 side handler (load-bearing?) | schedules_turn | 相 | ガード / 破棄 |
|---|---|---|---|---|---|---|---|---|---|
| C1 | `spot_interaction_application_service.py:534` (interact 本体。430 で接触ダメージ status も合流) | `SpotObjectInteractedEvent` + `public_events` (`SpotObjectStateChangedEvent` 等) + `graph_events` + `PlayerDownedEvent`(接触ダメージ) | LLM ツール (object interaction) | status(431→432) と graph(488→489) を回収→clear | **回収→clear→save**、その後 publish_all | `PlayerDownedEvent`→A1 と同一 handler。**load-bearing** | 種別依存 | ①(downed 有時) / ② | `publisher is not None` |
| C2 | `spot_interaction_application_service.py:725` (`_emit_failure_observation`) | `SpotObjectInteractionFailedEvent` | interaction 失敗観測 | その場生成 (715-724) | save なし | なし | — | ② | 冒頭 `publisher is None: return` + dedup throttle |
| C3 | `spot_graph_item_transfer_service.py:_publish_event(532)` ← drop(321)/pickup(395)/give(500) | `PlayerDroppedItemEvent` / `PlayerPickedUpItemEvent` / `PlayerGaveItemEvent` | LLM ツール (item transfer) | その場生成 | **save 後に publish** | なし (推測: 観測配信のみ) | 種別依存 | ② | `publisher is None: return` + try/except 握り |
| C4 | `harvest_command_service.py:289` (finish_harvest 系) | `ResourceHarvestedEvent` | LLM ツール (harvest) | physical_map を回収 (287) | **回収→publish→save(291)** (clear は save 内 `_register_aggregate` に委任) | なし (推測: 観測配信のみ) | 種別依存 | ② | `publisher is not None` + `if events` |
| C5 | `spot_exploration_application_service.py:110` (explore_once) | `SpotExploredEvent` | LLM ツール (explore) | その場生成 (103-109) | save(90) 後に publish (単発 `publish`) | なし | 種別依存 | ② | `publisher is not None` |
| C6 | `conversation_command_service.py:130` (`_start_conversation_impl`) | `ConversationStartedEvent` | LLM ツール (会話開始) | その場生成 | — | 未確認 | 種別依存 | ② | **ガードなし** (publisher 必須注入) |
| C7 | `conversation_command_service.py:283` (`_advance_conversation_impl`) | `ConversationEndedEvent` | LLM ツール (会話終了) | その場生成 | 報酬付与後 | 未確認 | 種別依存 | ② | **ガードなし** (publisher 必須注入) |
| C8 | `consumable_effect_handler.py:89` (`_handle_impl`) | `PlayerHpHealedEvent` 等 (回復系。効果適用の結果 status が積む) | **side handler として** `ConsumableUsedEvent` 受信時 (B3 / U から) | status を回収 (87) → clear (90) | **save(82)→回収→publish→clear** (他と逆順) | 二次発火。さらに handler 有無は未確認 | 種別依存 | ②(二次) | `publisher is not None and hasattr(get_events)` |
| C9 | `player_speech_service.py:107` (`_speak_impl`) | `PlayerSpokeEvent` | LLM ツール (speak) | status を回収 (105) → clear (108) | **メソッド内に save なし** (呼び出し元 save の可能性、推測) | なし (推測) | 種別依存 | ② | **ガードなし** (publisher 必須) + `if events` |

### U. 射程外だが隣接 (`use_item_service.py`, 第3経路)

| ID | 発行元 file:line | 内容 |
|---|---|---|
| U1 | `use_item_service.py:137` | `unit_of_work.add_events_from_aggregate(item)` で `ItemUsedEvent`/`ItemBrokenEvent` を UoW pending へ。**dispatcher 未設定の `InMemoryUnitOfWork()` (`world_runtime.py:3632`) なので `_committed_events` に溜まるだけで observation に橋渡しされない = 実質死に経路** |
| U2 | `use_item_service.py:150` | `publish(ConsumableUsedEvent.create(...))`。B3 と同じく `ConsumableEffectHandler` を同期起動する**唯一の実効経路**。集約イベントとは無関係にその場生成 |

→ 同じ「アイテム使用」1 回で「集約イベント回収 (U1, 死に)」と「その場生成 publish (U2, 実効)」が併存。
CLAUDE.md #65-73 の静かな失敗パターンと同型。**射程外だが、B1/B3 と種別が重なるので一元化時は必ず突き合わせる**。

## 構造的な発見 (Stage 1 以降の設計判断に直結)

1. **相 ① (即時性 load-bearing な同期 side handler) は 6 サイトに集中**: A1/A2/A3 (downed→grace 登録)、B2 (腐敗食 downed)、C1 (接触 downed)、B5 (revive→grace cancel)、B3/U2 (ConsumableUsed→効果適用)。
   **ここを 1 tick 遅延させると壊れる**。commit 後一括 dispatch に単純移行できない核心。
2. **回収→clear→save の順序が 3 派に分裂**:
   - 「回収→clear→save」(A1/A2/A3, B1, B5, C1): 正順。#746 で正とした形。
   - 「save→回収→publish」(B2, C8): 逆順。B2 は publisher ガード内なので canonical 汚染は #746 で塞いだが、順序理由がコメントに乏しい。
   - 「回収→publish→save (clear は repo 委任)」(C4 harvest): `_register_aggregate` の drain を先取りする独自形。
3. **その場生成イベントが多数** (A5, B3, B4, C2, C3, C5, C6, C7, U2): 集約に積まれず `.create()` して即 publish。
   → repo-tracking (UoW 収集) では**絶対に拾えない**。codex MEDIUM の「明示的 `DomainEventCollector` が要る」の実証。
4. **publisher ガードが二系統**: Optional 注入 (is not None 必須) vs 必須注入 (C6/C7/C9 はガードなし)。一元化時に契約を揃える論点。
5. **意図的非 publish が 2 種**: A6 (spawn を encounter_memory 直 observe)、U1 (UoW pending 死に経路)。前者は挙動保持必須、後者は Stage 5 で削除候補。
6. **graph 系は 2 系統**: 集約 (`SpotGraphAggregate`) に積む → save → post-tick の A4 で flush。player 系の即時 publish とタイミングが違う。

## Stage 0b で固定すべき順序不変条件 (この棚卸しから確定)

- **同 tick 内**: needs_decay(A1)/status_effects(A2)/attack(A3)/腐敗食(B2)/接触(C1) で downed → **death_grace_stage (#14) より前に grace_timer が登録済み**。
- **revive (B5)**: publish の同期内で **grace_timer が cancel 済み** (次 tick の death_grace で DEAD にならない)。
- **ConsumableUsed (B3/U2)**: publish の同期内で HP/MP 等が反映済み (C8 が走り終える)。
- **post-tick hook 順序**: graph_event_flusher(A4) → heartbeat → llm_turn_trigger。
- **初回 spawn (A6)**: `EntityEnteredSpotEvent` は publisher 経由で **配信されない** (encounter_memory 直行のみ)。
- **tick stage 順序**: travel → scenario_event → reactive_object → reactive_binding → sync_action → environment → day_night → needs_decay → status_effects → monster_spawn → monster_behavior → food_spoilage → outcome_resolution → death_grace。

## 移行チェックリスト (Stage 3 で 1 行ずつ消す)

相 ② の単純サイト (先に移行して安全):
B1, B4, C2, C3, C4, C5, C6, C7, C9, A4(の非 side-handler 分)。

相 ① の順序依存サイト (最後、Stage 0b で厳重ガード):
A1, A2, A3, B2, B3, B5, C1, C8, U2。

意図的挙動 (触らない/別 PR):
A5(例外握り), A6(spawn 非 publish), U1(死に経路除去は Stage 5)。
