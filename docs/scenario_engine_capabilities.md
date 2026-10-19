# シナリオ JSON で表現できる世界の仕組み (2026-10-05 時点、HEAD 23c6daa2)

#1508 (記憶を測るための、推論と敵対が要るシナリオ) の準備として、いまのエンジンでシナリオの JSON に何が書けるかを洗い出した一覧。書けないものはエンジン改善の Issue (#1513〜#1518、#1522) にした。

調べ方: ローダ (`src/ai_rpg_world/infrastructure/scenario/`)、ドメインの enum と評価器、実行時の stage service、ツール定義、既存シナリオ 19 本を読んだ。実 LLM・API は呼んでいない。

判定の記号: **できる** / **部分的** / **できない**。「推測」と書いたもの以外は、コードまたは既存シナリオで確かめた。

パスの略記:
- `L/` = `src/ai_rpg_world/infrastructure/scenario/`
- `D/` = `src/ai_rpg_world/domain/world_graph/`
- `A/` = `src/ai_rpg_world/application/`

> 2026-10-10 追記: 「確かめた不具合」の `PLAYER_AT_SPOT` と、I-13 (未知のキーを読み飛ばす) は #1513 (PR #1519) で直した。残る抜け道 (必須キーの欠け、値の綴り違い、包む層のキー) は #1522。

## 前提: 記述の部品

| 部品 | 何を書くか | 根拠 |
|---|---|---|
| `spots[].interior.objects[].interactions[]` | 物体への操作 (`interact` ツール)。`preconditions` (すべて AND) と `effects` | `L/parse_map.py:449-509`, `L/parse_interactions.py:77-233` |
| `item_specs[].interactions[]` | 持ち物の操作 (`use_item`)。物体系の効果には `target_object` が必須 | `L/parse_economy.py:308-375` |
| `item_specs[].event_removal_message` | シナリオの出来事 (`scenario_events` の `REMOVE_ITEM`) で持ち物から外れたとき、持ち主にだけ届く文 (例: 灯の燃え尽き)。人の操作 (使う、奪う、渡す、売る) で外れたときは使わず、「〈品名〉が手もとからなくなった。」になる | `L/parse_economy.py`、design_decisions D1569 |
| `metadata.limits_actions` | false にすると、system prompt の「行動の制限」の行 (行動の総量には限りがある) を出さない。締め切りを置かない世界で使う。既定は true | `L/parse_helpers.py`、design_decisions D1569-3 |
| `player_interactions[]` | 人を対象にする操作。`target: TARGET_PLAYER` の効果が 1 つ以上要る | `L/parse_interactions.py:343-400` |
| `scenario_events[]` | 世界の側で起きる出来事。`trigger` は `ON_TICK` か `ON_CHAIN`。条件は AND/OR/NOT の木 | `L/parse_scenario_events.py:46-166`, `L/validate_features.py:98-99` |
| `reactive_bindings.objects/passages` | 条件の真偽に応じて物体の state / 通路の状態を切り替える | `L/parse_reactive_bindings.py:23-198` |
| `synchronized_action_groups[]` | 複数人が窓 tick 内にそろえる操作 | `L/parse_sync_groups.py:66-146` |
| `game_end_conditions` / `player_outcome_rules` | 終了と個人結果 | `L/parse_world.py:585-727`, `L/parse_scenario_events.py:168-244` |

使える条件・効果の種類:
- 操作の前提条件 (`InteractionConditionTypeEnum`、30 種): `D/enum/interaction_condition_type.py`
- 効果 (`InteractionEffectTypeEnum`、33 種): `D/enum/interaction_effect_type.py`
- 出来事・反応の条件 (`ScenarioEventCondition`): leaf 15 種 + AND/OR/NOT。`D/value_object/scenario_event_condition.py:12-30`

**2 系統の条件は別物**。操作の前提条件は AND だけで、OR/NOT・確率・tick 条件を持たない。出来事・反応の条件は人の state・時間帯・明るさを見られない。

## A. 世界の決まり

