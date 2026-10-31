# 範囲 B: 世界の 1 tick と、エージェントの手番の進め方

調べた版: origin/main `21a33e4c9`。読むだけで、書き換えていない。
パスの略記:

- `WR` = `src/ai_rpg_world/application/world_runtime/world_runtime.py`
- `SIM` = `src/ai_rpg_world/application/world_graph/spot_graph_simulation_application_service.py`
- `TT` = `src/ai_rpg_world/application/llm/services/world_llm_turn/turn_trigger.py`
- `HB` = `src/ai_rpg_world/application/observation/services/heartbeat_observation_emitter.py`
- `RM` = `src/ai_rpg_world/presentation/spot_graph_game/runtime_manager.py`
- `EXP` = `scripts/run_scenario_experiment.py`
- `GPS` = `src/ai_rpg_world/application/world_graph/game_phase_store.py`
- `MCS` = `src/ai_rpg_world/application/world_graph/meeting_command_service.py`
- `PLQ` = `src/ai_rpg_world/application/player/services/player_life_query.py`
- `POR` = `src/ai_rpg_world/domain/player/service/player_outcome_registry.py`

各項目に【確認】(コードで読んだ事実) と【推測】(読んだことからの見立て) を付ける。印の無い記述は【確認】。

---

## 0. 全体の形 (要点)

- 1 回の `WorldRuntime.advance_tick()` が「世界の 1 tick」。中身は `SpotGraphSimulationApplicationService.tick()` で、**時刻を 1 進める → 世界の段 (stage) を固定順で 15 個 → 確定後フック 4 個 (観測の吐き出し → 待ち時間のタイマー → エージェントの手番 → 個人結果の 2 回目の判定)** の順に走る (`SIM:107-196`, `SIM:203-261`)。
- **エージェントの手番は tick の中 (確定後フック) で回る**。手番を回すのは `WorldLlmTurnTrigger.run_scheduled_turns()` で、`pending_player_ids` (その tick までに「起こされた」人の集合) を全部取り出して、1 人 1 回ずつ走らせる (`TT:124-195`)。
- 手番の起こし方は「観測駆動」。観測に `schedules_turn=True` が付いていれば受け手を pending に足す (`ObservationTurnScheduler.maybe_schedule`)。ほかに、移動の到着、待ち時間のタイマー (既定 6 tick)、成功した自分の行動のあと (D1597)、失敗の回し直し (`_RESCHEDULE_ERROR_CODES` と D1595) がある。
- 勝敗・終わりの判定 (`check_game_end`) は、実験の駆動ループが tick ごとに呼ぶ (`EXP:827`)。手番の入口でも呼んで、終わっていれば手番を回さない (`TT:129-136`)。
- 実験の 1 run は `EXP._drive_scenario` (`EXP:509-1000`)。`GameRuntimeManager.create_session` で runtime と LLM の配線を組み、全員を一度 `schedule_turn` してから、`current_tick < max_world_ticks` のあいだ `advance_tick` を回す。

---

## 1. 1 tick の流れ (順番つき)

実験 (`make experiment`) の 1 回の反復を、外側から順に書く。

### 1-A. 駆動ループの 1 反復 (`EXP:753-845`)

| # | 何が起きるか | 変わる状態 | 根拠 |
|---|---|---|---|
| A1 | ループ条件: `runtime.current_tick() < max_world_ticks` かつ `i < max_world_ticks*2` (安全弁) かつ SIGINT が来ていない | — | `EXP:751-753` |
| A2 | trace `TICK_START` (tick = 進める前の値) | trace | `EXP:758` |
| A3 | LLM 呼び出し数のカウンタを捨てる | `runtime._llm_call_count` | `EXP:762-764` |
| A4 | **`runtime.advance_tick()`** (下の 1-B) | 世界のほぼ全部 | `EXP:765` |
| A5 | 全員の現在地を前の反復と比べ、変わった人だけ trace `POSITION_CHANGE` | 駆動側の `prev_spots` | `EXP:767-788` |
| A6 | trace `TICK_END`、進捗 (LLM 呼び出し数、移動中の人数) | trace / progress.jsonl | `EXP:789-815` |
| A7 | LLM の連続失敗監視が「恒久障害」と言えば `LLM_ABORTED` で抜ける | `outcome` | `EXP:816-826` |
| A8 | `runtime.check_game_end()` が終了なら trace `TEAM_RESULT` を残して抜ける | `outcome`, `end_reason` | `EXP:827-845` |

ループの前に: 全員を `schedule_turn` する (`EXP:702-703`)。ループのあとに: `write_episodes_on_leaving` (LLM が使えなかった run は理由だけ残す) → `shutdown_async_events` → snapshot の保存 (`EXP:865-960`)。

### 1-B. `WorldRuntime.advance_tick()` (`WR:824-849`)

| # | 何が起きるか | 変わる状態 | 根拠 |
|---|---|---|---|
| B1 | `_simulation_service.tick()` (下の 1-C)。成否にかかわらず `finally` で `self._tick` を時刻の正本に合わせる | `WorldRuntime._tick` | `WR:825-830` |
| B2 | 腐敗の観測をためている日 (`_pending_spoiled_day`) と今日が違えば、ためた分を 1 件の観測にまとめて全員に配る | `_pending_spoiled`, `_pending_spoiled_day`、全員の観測 | `WR:834-839`, `WR:3474-3522` |
| B3 | 会議が沈黙上限か tick 上限に達していれば、票を集計して会議を閉じる | `GamePhaseStore`、outcome (追放)、倒れた体の記録 | `WR:840`, `WR:983-1000` → `MCS:173-186` |
| B4 | trace `WORLD_SPATIAL_METRICS` (区画ごとの在室数、各人の累積移動 tick) | trace | `WR:841`, `WR:948-981` |
| B5 | 公開 SNS の通知の送り直し (公開 SNS は今は起動時に拒否されるので実質動かない) | SNS | `WR:842-848`, `WR:4100-4106` |

【確認】B1 が例外で抜けると B2〜B5 は走らない (`try/finally` は `_tick` の同期だけ)。

### 1-C. `SpotGraphSimulationApplicationService._tick_impl` (`SIM:107-196`)

まず時刻を 1 進め、戻さない (`SIM:112`。途中の段が失敗しても巻き戻して同じ tick をやり直すと二重適用になるため、とコメントにある)。その後、宣言のある段だけを次の順で走らせる。各段は `WorldTickFailureIsolator.unit(stage=名前)` に包まれる (`SIM:198-201`)。

| 順 | 段 (stage) | 起きること | 変わる状態 | 置き場所 |
|---|---|---|---|---|
| 1 | `travel` | 移動中の人を 1 区間進める。倒れた・退場した人 (幽霊は除く) は予約を取り消す。到着したら到着の観察者を呼ぶ (到着の履歴、LLM の手番を積む)。区間が閉じていたら取りやめ、本人に観測 | `PlayerStatus.spot_navigation_state`、グラフ上の位置、累積移動 tick | `spot_graph_travel_stage_service.py:105-152` |
| 2 | `scenario_event` | シナリオの出来事を条件で評価して発火 (効果の中身は範囲外) | world flags、物、在庫、進捗 | `SpotGraphScenarioEventStageService` (`WR:5335`) |
| 3 | `reactive_object_state` | 条件から物の状態を決め直す (通路より先: 同 tick の通路判定に反映するため) | 物の状態 | `SIM:117-127` |
| 4 | `reactive_binding` | 条件から通路の開閉を決め直す | 接続の状態 | `SIM:128-131` |
| 5 | `sync_action_resolver` | 同期操作の組の成立 / 時間切れを判定し効果を当てる | flags 等 | `SIM:132-137` |
| 6 | `environment` | `tick % update_interval_ticks == 0` のときだけ天候を 1 段遷移させ、`SpotGraphWeatherChangedEvent` を確定後に配る | `weather_holder["state"]`、天候の乱数 | `spot_graph_environment_stage_service.py:40-55` |
| 7 | `day_night` | tick から時刻帯を計算し、帯が変わったときだけ event | 昼夜の現在値 | `spot_graph_day_night_stage_service.py:57-87` |
| 8 | `needs_decay` | 行動できる人の空腹・疲労を進め、限界なら飢餓ダメージ | `PlayerStatus.needs`, HP (→ 倒れる event) | `spot_graph_needs_decay_stage_service.py:73-106` |
| 9 | `status_effects` | 状態異常の継続効果と期限切れ | `PlayerStatus.active_effects`, HP | `status_effects_tick_stage_service.py` |
| 10 | `monster_spawn` | 条件付きのモンスターの出現 / 退去 | モンスター、グラフ | `SIM:153-158` |
| 11 | `monster_behavior` | モンスターの攻撃・徘徊 | HP、位置 | `SIM:159-163` |
| 12 | `food_spoilage` | 腐る物の経過を見て `spoiled` を立てる (観測は B2 で日ごとにまとめる) | 物の state | `food_spoilage_stage_service.py:90-` |
| 13 | `trade_offer_expiry` | 期限切れの取引提案を片付ける | 提案の store | `SIM:172-178` |
| 14 | `market_order_expiry` | 期限切れの板の注文を片付ける | 板の store | `SIM:179-183` |
| 15 | `player_outcome_rule` (1 回目, `evaluation_point=world_stage`) | 個人結果の規則 (救助・取り残し等) を判定 | outcome、規則の発火済み | `SIM:184-188` |
| 16 | `death_grace` | 倒れてから猶予 tick を過ぎた人を `DEAD` に確定し、退場位置を置く | outcome、猶予タイマー、退場位置 | `player_death_grace_tick_stage.py:113-200` |

### 1-D. 確定後フック (`SIM:203-261`)

順番は固定。どれかが失敗しても残りは走り、最後にまとめて `SpotGraphPostTickHookFailedException` を投げる (isolate では isolator が飲むので通常は投げない)。

| 順 | フック | 起きること | 根拠 |
|---|---|---|---|
| H1 | `graph_event_flusher` | 段のなかでグラフに積まれた event を取り出して観測パイプラインへ流す (`_process_graph_events`)。続けて遠景の手がかり (distant cue) の false→true を検出して見える人へ配る | `WR:5594-5597`, `WR:1771-1797`, `WR:3093-3165` |
| H2 | `heartbeat_emitter` | 待ち時間のタイマー。最後の活動から `interval_ticks` (既定 6) 経った人に「周囲に大きな変化はない」観測 (`schedules_turn=True`) を入れる。移動中の人は飛ばす | `HB:97-165` |
| H3 | `llm_turn_trigger` | **エージェントの手番**。下の 1-E | `TT:124-195` |
| H4 | `player_outcome_rule` (2 回目, `evaluation_point=after_turns`) | 手番の中で立ったフラグを、その tick のうちに判定する (D1618) | `SIM:233-237` |

H1 を H2 より前に置くのは、段で出た観測の `schedules_turn` を手番より先に pending へ積むため (`SIM:205-212`)。

### 1-E. 手番の回し方 `WorldLlmTurnTrigger.run_scheduled_turns` (`TT:124-195`)

| # | 何が起きるか | 根拠 |
|---|---|---|
| E1 | `check_game_end()` が終了なら pending と自己連鎖の連続数を空にして何もしない | `TT:129-139` |
| E2 | `to_run = list(pending)`、pending を空にする。以後に積まれた分は次の tick に回る | `TT:141-142` |
| E3 | 行動できない人を外す: 結果が確定 (幽霊は例外) / 倒れている / 移動中 | `TT:146`, `TT:379-400`, `PLQ:72-99` |
| E4 | `LLM_TURN_PARALLEL_WORKERS <= 1` か 1 人だけなら、1 人ずつ Phase A → Phase B を続けて走らせる | `TT:150-159` |
| E5 | それ以外は Phase A (非同期結果の反映 → プロンプト組み立て = 観測の取り出し → LLM 呼び出し) を全員ぶんスレッドで並べ、そのあと Phase B (世界の変更) を `to_run` の順に直列で走らせる | `TT:161-195`, `wiring.py:281-288` |
| E6 | Phase B の入口で Being の記憶のターン数を 1 進め (`advance_memory_turn`)、実行の手番数 (`_execution_turns`) を数え、ツールを実行し、出口で Being の短期記憶のターンを閉じる (`end_being_turn`) | `phase_b.py:89-126` |
| E7 | 結果の会計 (`_account_result`): 自己連鎖の連続数、呼び出し失敗の回し直し、成功した自分の行動のあとの回し直し、待ち時間のタイマーの起点を今にする、欲求と HP の「前回値」を保存 | `TT:225-270` |

### 1-F. 流れの図

```
EXP 反復
 ├ TICK_START
 ├ advance_tick ─┬ SIM.tick
 │               │   ├ time += 1  (戻さない)
 │               │   ├ 段 1..16 (travel → … → player_outcome_rule → death_grace)
 │               │   └ 確定後フック: flush観測+遠景 → 待ち時間タイマー → 手番(A並列/B直列) → 個人結果(2回目)
 │               ├ _tick 同期 (finally)
 │               ├ 腐敗の日まとめ配信 (日が変わったら)
 │               ├ 会議の打ち切り判定
 │               └ 空間指標の trace
 ├ POSITION_CHANGE / TICK_END / progress
 ├ LLM 恒久障害なら打ち切り
 └ check_game_end → 終了なら TEAM_RESULT
```

---

## 2. 振る舞いの一覧

### 2-1. 時間で進むもの