| # | 項目 | 判定 | 書き方の要点 | 根拠 | 制限 |
|---|---|---|---|---|---|
| 1a | 資源の在庫と時間回復 | **できる** | 方式は 2 つ。(1) 備蓄プール: 物体の `state` に `stock` / `stock_capacity` / `stock_tick` / `stock_refill_interval` を置き、前提条件 `OBJECT_STOCK_AT_LEAST` と効果 `CONSUME_OBJECT_STOCK` (`amount`) を組む。(2) 枯渇と再生: `RECORD_OBJECT_STATE_TICK` で採った tick を記録し、`reactive_bindings.objects` の `OBJECT_STATE_TICK_AT_LEAST` (`ticks_offset`) で `available` を戻す | `D/service/stock_pool_regen.py:31-75`、`D/service/effect_application/handlers/object_state.py:152-171`。使用例: v4 `berry_bush_a.harvest`、`shellfish_rocks.gather_shellfish`、`driftwood_pile` (16 tick で再生) | 備蓄の回復量は `refill_interval` ごとに **+1 個で固定**。量を変えたり、回復を確率にしたりはできない。`INCREMENT_OBJECT_STATE` と `OBJECT_STATE_INT_AT_LEAST` で「N 回採ると永久に枯れる」も書ける |
| 1b | 周期的な変化 (潮の満ち引き) | **部分的** | `scenario_events` に `once: false` と `TICK_MODULO` (`tick_modulo`, `tick_phase`) を書き、`SET_FLAG` / `CLEAR_FLAG` でフラグを切り替える。そのフラグを、操作の前提条件 `FLAG_SET` / `FLAG_NOT_SET` と、通路の反応から読む | `A/world_graph/scenario_condition_evaluator.py:698-703`。v4 の潮は一回きり (`tide_rises` tick 90、`tide_falls` tick 150) | `TICK_MODULO` を使う既存シナリオは無く、周期の切り替えを試した例が無い。出来事・反応の条件は **時間帯を直接見られない**。tick の剰余で計算して合わせる |
| 2 | 天候・時間帯で行動を変える | **部分的** | 操作の前提条件に `TIME_OF_DAY_IS(_NOT)`、`WEATHER_IS(_NOT)`、`SPOT_LIGHTING_IS(_NOT)`。出来事・反応の条件には `WEATHER_IS`、`TICK_*`。モンスターは `spawn_condition.day_night_phases` / `weather_types` で出現を絞れる | `L/parse_interaction_conditions.py:132-143, 179-209`、`L/validate_features.py:138-210`。使用例: v4 `fish_deep` | **天候の遷移は engine 固定** (`A/world_graph/spot_graph_environment_stage_service.py:85-92`)。シナリオから書けるのは初期値と `update_interval_ticks` だけで、天候を変える効果も無い。日付の概念は無い。変えられるのは行動の**可否**だけで、結果を変えるには前提条件の異なる操作を並べるしかない |
| 3 | 前提条件つきの行動 | **部分的** | 持ち物 `HAS_ITEM` / `HAS_ITEMS`、フラグ `FLAG_SET` / `FLAG_NOT_SET`、その場の人数 `PLAYERS_AT_SPOT` (以上)、本人の状態 `PLAYER_STATE_IS` / `PLAYER_NEED_AT_LEAST` / HP 比 / 所持金、相手の状態 `TARGET_PLAYER_STATE_IS` / `TARGET_PLAYER_IS_INCAPACITATED` / `TARGET_HAS_ITEM`、物体の状態 `OBJECT_STATE` / `OBJECT_STATE_INT_AT_LEAST`、合言葉 `PUZZLE_INPUT_MATCH` | `D/service/spot_interaction_service.py:330-620` | 条件は **AND だけ**。**人数の上限**を書けない。**過去にしたこと**は `CHANGE_PLAYER_STATE` の印と `PLAYER_STATE_IS` でしか書けず、`PLAYER_STATE_IS` は満たさない人から**操作ごと隠れる**。`RECORD_PLAYER_STATE_TICK` を読む条件が無い。**結果の分岐を 1 つの操作に書けない** (効果に条件が付かない) |
| 4 | 作る・組み合わせる | **部分的** | `HAS_ITEM` を並べ、効果で `REMOVE_ITEM` と `GIVE_ITEM` を組む (v4 `crafting_log.craft_fishing_rod`、`fire_pit.cook_fish`)。持ち物の instance state で道具の状態も持てる | `D/service/effect_application/handlers/items.py:133-146` | **`COMBINE_ITEMS` は JSON から実質使えない** (文字列 ID を変換しない。`parse_interaction_effects.py:230-244`)。レシピ表、何 tick もかかる工程、品質の揺らぎは無い |
| 5a | 敵 (monsters) | **できる** | `monsters.templates` (能力値、`attack_status_effects`、`respawn`、`vision_range`、`flee_threshold`) と `initial_placements` (`spawn_condition`: `day_night_phases` / `required_flags` / `forbidden_flags` / `weather_types`) | `L/parse_actors.py:113-381`、`A/monster/services/spot_monster_behavior_tick_service.py:1-25` | `attack` ツールは**モンスター専用**。モンスターのスキルは無い |
| 5b | 環境の危険 (2 人で同時に渡ると落ちる橋) | **できない** | 近い書き方: 物体の操作に `APPLY_DAMAGE` を付ける (v4 `slippery_cliff_edge.peer_over`)、状態つきの物体 (`crumbling_beam`) | `CHANGE_ATMOSPHERE` の `hazard_level` は保存されるだけで、読む実行時コードが無い | 移動は操作ではないので、渡った瞬間に何も起こせない。通路の条件は `ALWAYS` / `ITEM_REQUIRED` / `FLAG_SET` / `PUZZLE_SOLVED` の 4 種だけ。`scenario_events` の効果は人を対象にできず、`GIVE_ITEM` は全員に配られる |
| 5c | ダメージ | **できる** | `APPLY_DAMAGE` (対人なら `target: TARGET_PLAYER`)、`APPLY_STATUS_EFFECT` (`status_effect_type`, `value`, `duration_ticks`)、`needs.starvation_damage_per_tick` | `handlers/cross_domain.py:60-88` | `APPLY_STATUS_EFFECT` は相手を対象にできない |
| 6 | 遅れて起きる結果 | **部分的** | (1) `scenario_events` の `next_event_id` と `delay_ticks`。(2) `RECORD_OBJECT_STATE_TICK` と `OBJECT_STATE_TICK_AT_LEAST`。(3) 食べ物の腐敗 `spoils_after_ticks`。本人への遅れは状態異常の持続 | `L/parse_scenario_events.py:104-120` | **行為者本人に数 tick 後に効果を返す仕組みが無い** |
| 7a | 隠れた決まり (試して初めて分かる) | **部分的** | 試すまで見えない条件: `FLAG_SET`、`PLAYERS_AT_SPOT`、`PLAYER_NEED_AT_LEAST`、HP、所持金、`PUZZLE_INPUT_MATCH`、物体操作の `HAS_ITEM`。`hide_when_flag_preconditions_fail: true` でフラグ条件を満たすまで操作が一覧に出ない | `A/world_graph/spot_graph_current_state_builder.py:266-295`、`A/world_graph/interaction_condition_hint_text.py:97-257`、`D/enum/interaction_condition_visibility.py` | **時間帯・天候・明るさは必ずヒントとして表示される**。物体の state 条件は事前に「いまできない」と出る。**伏せる設定は無い**。`PLAYER_STATE_IS` は操作ごと消えるので「試して失敗する」体験にならない |
| 7b | 失敗したときに返す文 | **できる** | 前提条件ごとに `failure_message`。`on_failure_observation` で居合わせた人にも見える | `A/llm/services/executors/spot_graph_tool_executor.py:1684-1700` | 書かなければ engine の既定文で、決まりの中身を漏らす場合がある |
| 8a | ランダム性 | **部分的** | `GIVE_FROM_LOOT_TABLE` (重みつき)、出来事・反応の条件 `PROBABILITY`、状態異常の `chance`、戦闘、天候 | `L/parse_economy.py:50-130` | **操作の前提条件に確率が無い**。抽選表は「何も出ない」を表せない |
| 8b | シードでの再現 | **できる** (#1529 で追記) | `SCENARIO_RANDOM_SEED`。条件判定・天候・抽選表・攻撃・モンスターの行動の乱数を、用途ごとにシードと回の番号から作る | `A/world_runtime/world_random.py`、design_decisions D1514-3 | 続きからの再開では、抽選表・攻撃・モンスターの行動の乱数は先頭から引き直す。タイル地図の世界の戦闘 (`combat_logic_service.py`) は対象外 |
| 9 | 情報を持つ物 | **部分的** | `SHOW_MESSAGE` (行為者だけに見える)、`description_variants` (`required_state` / `required_flag`)、`is_visible: false` と `REVEAL_OBJECT`、隠れた `sub_locations`、`discoverable_items` (`explore` で探す)、場所に書く掲示 `WRITE_PLAYER_TEXT`、遠景 `distant_cues`、本人だけが知ること (`persona_prompt`、`objective`、`secret` の属性) | `L/parse_map.py:400-509, 521-531`、`L/parse_economy.py:734-802` | **地図は全員一律**。掲示は 1 枚を上書きする方式 |

## B. 他者との交流

| # | 項目 | 判定 | 書き方の要点 | 根拠 | 制限 |
|---|---|---|---|---|---|
| 10 | 話す手段 | **できる** | `speak` の `whisper` (同じ場所の 1 人)、`say` (隣接まで)、`shout` (2 つ先まで)、`say_inline`、SNS、市場の掲示板、場所の掲示 | `tool_catalog/spot_graph.py:213-253` | 届く範囲は engine 固定 (通路の `sound_permeability` だけ書ける)。**チームだけの連絡手段が無い** |
| 11 | 取引・譲渡・約束 | **部分的** | `give_item`、条件つきの交換 `player_trade` (`offer_expires_in_ticks`)、商人、市場 | `L/parse_world.py:333-369` | **約束 (後払いなど) を記録し、守ったか判定する仕組みは無い** |
| 12 | 複数人でしかできない行動 | **できる** | `synchronized_action_groups[]`、人数の前提条件 `PLAYERS_AT_SPOT` | `L/parse_sync_groups.py`。使用例: station_drill `restore_frozen_fuel` | 完了時の効果に行為者が居ない。協力した本人たちに品物を渡せない (推測: 全員に配られる) |
| 13 | 本人だけの情報・目的 | **できる** | `players[]` の `persona_prompt`、`objective`、`initial_items`、`initial_state`、`knows_at_start` (入るときに紹介する相手。書かなければ全員)。`role_personas`。属性の `visibility` は `public` / `secret` | `L/parse_actors.py:78-111, 383-536` | 公開範囲は 2 択で、**チーム内だけに公開する属性**は書けない |

## C. チームと敵対

| # | 項目 | 判定 | 書き方の要点 | 根拠 | 制限 |
|---|---|---|---|---|---|
| 14 | チームの定義と勝利条件 | **できる** (#1516 で追記) | シナリオの `teams` に、`id`、`name`、`member_state` (所属を決める `initial_state` の値)、`win` (勝利条件) を書く。チームの全員の個人結果を見る `ALL_MEMBERS_HAVE_OUTCOME` が使える。回ごとの組み分けは `round_assignment` の枠に `member_state` の値を書く。勝つのは高々 1 チームで、同時に成立したら DRAW | `L/parse_teams.py`、`D/value_object/scenario_team.py`、design_decisions D1516 | `teams` を書くと `game_end_conditions.win` / `lose` は置けず、`end` が 1 つ以上要る。`ALL_AT_SPOT` / `ANY_AT_SPOT` はチームの勝利条件に置けない。チームの名前と相手チームの所属はプロンプトに出ない。チーム内だけに公開する属性とチームだけの連絡手段は無い |
| 15 | 隠れた役 | **できる** | `initial_state.role` と `PLAYER_STATE_IS`。偽装用の操作を並べることもできる | `A/world_graph/hidden_interaction_filter.py` | 役の割り当ては JSON に固定 |
| 16 | 攻撃・妨害・盗み・死・脱落 | **できる** | `player_interactions` (`APPLY_DAMAGE`、`REMOVE_ITEM` と `GIVE_ITEM`、`witness_policy`、暗所の目撃文)、`death`、`tend_to_player`、`departed_agents_enabled` | `L/parse_world.py:78-235, 307-331` | 相手に状態異常や移動を与える効果は未配線。`attack` は人に使えない |
| 17 | 会議と投票 | **できる** | `meeting` ブロック、`CALL_MEETING`、`report_body`、`vote` | `L/parse_world.py:269-305, 371-390` | 投票の方式は engine 固定 (推測) |
| 18 | 勝敗の判定 | **できる** (#1516 で追記) | `game_end_conditions.win` / `lose` / `end`、`player_outcome_rules`。`teams` のあるシナリオでは `teams[].win` と `end` | `L/validate_features.py` の `_GAME_END_CONDITION_ALLOWED_SECTIONS`、design_decisions D1516 | 個人の結果は RESCUED / DEAD / EJECTED / STRANDED で、個人の勝敗は所属チームの勝敗と同じ (別の軸として trace の `team_result` に並ぶ)。個人結果の規則に役を見る条件は無い。結果を本人に届けて記憶へ持ち越す経路は無い |

## D. 繰り返し遊ぶ

| # | 項目 | 判定 | 書き方の要点 | 根拠 | 制限 |
|---|---|---|---|---|---|
| 19 | 記憶を持ち越して何回も遊ぶ | **できる** (#1526 で追記) | 実験設定に `"snapshot_load_mode": "replay"` を書く。1 回目は `SNAPSHOT_LOAD_DIR` 無し、2 回目以降は `make experiment-resume` に前の回の `snapshots` を渡す。回の番号は前の回の resolved から数え、`run_start` に残る | `scripts/run_scenario_experiment.py` の `_resolve_replay_round`、design_decisions D1514 | 記憶の欄は Being のターン数で持ち、世界の tick を持たないので、世界を tick 0 に戻しても記憶の前後はずれない |
| 20 | 回ごとに役や初期配置を変える | **できる** (#1527 で追記) | シナリオの `round_assignment.groups` に、player と同じ数の枠 (`spawn_spot`、`initial_state`) を書く。`SCENARIO_RANDOM_SEED` と回の番号で並べ替えて割り当て、trace の `round_assignment` に残る | `L/parse_round_assignment.py`、design_decisions D1514-2 | シードが要る。並べ替えなので、回が変わっても同じ並びになることがある。枠ごとの持ち物は書けない |
| 21 | 1 つの run の中で回を区切る | **できない** | — | ゲームが終わると run も終わる | 持ち物の回収、HP の回復、死者の復帰、tick の巻き戻しは書けない |

## E. 測る

| # | 項目 | 判定 | 根拠 | 制限 |
|---|---|---|---|---|
| 22 | 行動の結果・フラグ・資源の変化が trace に出るか | **部分的** | 出るもの: `action`、`action_result` (`success`、`error_code`、`precondition_failure_kind`)、`world_flag_changed`、`scenario_predicate_evaluated` (出来事・反応・個人結果の判定)、`observation`、`position_change`、`meeting_started/ended`、`run_end` | **出ないもの**: 物体の state の変化、持ち物の増減、HP、個人結果の確定 (終了時の個人結果は、`teams` のあるシナリオでだけ `team_result` に出る)、操作の前提条件の評価 (どの条件で落ちたか)。「資源が尽きたのを見て場所を変えた」のような、世界の状態との対応が組み立てにくい |

## 確かめた不具合 (#1513 で直した)

島のシナリオ (v2 / v2_short / v3_coop / v4_coop) の `PLAYER_AT_SPOT` に `player_id` と `spot_id` が書かれていたが、ローダが読むのは `target_spot` だけで、条件が一度も成立しなかった。`outpost_discovered` と `lone_hut_discovered` が発火していなかった。原因は未知のキーを黙って読み飛ばすことで、#1513 (PR #1519) で読み込み時に止めるようにした。同じ PR で、潮が引かない (`tide_falls` が `SET_FLAG` に `value: false`) と、出血が付かない (`duck_under` の種類のキー名違い) も直した。

## できない・足りないもの と Issue

| 候補 | 中身 | Issue |
|---|---|---|
| I-1 | 「最初からやり直す」と「続きから」を区別して起動できない | #1514 (#1526 で対応) |
| I-2 | 回ごとに役と初期配置を割り当て直せない | #1514 (#1527 で対応) |
| I-3 | 結果の分岐と確率が操作に書けない (AND だけ、効果に条件が付かない、人数の上限が無い) | #1515 |
| I-4 | 決まりのヒントを伏せられない | #1515 |
| I-5 | 世界の出来事から人を対象にできない (その場の人へのダメージ、協力した本人への報酬、行為者への遅れた効果) | #1517 |
| I-6 | 移動に決まりを付けられない (渡ったときの効果、同時に渡る人数) | #1517 |
| I-7 | 出来事の条件に時間帯が無い。天候の遷移を書けず、天候を変える効果も無い | #1517 |
| I-8 | 乱数のシードが一部にしか効かない | #1514 (#1529 で対応) |
| I-9 | 陣営が概念として無い (陣営ごとの勝敗、チーム内の情報、チームの連絡手段) | #1516 (勝敗は対応。チーム内の情報は続く PR、連絡手段は未対応) |
| I-10 | 本人の過去の行為を条件にできない | #1517 |
| I-11 | 約束を記録し、守ったかを判定する仕組みが無い | 優先度を下げた (予期の仕組みで他人についての予期として扱う) |
| I-12 | `COMBINE_ITEMS` が JSON から使えない | 優先度を下げた (今ある効果を並べれば表現できる) |
| I-13 | 未知のキーを黙って読み飛ばす | #1513 (直した)、残りは #1522 |
| I-14 | 世界の状態の変化が trace に出ない | #1518 |
| I-15 | 人ごとに知っている地図を変えられない | 優先度を下げた (チームごとの知識は人格の設定で配る) |

## 推測で書いた箇所 (確かめていない)

- #12 の「`on_complete` の `GIVE_ITEM` は全員に配られる」
- #17 の「投票の方式は engine 固定」
- #19 の「新しい run の tick が 0 から始まり、前の回の記憶の tick と同じ時間軸に並ぶ」