| 振る舞い | きっかけ | 起きること | 変わる状態 | 置き場所 |
|---|---|---|---|---|
| 時刻を進める | tick の先頭 | `WorldTick` を 1 進める。負の量は例外 | `InMemoryGameTimeProvider._current_tick` | `SIM:112`, `in_memory_game_time_provider.py:14-18` |
| 時刻の表示 | 観測・行動記録・プロンプト | 昼夜があれば `ticks_per_day` で 24 時間を割って `Day N h:mm`、無ければ 5 分/tick | — (計算のみ) | `WR:3397-3427`, `WR:442-454` |
| 天候 | `tick % update_interval_ticks == 0` | マルコフ遷移で次の天候。宣言で `announce_changes` なら全員に観測 (`schedules_turn=True`) | `weather_holder["state"]`、天候の乱数 | `spot_graph_environment_stage_service.py:40-91`, `WR:6471-6478`, `WR:3524-3539` |
| 昼夜 | 毎 tick | 時刻帯を計算、帯が変わったときだけ event。宣言で `announce_changes` なら `TimeOfDayChangedEvent` を観測パイプラインへ | 昼夜の現在値 | `spot_graph_day_night_stage_service.py:57-87`, `WR:6489-6520` |
| 欲求の進行 | 毎 tick | 行動できる人だけ空腹・疲労を進め、空腹が限界なら毎 tick 飢餓ダメージ。率はシナリオの `needs` から | `PlayerStatus.needs`, HP | `spot_graph_needs_decay_stage_service.py:89-106`, `WR:5390-5411` |
| 状態異常 | 毎 tick | 継続効果と期限切れ | `active_effects`, HP | `StatusEffectsTickStageService` |
| 腐敗 | 毎 tick | 初めて見た tick を `acquired_at_tick` に書き、閾値を過ぎたら `spoiled` | 物の state | `food_spoilage_stage_service.py` |
| 腐敗の知らせ | 腐った event (確定後) / 日の変わり目 | その日の分をためて、日が変わったら 1 件「今日は◯◯が N 個腐った」を全員に (`schedules_turn=False`) | `_pending_spoiled`, `_pending_spoiled_day` | `WR:6300-6310`, `WR:3429-3522`, `WR:834-839` |
| 死亡の猶予 | 倒れた event (commit 前) で登録、毎 tick 判定 | 猶予 tick (既定 30、シナリオで 0 も可) を過ぎた倒れた人を `DEAD`。scope の中でまだ倒れているかを確かめ直す | outcome、猶予タイマー、退場位置 | `player_downed_outcome_handler.py:59-82`, `player_death_grace_tick_stage.py:113-200` |
| 取引・板の期限切れ | 毎 tick | 期限切れを片付ける | 提案 / 注文 | `SIM:172-183` |
| 遠景の手がかり | 確定後フック H1 | 物の状態から手がかりの有無を出し、false→true のときだけ見える人へ配る。初回は基準として記録するだけ | `_distant_cue_states` | `WR:3093-3165` |
| 会議の打ち切り | `advance_tick` の後段 | 沈黙上限 → tick 上限の順に見て、当たれば票を集計して閉じる | `GamePhaseStore` 等 | `WR:983-1000`, `GPS:185-198` |

### 2-2. 手番

| 振る舞い | きっかけ | 起きること | 変わる状態 | 置き場所 |
|---|---|---|---|---|
| 起こす (外から) | `schedules_turn=True` の観測、到着、待ち時間のタイマー、観戦者からの声 (`send_chat_message`) | `pending_player_ids` に足す。自己連鎖の連続数には触らない | `pending_player_ids` | `TT:111-122`, `observation_turn_scheduler.py:26-41`, `RM:475-479`, `RM:782-786` |
| 初回 | run の開始 | 全員を起こす | 同上 | `EXP:702-703` |
| 待ち時間のタイマー | 確定後フック H2 | 最後の活動から N tick (`LLM_IDLE_TIMEOUT_TICKS`、既定 6) 経った人に観測を入れて起こす。初回は基準点を記録するだけ。移動中は飛ばす。手番が走るたびに起点を今に戻す | `HB._last_emitted_tick` | `HB:97-185`, `TT:360-377`, `RM:443-451` |
| 手番を回す | 確定後フック H3 | pending を全部取り出し、行動できる人だけ 1 回ずつ。並列設定なら Phase A 並列 → Phase B 直列 | 世界 (ツールの実行)、観測 buffer の取り出し | `TT:124-195` |
| 行動できるかの判定 | 手番の入口 | 結果確定 → 不可 (幽霊の DEAD は可)、倒れている → 不可、移動中 → 不可。情報が取れなければ「可」に倒す | — | `PLQ:72-99`, `TT:379-415` |
| 自己連鎖 | 結果の `should_reschedule=True` (失敗コードが `_RESCHEDULE_ERROR_CODES`) | 次の tick に回す。連続 5 回で打ち切る (pending は触らない) | `_self_reschedule_streak` | `TT:225-259`, `contracts/dtos.py:14-55` |
| 呼び出し失敗の回し直し (D1595) | 結果の `error_code == LLM_API_FAILED` | 次の tick に回す。同じ人の 3 回連続で回さない。毎回 trace `llm_failure_retry` | `_llm_failure_streak` | `TT:272-295` |
| 自分の行動のあと (D1597) | 成功し、`was_no_op` でない | 次の tick に回す。`wait` (`rests_until_woken`)、行動不能、移動中は回さない。trace `own_action_follow_up` | `pending_player_ids` | `TT:297-323` |
| 移動中の中断 | Phase B で移動中に「重い」ツール | 移動を取りやめてから実行。ツールが失敗したら移動を元に戻す | `spot_navigation_state` | `phase_b.py:230-283` |
| 記憶のターン | Phase B の入口と出口 | Being のターン数を進め、短期記憶のターンを閉じる (範囲が埋まった等の event はここから) | `MemoryTurnClock`、短期記憶 | `WR:1914-1938`, `phase_b.py:103-126` |
| 欲求の前回値 | 手番のあと | 次のプロンプトで差分を出すために、いまの欲求と HP を保存 | `PlayerStatus` の delta 基準 | `TT:339-358` |
| 手番の外から回す入口 | `POST /api/sessions/{id}/llm-turns` | `run_scheduled_turns()` を tick の外で直接呼ぶ。個人結果の 2 回目は通らない (D1618 の「残っている穴」) | — | `RM:582-590` |

### 2-3. 勝敗・終わり

| 振る舞い | きっかけ | 起きること | 置き場所 |
|---|---|---|---|
| 世界の終了判定 | 駆動ループ (`EXP:827`)、手番の入口 (`TT:131`)、サーバの tick loop | チームの勝利条件 → `win` → `lose` → `end` の順に評価し、最初に成立したものを返す。チームがあれば勝ちを `end` より先に見る | `WR:3666-3761` |
| 外的停止 | 世界の判定が「続行」のとき | 全員が結果確定済みか倒れているなら `外的停止 END_ON_ALL_DOWN` で終わる。世界の判定が成立した tick では外的停止に置き換えない (design_decisions 43「その後」) | `WR:3543-3561`, `WR:3652-3664` |
| チームの勝敗 | 終了時 | チームごとに勝利条件の成否と理由、個人の outcome を trace `TEAM_RESULT` へ | `WR:3563-3650`, `EXP:829-835` |
| run の終わり方 | 駆動ループ | `TIMEOUT` (既定) / 世界の結果 / `LLM_ABORTED` / `INTERRUPTED` / `LLM_FAILURE` (呼び出しが 1 件以上で成功 0 件) | `EXP:705`, `EXP:816-846`, `EXP:102-132` |
| 個人結果の規則 | 段 15 と確定後フック H4 | 規則の条件が成り立てば対象者に `RESCUED` 等を確定。`once` は 1 回目で発火済み | `player_outcome_rule_stage_service.py:82-201` |
| 結果の知らせ | outcome の変化 (callback) | 全員に観測 (`schedules_turn=True`)。`DEAD` は `death.announce_globally` でなければ配らない。追放は全員に名前つき。それ以外は知らない相手には名前を伏せる | `WR:5838-5900` |

### 2-4. 観測の配送

| 経路 | 使う場面 | 流れ | 置き場所 |
|---|---|---|---|
| パイプライン経由 | ドメインイベント (発話・作用・グラフの event・会議・昼夜) | `PipelineEventPublisher._dispatch`: 受け手の handler を先に同期実行 → `ObservationPipeline.run` で宛先と文面を決める → `ObservationAppender.append` → `ObservationTurnScheduler.maybe_schedule` | `pipeline_event_publisher.py` の `_dispatch` |
| 直接 | 宛先が決まっているもの (天候、腐敗、結果の知らせ、遠景、移動の取りやめ、会議での異常の解決) | `_emit_observation_directly`: appender → scheduler | `WR:1799-1822` |
| 待ち時間のタイマー / 失敗の観測 | 確定後フック、Phase B の失敗 | 専用の emitter が appender と scheduler を直接呼ぶ | `HB:140-165`, `RM:456-464` |
| グラフの event の吐き出し | 確定後フック H1、移動の開始直後 (`do_move`) など | グラフ集約の `get_events()` を取り出して clear し、パイプラインへ。publisher が未設定なら取り出さない | `WR:1771-1797`, `WR:2962` |

`ObservationAppender.append` は、受け手に名前を見せるか伏せるかを選び (`recipient_view`)、buffer に積み、trace `observation` を残し、observer (遭遇の記録など) を呼ぶ。伏せきれないときは `False` を返して積まない (`observation_appender.py:82-126`)。積んだ観測は `UnifiedRecentEventStore` の listener から Being の短期記憶へ写される (`WR:6759-6768`)。

### 2-5. 離れる

「離れる」は 3 つの別の意味で使われている。

| 種類 | きっかけ | 起きること | 置き場所 |
|---|---|---|---|
| 倒れる (盤には居る) | HP 0 の `PlayerDownedEvent` | commit 前に倒れた体の記録と猶予タイマーへ登録。手番・観測・投票の対象から外れる | `WR:6093-6113`, `PLQ:72-121` |
| 死ぬ / 去った主体 (幽霊) | 猶予切れ | `DEAD` に確定。`departed_agents_enabled` の世界では、DEAD の人は「去った主体」として手番を持ち、倒れた場所を退場位置として持つ。生者からは知覚されない | `player_death_grace_tick_stage.py:172-182`, `player_perception_policy.py:36-51`, `WR:3802-3810` |
| 追放 | 会議の集計 | `EJECTED` に確定し、グラフから外す (`unplace_entity`) | `MCS:221-225`, `WR:2477-2516` |
| 救助・取り残し | 個人結果の規則 | `RESCUED` / `STRANDED`。手番は来なくなる。グラフからは外さない【確認: `unplace_entity` の呼び出しは上の 2 か所だけ】 | `POR:60-88` |
| 環境を離れる (run の終わり) | 駆動ループの後 | Being の短期記憶のまだまとめていない分からエピソードを書く。LLM が使えなかった run は書かずに理由を trace へ。snapshot の保存より前 | `EXP:865-867`, `WR:1959-1973` |

---

## 3. 不変条件

列: 規則の文 / どこで守るか / 守り方 / 層 / 分類の見立て (ドメインの規則 = D、シナリオの宣言を確かめているだけ = S、実装の都合 = I)。

### 3-1. 時間

| # | 規則の文 | どこで | 守り方 | 層 | 分類 |
|---|---|---|---|---|---|
| T1 | 世界の時刻は tick の先頭で 1 だけ進み、段が失敗しても戻らない | `SIM:108-112` | 構造 (進めてから段を走らせ、戻す口が無い) | application | D + I (二重適用の回避) |
| T2 | 時刻は負の量で進まない / 負の値に置けない | `in_memory_game_time_provider.py:15-16`, `:32-33` | 例外 (`ValueError`) | infrastructure | I |
| T3 | 「今日」の区切りは、エージェントが見ている時計の 1 日にそろえる | `WR:3467-3472`, `WR:3397-3427`, `WR:442-454` | 構造 (同じ換算を使う) が 3 関数に分かれている | application | D |
| T4 | 天候は `update_interval_ticks` ごとに 1 段だけ変わる | `spot_graph_environment_stage_service.py:41-42` | 黙って飛ばす | application | S |
| T5 | 昼夜は tick の決定論的な関数で、帯が変わったときだけ知らせる | `spot_graph_day_night_stage_service.py:78-87` | 構造 | application (計算は domain の `DayNightCycleDef`) | D |
| T6 | 段の順番は固定: 物の状態 → 通路、出来事・物の状態 → 結び付け、同期操作は反映の後、天候 → 昼夜、欲求 → 状態異常 → モンスター出現 → 行動、期限切れはその tick の変化の後、個人結果 → 死亡の猶予 | `SIM:113-194` | コードの並び。試験 `tests/application/world_graph/test_spot_graph_simulation_stage_order.py` | application | D (因果の順) |
| T7 | 段で出た event は、手番より前に観測へ流す | `SIM:217-232` | フックの並び | application | I (観測駆動を成り立たせる) |

### 3-2. 手番

| # | 規則の文 | どこで | 守り方 | 層 | 分類 |
|---|---|---|---|---|---|
| P1 | 1 tick の中で、同じ人の手番は高々 1 回 | `TT:141-142` (取り出して空にしてから回す。手番中に積まれた分は次の tick) | 構造 | application | D【推測: 明文の規則ではなく形から出る性質。`RM:582-590` の入口を tick の中で呼べば崩れる】 |
| P2 | 結果が確定した人は手番を持たない。ただし去った主体が有効な世界の DEAD は持つ | `PLQ:72-86` | 黙って外す | application | D |
| P3 | 倒れている人は手番を持たない | `PLQ:87-99` (`status.can_act()`) | 黙って外す | application (判定本体は domain の `PlayerStatusAggregate.can_act`) | D |
| P4 | 移動中の人は手番を持たない。着いたら起こす | `TT:400`, `TT:311-312`, `HB:128-134`, `RM:475-479` | 黙って外す (3 か所で重ねて守る) | application / presentation | D |
| P5 | 行動できるかの情報が取れないときは、手番を回す側に倒す | `PLQ:78-98`, `TT:406-415` | 黙って補う (fail_fast では止める。D1558-2) | application | I |
| P6 | 終了した世界では手番を回さない | `TT:129-136` | 黙って pending を捨てる | application | D |
| P7 | 自分で失敗を回し直す連鎖は 5 回まで | `TT:104`, `TT:246-255` | 黙って打ち切る | application | I (LLM のループ止め) |
| P8 | 同じ人の呼び出し失敗は 3 回続いたら回し直さない | `TT:31`, `TT:281-287` | 黙って打ち切り、trace に残す | application | I |
| P9 | 成功した自分の行動のあとは次の tick に手番が来る。`wait` と移動中と行動不能は除く | `TT:297-323` | 構造 | application | D 寄り (エージェントの生き方の規則。D1597) |
| P10 | 何も起きない人も、N tick (既定 6) 以内に一度は起こされる。手番が走るたびに数え直す | `HB:178-205`, `TT:266` | 構造。`interval_ticks < 1` は例外 | application | D 寄り (design_decisions 7) |
| P11 | 待ち時間のタイマーは起動直後に全員を起こさない (初回は基準点だけ) | `HB:179-184` | 構造 | application | I |
| P12 | 世界の変更 (Phase B) は直列で、`to_run` の順に適用する | `TT:187-195` | 構造 | application | I (決定性) |
| P13 | 移動の中断は、新しい行動が成功したときだけ確定する | `phase_b.py:272-283` | 失敗したら移動を元に戻す | application | D |
| P14 | Phase B は Being の記憶のターンを 1 回進め、1 回閉じる | `phase_b.py:103-126` | 構造 (例外で途中で抜けると閉じない。D1558 に記載) | application | D (Being 側) |
| P15 | 待ち時間のタイマーは手番の前に走る | `SIM:217-232` | フックの並び | application | I |

### 3-3. 生死・結果

| # | 規則の文 | どこで | 守り方 | 層 | 分類 |
|---|---|---|---|---|---|
| O1 | 個人の結果は UNRESOLVED から 1 回だけ確定し、上書きしない | `POR:60-88` | 黙って補う (`False` を返して何もしない) | domain (ただし「サービス」の名で可変の写像) | D |
| O2 | UNRESOLVED への遷移は無いものとする | `POR:79-80` | 黙って無視 | domain | D |
| O3 | 結果の置き換え (snapshot 復元) は同じ人の集合でだけ | `POR:126-` | 例外 (`PlayerOutcomeRegistryValidationException`) | domain | I |
| O4 | 同じ tick なら救助が死亡に勝つ | 段の順 `SIM:184-194` + O1 | 順序と冪等 | application | D |
| O5 | 手番の中で立ったフラグは、その tick のうちに、そのときの位置で結果を判定する | `SIM:233-237` (D1618) | フックで 2 回目を走らせる | application | D |
| O6 | 猶予切れの判定は、確定直前にもう一度「まだ倒れているか」を確かめる。生きていれば猶予の記録を消す | `player_death_grace_tick_stage.py:156-170` | 黙って修復 | application | D |
| O7 | 猶予は 0 以上の整数 | `player_death_grace_tick_stage.py:81-82`, `parse_world.py:280-283` | 例外 | application / infrastructure | S |
| O8 | 猶予 0 の世界では手当て (`tend_to_player`) を出さない | `validate_features.py:122-123` | 例外 (読み込み時) | infrastructure | S |
| O9 | 倒れた・退場した人の移動予約は消化せずに取り消す (幽霊は除く) | `spot_graph_travel_stage_service.py:114-129` | 黙って取り消す | application | D |
| O10 | 行動できない人の欲求は進めない | `spot_graph_needs_decay_stage_service.py:91-92` | 黙って飛ばす | application | D |
| O11 | 生者は去った主体を知覚しない (逆は可) | `player_perception_policy.py:44-51` | 構造 | application | D |
| O12 | 退場 (`is_eliminated`) は DEAD と EJECTED だけ。救助・取り残しは退場ではない | `player_outcome_enum.py:38-51` | 構造 | domain | D |
| O13 | 追放された人はグラフから外す。殺された人の体は残す | `MCS:221-225`, `WR:2477-2516` | 構造 (外せなければ warning のみ: `WR:2507-2515`) | application | D |
| O14 | DEAD は `death.announce_globally` のときだけ全員に知らせる。追放は必ず全員に知らせる | `WR:5885-5899` | 黙って配らない | application (工場の中の閉包) | S + D |

### 3-4. 会議・フェーズ

| # | 規則の文 | どこで | 守り方 | 層 | 分類 |
|---|---|---|---|---|---|
| M1 | フェーズは常にちょうど 1 つ (自由時間 / 会議) | `GPS:114`, `GPS:333-352` | 構造 | application | D |
| M2 | 会議中に会議を始められない / 会議外で終えられない | `GPS:230-233`, `GPS:250-253` | 例外 (`GamePhaseTransitionException`、domain の例外) | application | D |
| M3 | 会議を始めるたびに票を空にする | `GPS:236` | 構造 | application | D |
| M4 | 会議の打ち切りは沈黙上限を tick 上限より先に見る | `GPS:185-198` | 構造 | application | D |
| M5 | 打ち切りでも、投じられた票は集計する | `WR:983-1000` → `MCS:173-186` | 構造 | application | D |
| M6 | 会議中の発言は沈黙の起点を進める | `WR:1141-1148` | 構造 | application | D |
| M7 | 緊急招集は「会議中でない・止める物が無い・ボタンが残っている・クールダウン外・盤上にいる」ときだけ | `MCS:304-343` 付近 | 失敗の結果 DTO | application | D |
| M8 | クールダウンの起点は会議の終わり | `GPS:200-217` | 構造 | application | D |
| M9 | 投票は会議中だけ、1 人 1 回 | `MCS:136-147` | 失敗の結果 DTO | application | D |
| M10 | 投票の母数は「退場していない・倒れていない人」。全員が投じたらその場で集計して閉じる | `PLQ:116-121`, `MCS:150-166` | 構造 | application | D |
| M11 | 会議が終わると倒れた体の記録をすべて消す | `MCS:264` | 構造 | application | D【推測: 会議のあとは同じ体で再招集できないようにするため。コメントは無い】 |
| M12 | 会議の tick 上限は死亡の猶予より短い | コメント `GPS:57-67`, `player_death_grace_tick_stage.py` の `DEFAULT_GRACE_TICKS` のコメント | 既定値どうしを試験で固定 (`test_meeting_does_not_outlive_rescue.py`)。シナリオで両方を変えたときの突き合わせは見当たらない | application | D (守っていない: 宣言の組み合わせの検査なし) |
| M13 | 会議を開く仕組みを宣言しない世界では、招集・投票を断る | `MCS:127-132` 等, `WR:599-602` | 失敗の結果 DTO / ツールを出さない | application | S |

### 3-5. 終わり

| # | 規則の文 | どこで | 守り方 | 層 | 分類 |
|---|---|---|---|---|---|
| E1 | 終了の評価順: チームの勝ち → win → lose → end | `WR:3707-3760` | 構造 | application | D |
| E2 | チームの勝ちが決まった tick に end も成立しても、勝ったチームを負けにしない | `WR:3707-3723` | 順序 | application | D |
| E3 | 外的停止は世界の判定が続行のときだけ。終了理由の文字列は変えない | `WR:3543-3561` | 順序 | application | I (実験の都合) |
| E4 | 外的停止は「全員が結果確定か倒れている」。人数 0 なら止めない | `WR:3652-3664` | 構造 | application | I |
| E5 | 陣営条件の評価には役割と生死の表を必ず渡す (渡さないと評価器が例外) | `WR:3679-3705` | 必要なときだけ集める。評価器側は例外 | application / domain | D |
| E6 | run は `max_world_ticks` に達すると終わる。1 反復で時刻が進まない不具合に備えて反復は 2 倍まで | `EXP:751-753`, `EXP:847-860` | 黙って止まり warning | scripts | I |
| E7 | 打ち切った run (`LLM_ABORTED`) を `INTERRUPTED` で上書きしない。全滅判定でも上書きしない | `EXP:843-846`, `EXP:120-123` | 構造 | scripts | I |
| E8 | 環境を離れるときのエピソードは snapshot 保存より前に書く | `EXP:865-867` | 順序 | scripts | D (Being 側) |

### 3-6. 観測・失敗の扱い・起動

| # | 規則の文 | どこで | 守り方 | 層 | 分類 |
|---|---|---|---|---|---|
| X1 | 観測は必ず appender → scheduler を通す (trace と起床を漏らさない) | `WR:1771-1822`, `pipeline_event_publisher.py` の `_dispatch` | 構造 (経路を一本化) | application | I |
| X2 | publisher が無いうちはグラフの event を取り出さない (捨てない) | `WR:1789-1792` | 早期 return | application | I |
| X3 | 遠景の手がかりは初回評価では配らず、false→true の境目でだけ配る | `WR:3111-3127` | 構造 | application | D |
| X4 | 1 体の処理の例外は、その 1 体だけ取りやめて trace に残す。trace に残せなければ止める。commit 後の後始末の失敗は止める | `world_tick_failure_isolation.py:69-129` (D1558) | 例外 / 記録 | application | I |
| X5 | 確定済みの処理に続く後処理の失敗は、続けて trace に残す | `world_tick_failure_isolation.py:131-198` (D1558-2) | 記録 | application | I |
| X6 | 到着の観察者は足すだけで置き換えない | `spot_graph_travel_stage_service.py:58-64` | 構造 | application | I |
| X7 | 公開 SNS を有効にしたシナリオは起動しない | `WR:4100-4106` | 例外 (`PublicSnsNotSupportedError`) | application | S + I |
| X8 | `disabled_tools` の名前は実在する | `WR:1526-1547`, `WR:6801` | 例外 | application | S |
| X9 | 全員の Being を用意できなければ起動しない | `WR:6716-6724` | 例外 (`RuntimeError`) | application | D |
| X10 | `WORLD_TICK_FAILURE_POLICY` は `isolate` / `fail_fast` のどちらか | `world_tick_failure_isolation.py:35-40` | 例外 | application | I |

---

## 4. application にあるが、本来ドメインに置く規則 (★印) と、WorldRuntime が持つドメインの状態

### 4-1. ★ ドメインに置くべき規則が application にあるもの

| ★ | 規則 | いまの置き場所 | 見立て |
|---|---|---|---|
| ★1 | 段の順番そのもの (因果の順) | `SIM:107-196` | 「世界の 1 tick で何がどの順に起きるか」は世界の規則。いまは application の調整役のコードの並びとコメントにしか無い |
| ★2 | 手番を持てるか (確定・倒れ・移動中・幽霊の例外) | `PLQ:72-99`, `TT:379-415` | 「行動できる主体か」は主体の状態の問い。判定が PlayerStatus と outcome registry と移動状態にまたがり、application の query に組まれている |
| ★3 | 手番を次の tick に回す規則 (成功のあと / wait / 失敗コード表 / 連続上限) | `TT:225-323`, `contracts/dtos.py:14-55` | 前半 (成功したら次、wait は休む、移動中は着くまで) は「エージェントの時間の過ごし方」。失敗コード表と上限は LLM 都合なので application でよい |
| ★4 | 待ち時間のタイマー (N tick 何も無ければ起こす) | `HB:97-205` | 主体ごとの「最後の活動」の状態を emitter が dict で持つ。主体の状態として持つ候補 |
| ★5 | 会議の規則一式 (排他、沈黙・tick 上限、クールダウン、緊急ボタン回数、報告済みの体、票) | `GPS` 全体 | ファイル冒頭で「application 層に置く world 単位の可変状態」と自称。投げる例外は domain のもの。集約にしてよい形 |
| ★6 | 投票の母数、集計、追放でグラフから外す | `PLQ:116-121`, `MCS:204-253` | 集計 (`resolve_vote`) は domain の関数 (`domain/world_graph/service/vote_tally.py`、`MCS:50`) だが、追放の反映は application のサービスで outcome とグラフを直接書く |
| ★7 | 終了判定の評価順と外的停止 | `WR:3543-3761` | 評価器 (`GameEndConditionEvaluator`) は domain だが、どの順で評価してどれを優先するかは WorldRuntime のメソッド |
| ★8 | 腐敗の知らせを日ごとにまとめる、日の区切り | `WR:3429-3522`, `WR:834-839` | 「今日」の定義が `_time_label` / `_minutes_per_tick` / `_ticks_per_day_or_default` の 3 か所に分かれる |
| ★9 | 時刻の表示と 1 tick の分数 | `WR:3397-3427`, `WR:442-454`、さらに `wiring.py:332-339` と `RM:516`・`RM:757` に `tick % 24` の別のフォールバック | 世界の暦は値オブジェクトにまとめられる。いまは 4 か所 |
| ★10 | 遠景の手がかりの境目検出 | `WR:3093-3165` | 状態 (`_distant_cue_states`) も規則も WorldRuntime に直接ある |
| ★11 | 死亡の猶予 (猶予 tick、確定前の再確認、退場位置を置く) | `player_death_grace_tick_stage.py`, `player_death_grace_timer.py` (application/player/services) | 倒れた → 死ぬの遷移は主体の生死の規則 |
| ★12 | 倒れた・退場した人の移動予約を取り消す | `spot_graph_travel_stage_service.py:114-129` | 「倒れた体は動かない」は移動の規則 |
| ★13 | 会議の開始で、宣言された異常を解く | `WR:2567-2601` と `MCS:557-` の 2 か所 | 【確認】同じ処理が runtime と会議サービスの両方にある。runtime 側 (`begin_meeting`) を呼ぶのは試験だけ (14 ファイル) |
| ★14 | 追放 | `WR:2477-2516` と `MCS:221-225` の 2 か所 | 【確認】runtime の `eject_player` を呼ぶのは試験だけ (9 ファイル)。runtime 側は callback つきで outcome を確定し、サービス側は callback なしで確定して確定後に知らせる。振る舞いが違う |
| ★15 | 結果の知らせを誰に配るか (DEAD の到達範囲、追放は全員、知らない相手には伏せる) | `WR:5838-5900` (工場の中の閉包) | 「誰が何を知るか」は世界の規則 |
| ★16 | 個人結果を 1 回だけ確定 | `POR` | domain にあるが「サービス」の名で可変の dict を持つ。集約の形にしていない |

### 4-2. WorldRuntime が属性として持つドメインの状態

【確認】`WR:485-680` の宣言と `_wire_being_stack` (`WR:1867-1902`) から。

| 属性 | 中身 | snapshot | 見立て |
|---|---|---|---|
| `_tick: int` | 時刻の写し | 載らない (正本は `_time_provider`) | 写しが遅れる (6 章 F1) |
| `_pending_spoiled: dict[int, dict]`, `_pending_spoiled_day` | その日に腐った物 | 載る (`pending_food_spoilage_codec.py`) | ドメインの状態 |
| `_distant_cue_states: dict[str, dict]` | 遠景の手がかりの有無と初期化済みか | 載る (`distant_cue_state_codec.py`) | ドメインの状態 |
| `_game_phase_store: GamePhaseStore` | フェーズ、履歴、緊急ボタン、報告済みの体、票 | 載る (`game_phase_codec.py`) | 集約の候補 |
| `_interaction_cooldown_store` | 対人行為の再使用間隔 | 載る | ドメインの状態 |
| `_current_weather` (= 工場の `weather_holder` dict) | 現在の天候 | 載る (`weather_codec.py`) | `dict` を 1 個の可変の箱として共有している |
| `_world_flag_state: MutableWorldFlagState` | world flags | 載る | application にある可変状態 |
| `_execution_turns: dict[int, int]` | 実行した手番の数 (Phase B が書く) | 公開 SNS の codec の中にだけ載る (`public_sns_codec.py:31,62`) | 置き場所が SNS に寄っている |
| `_meeting_enabled: bool` | 会議を使う世界か | — (シナリオ由来) | シナリオの宣言 |
| `_public_sns_screens` | SNS の画面 | 載る | — |
| `_player_beings`, `_being_environment`, `_aux_being_*` | 誰がどのプレイヤーを動かすか、Being の環境 | `player_beings` は載る | **宣言の無い属性**。`_wire_being_stack` が `hasattr` で遅延に作る |
| `_memory_turn_clock` | Being ごとの記憶のターン数 | Being の snapshot に載る | Being 側の状態 |
| `_cumulative_travel_ticks_by_player`, `_cumulative_meeting_ticks` | 実験の指標 | 載らない (意図どおり) | 観測値。ドメインではない |
| `_llm_call_count`, `_llm_failure_monitor` | LLM の計測と停止判定 | 載らない | 実装 |

WorldRuntime の外 (手番の配線) が持つ状態:

| 持ち主 | 属性 | snapshot |
|---|---|---|
| `WorldLlmTurnTrigger` | `pending_player_ids`, `_self_reschedule_streak`, `_llm_failure_streak` | 載らない。再開時は `EXP:702-703` で全員を起こし直す |
| `HeartbeatObservationEmitter` | `_last_emitted_tick` | 載らない。再開後の最初の tick は基準点の記録だけ |
| `PlayerDeathGraceTimer` | 倒れた tick | **載らない** (6 章 F3) |

---

## 5. 語彙 (ドメインの語彙の候補) と、同じものの別名

| 概念 | コードの名前 | 別名・揺れ |
|---|---|---|
| 世界の 1 歩 | `WorldTick`, `world tick`, `advance_tick` | 「driver iteration」(`EXP` の外側ループ 1 回。#405 で 1 iteration = 1 tick に揃った)、`TT` の docstring の「wave」(1 tick = 1 wave) |
| エージェントの 1 回の判断 | 「手番」(D1595/D1597)、`turn`, `run_turn`, `schedule_turn` | 「ターン」「wave」「起床」「LLM turn」。`turn` という数が 3 種類ある: `_execution_turns` (Phase B が数える実行の手番)、`MemoryTurnClock` (Being の記憶のターン)、`ExecutionProvenance.actor_turn`。旧 `_turn_counts` は `_self_reschedule_streak` に改名済み |
| 手番の 2 段 | `Phase A` / `Phase B` (`phase_a.py`, `phase_b.py`) | CLAUDE.md は「処理の段階や番号で名前を付けない」としている。中身は「判断を引く」/「判断を世界に当てる」 |
| 起こす | `schedule_turn`, `schedules_turn`, `pending_player_ids`, `maybe_schedule` | 「起床」「起こす」「外部起床」「wake」 |
| 待ち時間のタイマー | `HeartbeatObservationEmitter`, `heartbeat`, `LLM_IDLE_TIMEOUT_TICKS`, `interval_ticks` | 「idle timer」「idle_timeout」「heartbeat」「最大沈黙時間」。設定名は idle、クラスは heartbeat、試験・文書は「待ち時間のタイマー」 |
| 起動判定 | (コードには無い) | 依頼文と D1595/D1597 にある語。**#1692 で消えている** (D1597 末尾)。`src` で「起動判定」が出るのは `unified_recent_event_store.py` のコメントだけ |
| 世界の段 | `stage`, `_SpotGraphTickStage`, `*StageService`, `*TickStage` | `PlayerDeathGraceTickStage`, `TradeOfferExpiryStage`, `StatusEffectsTickStageService` と接尾辞が揃っていない |
| 確定後フック | `post_tick_hooks`, `post_tick.<名前>` | 「post-commit hook」(`SIM:250`)。ただしフックは tick 全体の commit の後ではない (tick は transaction でない、`SIM:108-111`) |
| 個人の結果 | `PlayerOutcomeEnum`, `outcome`, `player_outcome_rules` | 「個人結果」「終局」「outcome 確定」。`is_resolved` (確定) と `is_eliminated` (退場) を分けて使う |
| 倒れる | `is_down`, `PlayerDownedEvent`, `can_act()` | 「ダウン」「昏倒」「倒れている」「行動不能」 |
| 去った主体 | `departed`, `PlayerPerceptionPlane.DEPARTED`, `departed_agents_enabled` | 「幽霊」「去った主体」「死者」。DEAD と departed は同じ人を指すが、departed は設定が有効なときだけ |
| 退場 | `is_eliminated` (DEAD / EJECTED) | 「盤から排除」「退場済み」 |
| 終わり | `GameEndResult`, `check_game_end`, `win/lose/end_conditions` | 「ゲーム終了」「終局」「勝敗」。run の終わり (`outcome` = `TIMEOUT` 等) とゲームの終わり (`GameEndResult.result`) が同じ `outcome` という語で呼ばれる (`EXP:705`)。個人の `outcome` とも同名 |
| 外的停止 | `END_ON_ALL_DOWN` (文字列だけ残る), `_all_players_unable_to_act` | 設定は #1793 で消えたが、終了理由の文字列は grep 互換で残す |
| フェーズ | `GamePhase.FREE_ROAM` / `MEETING`, `GamePhaseStore` | 「自由時間」「会議」「話し合い」 |
| 観測 | `ObservationOutput`, `ObservationEntry`, `observation buffer` | 「観測」「出来事」「直近の出来事」 |
| 主体 | `PlayerId`, `player`, `BeingId`, `Being`, `agent`, `LLM player` | ゲーム側は player、記憶側は Being、文書は「エージェント」。`ActingBeing` が両方を束ねる |
| 世界 / 環境 | `scenario`, `world_id` (`DEFAULT_SINGLE_WORLD_ID`), `environment_id` (`"{metadata.id}#{world_id}"`), `environment_name` (= `metadata.title`) | `world_id` は実験では `scenario_path.stem` (`EXP:539`) にも使われる。`metadata.id` / `stem` / `WorldId` / `environment_id` の 4 つが「この世界」を指す |
| 場所 | `spot`, `SpotId`, `spot_graph` | 「場所」「スポット」「区画」(`WORLD_SPATIAL_METRICS`)、「区間」は経路の 1 本 |
| 移動 | `travel`, `spot_navigation_state`, `is_traveling` | 「移動中」「travel」「navigation」。開始は `do_move` / `start_travel_to_spot`、進行は `advance_spot_travel_one_tick` |

---

## 6. 分からなかったこと、食い違い

### 6-1. 食い違い (コードで確認したもの)

- **F1. `WorldRuntime._tick` は tick の中で 1 つ遅れる**【確認】。`advance_tick` は `_simulation_service.tick()` が返ったあとで `_tick` を合わせる (`WR:825-830`)。手番は `tick()` の中 (確定後フック) で走るので、手番の入口の `check_game_end` (`TT:131`) と、プロンプトの「残り tick」(`_compute_tick_budget_remaining`, `WR:1446-1465`) は前の tick の値を使う。`_check_game_end_collective_mode` と `_satisfied_teams` も `WorldTick(self._tick)` を使う (`WR:3577`, `WR:3673`)。一方で `current_tick()` は正本を読むので、同じ手番の中で 2 つの時刻が混ざる。さらに snapshot の復元は `_time_provider.set_current_tick` だけを呼び (`world_tick_codec.py`)、`_tick` は 0 のまま。【推測】再開後の最初の tick の手番では「残り tick」が上限そのままで出て、`TICK_LIMIT` の判定も tick 0 で行われる。
- **F2. 実行の設定で、同じ tick の中で他人の行動が見えるかが変わる**【確認】。`LLM_TURN_PARALLEL_WORKERS <= 1` では 1 人ずつ A→B なので、後の人は前の人の行動の観測を同じ tick のプロンプトで読める。`>= 2` では全員の A (観測の取り出し) が B より先なので読めない (`TT:150-195`)。本命の profile は 2、`smoke_stub` は 0。【推測】smoke と本番で、世界の時間の意味が違う。
- **F3. 死亡の猶予タイマーは snapshot に載らない**【確認】。world の codec 一覧 (`application/being/world_subsystems/`) に猶予タイマーの codec は無く、倒れた体の記録 (`fallen_body_codec.py`) だけが載る。タイマーへの登録は `PlayerDownedOutcomeHandler` (`player_downed_outcome_handler.py:82`) だけ。【推測】倒れた人がいる状態で保存して再開すると、その人は DEAD に確定しない。
- **F4. 天候を宣言しない世界でも天候は進み、知らせが出る**【確認】。`weather_config` が無いと初期値 FOG 0.6、6 tick ごとに遷移 (`WR:4873-4880`, `WR:5371-5377`)、知らせの登録は `weather_config is None or announce_changes` (`WR:6472`)。`enabled: false` の世界も遷移は進む (知らせは `announce_changes` 次第)。【確認】`data/scenarios` の 19 本はすべて `weather` を書いているので、宣言の無い世界は今は無い。【推測】`enabled: false` の世界でも `WEATHER_IS` 条件やモンスターの出現条件は動いている天候を読む。
- **F5. 腐敗の知らせの docstring と実装が合わない**【確認】。`_append_food_spoiled_batch_observation` の docstring は「日境界または game-end の直前に 1 日分まとめて flush」(`WR:3438-3440`) だが、flush を呼ぶのは日の変わり目の 2 か所だけ (`WR:839`, `WR:3453`)。終了の前に flush する呼び出しは無い。その日のうちに終わった分は知らされない (snapshot には `pending_food_spoilage_codec` で載る)。
- **F6. 追放と、会議開始時の異常の解決が 2 か所にある** (★13, ★14)。runtime 側 (`eject_player`, `begin_meeting`) は本番から呼ばれず、試験からだけ呼ばれる。runtime の `begin_meeting` は緊急ボタンを消費せず、集合 (`_gather_for_meeting`) もしない。試験が本番と違う経路を見ている可能性がある。
- **F7. 会議の tick 上限 < 死亡の猶予は、既定値でしか守られていない** (M12)。シナリオで `meeting.tick_limit` と `death.grace_ticks` を別々に変えられるが、組み合わせを読み込み時に確かめる箇所は見当たらない (`parse_world.py`, `validate_features.py` を grep した範囲)。
- **F8. 手番の外から手番を回す入口が残る**: `RM:582-590`。D1618 の「残っている穴」に書かれたとおり、呼ぶものは無い。
- **F9. 「起動判定」は今のコードに無い**。依頼文にある語だが、D1597 の末尾のとおり #1692 で消えている。手番の起こし方は 2-2 の表がすべて。
- **F10. 時刻の換算が 4 か所**: `WR:_time_label`、`WR:_minutes_per_tick`、`WR:_ticks_per_day_or_default`、`wiring.py:_time_label` と `RM:send_chat_message` のフォールバック (`tick % 24` を「時」として扱う。5 分/tick と合わない)。【確認】実験経路では runtime の `_time_label` が使われるので、フォールバックは runtime が `_time_label` を持たないときだけ。
- **F11. `_wire_being_stack` が宣言の無い属性を作る** (`WR:1875-1902`)。dataclass のフィールド宣言 (`WR:485-680`) には `_player_beings` などが無い。宣言の無い属性は代入側の typo を受け入れる、と同じファイルの別のコメント (`WR:597-599`) が書いている。
- **F12. `SIM` のコメントの「post-commit hook」**: tick は transaction ではない (`SIM:108-111`) ので、フックは「tick 全体が確定したあと」ではなく「各段がそれぞれ確定したあと」。名前から受ける印象と違う。

### 6-2. 分からなかったこと

- `to_run = list(set)` の順番 (`TT:141`)。Phase B はこの順に世界を変えるが、順番を決める規則は書かれていない。【推測】小さな int の set は CPython で昇順に並ぶので、事実上 player_id の昇順。順番に意味を持たせる規則があるのかは分からない。
- 救助・取り残しの人をグラフから外さないことの意図。同席の表示 (`state_builder` の死者チェックは `is_eliminated` だけ) にどう出るかは追っていない。
- 会議中の投票が沈黙の起点を進めるか。`note_activity` を呼ぶのは発言 (`WR:1148`) だけで、`cast_vote` は呼ばない (`MCS:121-171`)。投票が「活動」に入らないのが意図かは分からない。
- 段 2〜5 (出来事・物・通路・同期操作) と、モンスター・状態異常の段の中身は範囲外として追っていない。D1558 の表によると、取りやめる単位は段ごとに違う。
- `apply_async_results` (Phase A の入口で非同期の結果を反映, `WR:1034-1039`) にどの handler が載るか。登録側は Being の記憶の書き起こし (`_wire_backstory_writing` など) と見えるが、確かめていない。
- 待ち時間のタイマーは全員の player_id を対象にする (`RM:423-424`)。倒れた人・確定した人に心拍の観測を入れたとき、appender が捨てるのか積むのかは確かめていない。積んでも手番の入口で落ちるので手番にはならない。
