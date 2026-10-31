# 範囲 D: 世界の状態の持ち主 (集約・値オブジェクト・規則の一覧)

対象: origin/main `21a33e4c9`。
パスは `src/ai_rpg_world/` からの相対で書く。行番号はこのコミットのもの。

## 調べ方と、印の意味

- コードを読んだ。加えて、`create_world_runtime` で `mine_village_v1.json` と `station_drill.json` の runtime を組み、`advance_tick()` を 5 回呼んだあと、`gc.get_objects()` でドメインの型のインスタンスを数えた (使い捨ての調査スクリプトで数えた。スクリプトは残していない)。LLM は呼んでいないので、エージェントの行動で初めて作られる型 (モンスター個体、ドロップ品など) はこの数に出ない。
- **[確認]** コードか実行結果で確かめた事実。**[推測]** 読んだ範囲からの見立てで、確かめていない。
- 「今の run で使われているか」: ◎ 2 シナリオとも状態が動く / ○ 片方、または条件付きで動く / △ 作られるが空のまま / × runtime から作られない。

---

## 1. 集約と値オブジェクトの一覧

### 1-1. 状態を持つ集約 (AggregateRoot を継承するもの)

| 名前 | 持つもの | 変える操作 | 自分で守る規則 | 置き場所 | run |
|---|---|---|---|---|---|
| `SpotGraphAggregate` (世界に 1 つ。ID は `SpotGraphId`) | スポット (`SpotNode`)、接続 (`SpotConnection` と逆向きの対応)、プレイヤーの居場所 (`_entity_spot` / `_presences`)、モンスターの居場所 (`_monster_spot` / `_monster_presences`) | `add_spot` `add_connection` `add_connection_dynamic` `remove_connection` `set_connection_passage(_state)` `update_spot_atmosphere` `place_entity` `unplace_entity` `teleport_entity` `move_entity` `place_monster` `unplace_monster` `move_monster` `emit_listen_carefully` | スポット ID と接続 ID の重複禁止、両端が登録済みのスポット、二重配置の禁止、移動は接続の始点から・通行可のときだけ、モンスターの二重索引の整合 (復元時) | `domain/world_graph/aggregate/spot_graph_aggregate.py` | ◎ |
| `PlayerStatusAggregate` (ID `PlayerId`) | 能力値・成長・経験値表、HP/MP/スタミナ・所持金、ダウン、状態異常、注意の水準、スポット移動の途中状態 (`PlayerSpotNavigationState`)、欲求 (`AgentNeeds`)、自由 state (dict)、前回の欲求と HP (差分表示用)、`_current_spot_id` | `apply_damage` `heal_hp` `use_mp` `pay_gold` `earn_gold` `consume_stamina` `consume_resources` `gain_exp` `revive` `speak` `increase_need` `satisfy_need` `apply_needs_decay_tick` `apply_fatigue` `recover_fatigue` `add_status_effect` `cleanup_expired_effects` `set_spot_navigation_state` `set_spot_sub_location` `replace_state` `merge_state` `set_attention_level` `snapshot_*_for_delta` | ダウン中は MP・ゴールド・スタミナを使えない/経験値を得ない/発言できない、残量不足の消費禁止、HP 0 でダウン、state は JSON の素の値だけ | `domain/player/aggregate/player_status_aggregate.py` | ◎ |
| `PlayerInventoryAggregate` (ID `PlayerId`。状態の集約と同じ ID) | 枠ごとのアイテム ID、装備枠、取引のために押さえたアイテム ID、枠数 | `acquire_item` `move_item` `drop_item` `remove_item` `remove_item_for_storage` `remove_item_for_placement` `reserve_item` `unreserve_item` `remove_reserved_item` `request/complete_equip_item` `unequip_item` `request/complete_inventory_compaction` | 枠の範囲、空き枠への移動、押さえたアイテムは動かせない、装備枠の種類 | `domain/player/aggregate/player_inventory_aggregate.py` | ◎ |
| `ItemAggregate` (ID `ItemInstanceId`。中に `ItemInstance` を 1 つ持つ) | 個体の仕様 (`ItemSpec`)、数量、耐久、state (腐敗の開始 tick・腐ったか など) | `use` `add/remove/set_quantity` `repair_durability` `replace_state` `merge_state` `advance_spoilage` | 数量 0 以上・スタック上限以下、耐久を持つなら仕様と最大値が一致しスタック 1、state は JSON の素の値だけ (`ItemInstance` 側) | `domain/item/aggregate/item_aggregate.py`、`domain/item/entity/item_instance.py` | ◎ (mine 15 個、station 4 個) |
| `MonsterAggregate` (ID `MonsterId`) | テンプレート、出現スポット `_spot_id`、生死と HP/MP/空腹 (`MonsterLifecycleState`)、行動状態 (追跡・逃走・探索)、群れ、技能、餌の記憶、最後に攻撃した/された tick と相手 | `spawn` `apply_damage` `take_environmental_damage` `heal_hp` `recover_mp` `use_mp` `record_attack` `record_attacked_by_in_spot` `enter_flee_state` `enter_chase_state` `start_chase_search` `tick_chase_search_timer` `clear_behavior_state_to_idle` `remember_feed` `on_tick` | 生きているときだけ傷つく・回復する・攻撃を記録する、出現中の二重出現の禁止、空腹 0〜1 | `domain/monster/aggregate/monster_aggregate.py` | ○ (mine のみ。フラグが立つと出現。5 tick では 0 個) |
| `PlayerBeings` (ID `WorldId`) | プレイヤー ↔ Being の 1 対 1 の対応表 | `drive` `replace_with` | 1 人のプレイヤーを動かす Being は 1 つ、1 つの Being が動かすプレイヤーは 1 人 | `domain/world/aggregate/player_beings.py` | ◎ |
| `LootTableAggregate` | ドロップ表 | (作るだけ) | — | `domain/item/aggregate/loot_table_aggregate.py` | △ (宣言が無ければ空の保存先) |
| `RecipeAggregate` | 調合の材料と結果 | — | — | `domain/item/aggregate/recipe_aggregate.py` | × |
| `IntentQueue` | 意図の待ち行列 | — | — | `domain/intent/aggregate/intent_queue.py` | × (`IntentResolutionService` を組む `ToolCommandMapper(` が src に無い) |
| `WeatherZone` | 天候区域 | — | — | `domain/world/aggregate/weather_zone.py` | × (天候は runtime の dict が持つ。下記) |
| `LocationEstablishmentAggregate` | 施設の割当 | — | — | `domain/world/aggregate/location_establishment_aggregate.py` | × (SQLite 保存先・ギルド・ショップからだけ参照) |
| `PlayerProfileAggregate` | 名前・役割・種族・属性・操作主 | `change_*` | — | `domain/player/aggregate/player_profile_aggregate.py` | × (runtime の名前はシナリオの spawn と Being の persona から来る) |

### 1-2. 状態の一部を表す値オブジェクト・エンティティ (中身が変わる場所を示す)

| 名前 | 持つもの | 変え方 | 自分で守る規則 | 置き場所 | run |
|---|---|---|---|---|---|
| `SpotInterior` (frozen dataclass。ID なし。保存先がスポット ID をキーに持つ) | サブロケーション、物体 (`SpotObject`)、地面のアイテム (`GroundItem`)、探索で見つかるアイテム (`DiscoverableItem`) | `replace_object` `replace_sub_location` `replace_discoverable_items` `with_ground_item` `without_ground_item` が新しい値を返し、呼び出し側が `ISpotInteriorRepository.save` で差し替える | 置き換える物体・サブロケーションが存在すること | `domain/world_graph/entity/spot_interior.py` | ◎ |
| `SpotObject` (frozen。ただし `state: dict`) | 名前・説明・作用 (`InteractionDef`)・表示の規則、`state`、見えるか、パズル、詳細を読んだ人、隠す state のキー | `with_state` `with_visible` `with_puzzle` `with_detail_read` | 名前が空でない、`unavailable_hint` が空でない | `domain/world_graph/entity/spot_object.py` | ◎ |
| `SubLocation` | 隠れているか、発見条件 | `revealed()` | 名前が空でない | `domain/world_graph/entity/sub_location.py` | ○ |
| `SpotNode` | 名前・説明・分類・親・雰囲気 (`SpotAtmosphere`)・屋外か・罠・位置・エリア、`interior` (シナリオ読込では None) | 集約の `update_spot_atmosphere` が丸ごと差し替える | 名前が空でない | `domain/world_graph/entity/spot_node.py` | ◎ |
| `SpotConnection` (frozen。ただし `passage_conditions: list`) | 両端、所要 tick、双方向か、通行条件、`Passage` | 集約の `set_connection_passage(_state)` が差し替える | `travel_ticks >= 0` | `domain/world_graph/entity/spot_connection.py` | ◎ |
| `Passage` | 種類 (開口・壁・扉・障壁)、状態、通れるか、音の通しやすさ、状態ごとの上書き | `with_state` | 音の通しやすさ 0〜1、状態の上書きの重複禁止、種類と状態の組の既定値があること | `domain/world_graph/value_object/passage.py` | ◎ |
| `PlayerSpotNavigationState` | 現在のスポット、サブロケーション、移動中か、経路・区間・残り tick | `at_rest` `begin_travel` `advance_one_world_tick` `with_sub_location` | 経路は 2 スポット以上、区間・接続・所要 tick の数が揃う、移動中はサブロケーションを変えない | `domain/player/value_object/player_spot_navigation_state.py` | ◎ |
| `Hp` `Mp` `Stamina` `Gold` | 値と上限 | `heal` `damage` `consume` `add` `subtract` (新しい値を返す) | 0 以上・上限以下。`create` は範囲に丸める | `domain/player/value_object/` | ◎ |
| `AgentNeed` / `AgentNeeds` | 空腹・疲労の値と上限 | `increase` `satisfy` `with_updated` | 0〜上限 (`create` は丸める) | `domain/player/value_object/agent_need(s).py` | ◎ |
| `WorldFlagRegistry` | フラグ名の集合 | `with_added` `with_removed` | なし (任意の文字列) | `domain/world_graph/value_object/world_flag_registry.py` | ◎ |
| `GamePhaseState` | 自由時間/会議、開始 tick、最後の発言 tick、きっかけ、招集者 | `with_activity_at` | 開始 tick 0 以上 など | `domain/world_graph/value_object/game_phase_state.py` | ○ (station_drill の会議) |
| `PuzzleState` | 種類・正解・入力・解けたか・試行回数 | `with_input` `with_step` `with_solved` `with_reset_input` | 種類と正解が空でない | `domain/world_graph/value_object/puzzle_state.py` | ○ |
| `SpotPresence` / `MonsterSpotPresence` | スポットに居る ID の集合 | `add` `remove` | 二重追加・不在の削除を断る | `domain/world_graph/value_object/` | ◎ |
| `WeatherState` | 天候の種類と強さ | 天候の段の `WeatherSimulationService.simulate_next_weather` | — | `domain/world/value_object/weather_state.py` | ◎ (mine は SNOW、station は FOG) |
| `TimeOfDay` (world_graph) / `DayNightCycleDef` | ある tick の時刻の派生値 | tick から計算 | 比率・光の範囲 | `domain/world_graph/value_object/time_of_day.py` | ○ (mine のみ。station は昼夜なし) |
| `ItemSpec` | 仕様 (名前・種類・スタック上限・耐久・消費効果・腐るまでの tick・光源か …) | 不変 | 名前・説明が空でない、装備品なら装備種別、置ける品なら物体種別、消費効果は CONSUMABLE だけ | `domain/item/value_object/item_spec.py` | ◎ (シナリオの宣言) |
| `StatusEffect` / `StatusModifier` (combat) | 状態異常の種類・値・期限 | 不変 | — | `domain/combat/value_object/` | ○ (列挙だけ実体あり) |
| `Intent` | ツール呼び出しの意図 | 不変 | 名前など | `domain/intent/value_object/intent.py` | ○ (失敗したツール呼び出しの観測を作るときだけ。`phase_b.py:494`) |

### 1-3. 状態を持つ domain の「サービス」

| 名前 | 持つもの | 置き場所 | run |
|---|---|---|---|
| `PlayerOutcomeRegistry` | プレイヤーごとの終局 (UNRESOLVED / DEAD / EJECTED …)、変化時のコールバック | `domain/player/service/player_outcome_registry.py` | ◎ |

ドメインサービスの名前なのに中身が変わる状態を持つ。集約になっていない **[確認]**。

### 1-4. 休眠中の文脈 (guild、quest、shop、sns、trade、skill)

- **[確認]** `world_runtime.py` は guild・quest・shop を import しない。2 シナリオの runtime を組んで数えると、guild・quest・shop は列挙型しか無い。
- **[確認]** sns: `PostAggregate` 20 個・`UserAggregate` 6 個などが生きている。これは `InMemoryDataStore.__init__` が毎回 `_setup_sample_data()` で見本データを入れるため (`infrastructure/repository/in_memory_data_store.py:131`)。runtime は `public_sns_enabled` のシナリオを起動時に断る (`world_runtime.py` `PublicSnsNotSupportedError`)。今の 2 シナリオでは使われていない。
- **[確認]** trade: `MarketBoard` が 1 つ、空のまま作られる。2 シナリオとも商人・市場を宣言していない。
- **[確認]** skill: `MonsterAggregate.create` が `SkillLoadoutAggregate` を必須にしている。mine_village でモンスターが出現すると作られる。プレイヤー側の技能は使われていない **[推測]**。

---

## 2. 世界の snapshot に入る状態と、その持ち主

登録順は `application/being/experiment_snapshot_session.py:213-259`。codec は `application/being/world_subsystems/`。

| キー | 中身 | 読み書きする持ち主 | 書き戻し方 |
|---|---|---|---|
| `public_sns` | 公開 SNS の保存先・画面・投影、`_execution_turns` | runtime の属性 | 属性に代入 |
| `player_beings` | プレイヤー ↔ Being | `PlayerBeings` | `replace_with` |
| `world_tick` | 現在の tick | `InMemoryGameTimeProvider` | `set_current_tick` |
| `player_position` | 各プレイヤーの現在スポット | `SpotGraphAggregate._entity_spot` / `_presences` | **集約の private dict を直接書き換える** (`player_position_codec.py:72-101`)。イベントを出さない |
| `player_vitals` | HP・MP・スタミナ・ゴールド・ダウン | `PlayerStatusAggregate` | `agg._hp = ...` など private 属性へ直接代入 (`player_vitals_codec.py:83-99`) |
| `player_outcome` | 終局 | `PlayerOutcomeRegistry` | `replace_all` |
| `fallen_body` | 倒れた身体 (誰・どこ・いつ) | `FallenBodyRegistry` (application) | 置き換え |
| `departed_position` | 退場した人の居場所 | `DepartedPositionStore` (application) | `replace_all` |
| `player_needs` | 欲求 | `PlayerStatusAggregate._needs` | 直接代入 |
| `player_inventory` | 枠・装備・押さえたアイテム | `PlayerInventoryAggregate` | private を読む (`inv._reserved_item_ids`) |
| `player_growth` | 能力値・成長係数・経験値表・成長 | `PlayerStatusAggregate` | 直接代入 |
| `player_state_dict` | 自由 state | `PlayerStatusAggregate._state` | 直接代入 (検証を通らない) |
| `world_flags` | フラグ集合 (準備・同期行動の印を含む) | `MutableWorldFlagState` (application) | 置き換え |
| `scenario_event_progress` | 発火済みと予約中の出来事 | `InMemorySpotGraphScenarioEventProgressStore` (application) | private `_scheduled` を読む |
| `scenario_predicate_rng` | 確率条件の乱数の位置 | runtime の `random.Random` | setstate |
| `exploration_progress` | (プレイヤー, スポット) → 探索回数 | `InMemorySpotExplorationProgressStore` (application) | 置き換え |
| `spot_interior` | 地面のアイテム、物体の state・見えるか・パズル・詳細を読んだ人、見つかったか、隠れているか | `SpotInterior` (保存先 `_data` を private で列挙) | シナリオの初期値に動的な欄だけ重ねる |
| `item_instance` | 全アイテム個体の仕様 ID・数量・耐久・state | `ItemAggregate` | 無い個体は仕様から作り直し、`inst._quantity` などへ直接代入。採番器も進める |
| `player_active_effects` | 状態異常 | `PlayerStatusAggregate._active_effects` | 直接代入 |
| `player_attention_level` | 注意の水準 | 同上 | 直接代入 |
| `player_spot_navigation_state` | 移動の途中状態 | 同上 | 直接代入 |
| `weather` | 天候と天候用の乱数位置 | runtime の `_current_weather` (dict) と `SpotGraphEnvironmentStageService._random` | 置き換え |
| `day_night` | 昼夜の段 | `SpotGraphDayNightStageService._current` | tick から計算し直して直接代入 |
| `recent_event_store` (短期記憶 codec) | 未処理の観測と直近の行動の結果 | `UnifiedRecentEventStore` (application) | 置き換え |
| `encounter_memory` | 初対面・再会・初訪問・再訪の記録 | `InMemoryEncounterMemory` (application) | 置き換え |
| `pending_food_spoilage` | 日次でまとめる前の腐敗通知 | runtime の `_pending_spoiled` / `_pending_spoiled_day` | 属性に代入 |
| `distant_cue_state` | 遠景の手がかりの境界検出 | runtime の `_distant_cue_states` | 属性に代入 |
| `game_phase` | 現フェーズ・履歴・使った緊急ボタン・報告済みの死体 | `GamePhaseStore` (application) | `replace_all` |
| `interaction_cooldown` | 行為の最後の成功 tick (人ごと・世界共通) | `InteractionCooldownStore` (application) | `replace_all` |
| `pending_trade_offer` | 返事待ちの取引提案 | `InMemoryPendingTradeOfferStore` (application) | 置き換え |
| `market_board` | 板の注文と直近の約定 | `InMemoryMarketBoardStore` (application) | 置き換え |

### 2-1. 中身が変わるのに snapshot に入らないもの **[確認: 対応する codec が無い]**

| 状態 | 持ち主 | 変える経路 | 再開後どうなるか |
|---|---|---|---|
| 接続の `Passage` の状態 (扉の開閉・障壁) | `SpotGraphAggregate._connections_by_id` | 作用・シナリオの出来事・同期行動 (`spot_interaction_application_service.py:1324`、`spot_graph_scenario_event_stage_service.py:344`、`synchronized_action_resolver_stage_service.py:281`)、反応する束縛 | 束縛で決まる接続は次の tick にフラグから決め直される (`reactive_passage_binding_stage_service.py`)。束縛の無い接続は初期状態に戻る **[推測]** |
| スポットの雰囲気 (停電など) | `SpotNode.atmosphere` | `update_spot_atmosphere` (作用・出来事) | 初期値に戻る **[推測]** |
| 動的に作った/壊した接続 | `SpotGraphAggregate` | `add_connection_dynamic` / `remove_connection` | 初期の接続に戻る **[推測]** |
| モンスター個体 (HP・生死・行動状態) と居場所 | `MonsterAggregate`、`SpotGraphAggregate._monster_spot` | 行動の tick、攻撃 | 初期構築に戻る。`docs/game/world_architecture.md` が制限として明記 |
| 倒れた人が死ぬまでの猶予の開始 tick | `PlayerDeathGraceTimer._downed_at` (`application/player/services/player_death_grace_timer.py:35`) | ダウン時に `register` | 再開時に倒れていた人の猶予が数えられない **[推測。読み直しで作り直す経路は見つけていない]** |
| ダウンに至った出来事の記録 | `DownedIncidentLog._entries` | ダウン時 | 失われる |
| 会議の票 | `GamePhaseStore._ballots` | `cast_vote` | 会議の途中で保存すると票が消える。`game_phase_codec.py` は `ballots` を書かない |
| 戦闘・ドロップ・モンスター行動の乱数位置 | `world_random(..., "attack"/"loot"/"monster_behavior")` (`world_runtime.py:4493,5435,5447`) | 各段 | 再開後は種からやり直す |
| `runtime._tick` | runtime の属性 | `advance_tick` で時間の提供元から写す (`world_runtime.py:830`) | 読み直し直後から次の `advance_tick` までは 0 のまま **[推測。読み直し後に同期する行は見つけていない]**。`_compute_tick_budget_remaining` と終了判定が読む (`world_runtime.py:1465,3578,3673`) |

---

## 3. 不変条件

「守り方」: ドメイン例外 / 組み込み例外 / 黙って補う (丸める・何もしない・別の経路へ逃がす) / 守っていない。
「分類」: ドメインの規則 / シナリオの宣言を確かめているだけ / 実装の都合。

### 3-1. 場所と移動

| 規則の文 | どこで | 守り方 | 層 | 分類 |
|---|---|---|---|---|
| スポット ID は世界に 1 つ | `spot_graph_aggregate.py:162` | ドメイン例外 `DuplicateSpotException` | domain | シナリオの宣言を確かめている |
| 接続 ID は重複しない、両端は登録済みのスポット | `spot_graph_aggregate.py:215-217, 255-257` | ドメイン例外 | domain | シナリオの宣言 (動的追加では実装の都合も) |
| 双方向の接続には逆向きの ID が要る | `spot_graph_aggregate.py:221, 261` | **組み込み例外** `ValueError` | domain | 実装の都合 |
| 所要 tick は 0 以上 | `spot_connection.py:38` | ドメイン例外 | domain | シナリオの宣言 |
| 1 人のプレイヤーは同時に 1 つのスポットにだけ居る | `spot_graph_aggregate.py:294`、`spot_presence.py:25,32` | ドメイン例外 | domain | ドメインの規則 |
| 移動は今いるスポットを始点とする接続に沿う | `spot_graph_aggregate.py:409-415` | ドメイン例外 `EntityNotAtSpotException` | domain | ドメインの規則 |
| 閉じた接続・条件 (鍵・フラグ) を満たさない接続は通れない | `spot_graph_aggregate.py:416-418` → `spot_graph_navigation_service.py:69-82` | ドメイン例外 `ConnectionNotPassableException` | domain (判定はドメインサービス、持ち物とフラグは呼び出し側が渡す) | ドメインの規則 |
| テレポートは通行条件を見ない。同じスポットへは何もしない | `spot_graph_aggregate.py:363-371` | 黙って何もしない | domain | ドメインの規則 |
| 移動中はサブロケーションを変えない | `player_spot_navigation_state.py:82` | ドメイン例外 | domain | ドメインの規則 |
| 経路は 2 スポット以上、区間と接続と所要 tick の数が揃う | `player_spot_navigation_state.py:60-67` | ドメイン例外 | domain | 実装の都合 |
| 移動中の人をテレポートさせない | `spot_graph_aggregate.py` の `teleport_entity` docstring | **守っていない** (呼び出し側の責任と書いてあるだけ) | — | ドメインの規則 |
| モンスターは同時に 1 か所、二重索引が一致する | `spot_graph_aggregate.py:98-122, 743, 764` | ドメイン例外 | domain | 実装の都合 (索引が 2 つあるため) |
| 生きていないモンスターは動かない | `move_monster` docstring | **守っていない** (呼び出し側の責任と明記) | — | ドメインの規則 |
| 追放された人はグラフから外れる | `world_runtime.py:2477-2516`、`meeting_command_service.py:224` | application が `unplace_entity` を呼ぶ。失敗はログだけ | application (2 か所に重複) | ドメインの規則 |

### 3-2. プレイヤーの身体と生死

| 規則の文 | どこで | 守り方 | 層 | 分類 |
|---|---|---|---|---|
| HP・MP・スタミナ・ゴールドは 0 以上、上限以下 | `hp.py:21-27`、`gold.py:18`、`stamina.py:20-28` | ドメイン例外 (生成時)。増減は `create` で丸める | domain | ドメインの規則 |
| 欲求は 0〜上限 | `agent_need.py:43,45` | **組み込み例外** `ValueError`。増減は丸める | domain | ドメインの規則 |
| HP が 0 になったらダウンする | `player_status_aggregate.py:438-449` | 集約の操作の中で状態を変える | domain | ドメインの規則 |
| ダウン中は MP・ゴールド・スタミナを使えず、経験値を得ず、話せない | `player_status_aggregate.py:474, 535, 605, 633, 665, 781` | ドメイン例外 `PlayerDownedException` | domain | ドメインの規則 |
| ダウン中は回復しない | `player_status_aggregate.py:509` | 黙って何もしない | domain | ドメインの規則 |
| ダウン中は欲求が進まない | `player_status_aggregate.py:215-216` | 黙って何もしない | domain | ドメインの規則 |
| 足りない MP・スタミナ・ゴールド・HP は使えない | `player_status_aggregate.py:538, 608, 636, 668-676` | ドメイン例外 | domain | ドメインの規則 |
| ダウンしていない人は蘇生できない | `player_status_aggregate.py:739` | ドメイン例外 | domain | ドメインの規則 |
| 疲労・欲求の量が 0 以下なら何もしない。宣言の無い欲求は無視 | `player_status_aggregate.py:198-208, 366-376` | 黙って補う | domain | 実装の都合 |
| 自由 state の値は JSON の素の値だけ | `player_status_aggregate.py:59-72` | ドメイン例外 | domain | 実装の都合 (保存のため) |
| 終局は 1 度だけ決まり、上書きしない | `player_outcome_registry.py:74-79` | 黙って何もしない (`False` を返す) | domain (サービス) | ドメインの規則 |
| 倒れた身体は 1 人 1 件、最初の場所を保つ | `application/player/services/fallen_body_registry.py:27-40` | 黙って既存を返す | application | ドメインの規則 |
| 退場した人の居場所は、置いてからでないと動かせない | `departed_position_store.py:25` | 組み込み例外 | application | 実装の都合 |
| 全員が終局済みか倒れていればゲームが終わる | `world_runtime.py:3652-3664` | application が値を取り出して判断 | application | ドメインの規則 |
| 1 人のプレイヤーを動かす Being は 1 つ (逆も) | `player_beings.py:54-82` | ドメイン例外 | domain | ドメインの規則 |

### 3-3. アイテムと持ち物

| 規則の文 | どこで | 守り方 | 層 | 分類 |
|---|---|---|---|---|
| 数量は 0 以上・スタック上限以下 | `item_instance.py:70-74, 218-262` | ドメイン例外 | domain | ドメインの規則 |
| 耐久を持つ品はスタック 1、耐久の最大は仕様と一致 | `item_instance.py:76-86` | ドメイン例外 | domain | シナリオの宣言 |
| 品の state は JSON の素の値だけ | `item_instance.py:28-36` | ドメイン例外 | domain | 実装の都合 |
| 仕様: 名前・説明が空でない、消費効果は CONSUMABLE だけ、装備品は装備種別 … | `item_spec.py:67-114` | ドメイン例外 | domain | シナリオの宣言 |
| 腐る品は、手に入れた tick から閾値を過ぎたら腐る | `item_aggregate.py:135-172` | 集約の操作 | domain | ドメインの規則 |
| 持ち物が満杯なら入らない | `player_inventory_aggregate.py:343-351` | 黙って補う: 例外ではなく溢れたイベントを出し、application が足元へ落とす (`_ground_overflow_sink`) | domain + application | ドメインの規則 |
| 押さえた品は動かせない・捨てられない・置けない・装備できない | `player_inventory_aggregate.py:378, 397, 417, 434, 448, 461, 479` | ドメイン例外 | domain | ドメインの規則 (取引) |
| 枠番号は範囲内 | `player_inventory_aggregate.py:608, 622` | ドメイン例外 | domain | 実装の都合 |
| 地面に同じ個体を二重に置かない | `spot_interior.py:79-96` | 黙って何もしない | domain | 実装の都合 (再試行への備えと docstring) |
| 渡す相手は自分でなく、死んでおらず、倒れておらず、同じスポットに居る | `spot_graph_item_transfer_service.py:551-580` | application の例外 | application | ドメインの規則 |
| 1 つの品は、どこか 1 か所 (誰かの持ち物か、どこかの地面) にだけある | 見つからない | **守っていない [推測]**。持ち物は `PlayerInventoryAggregate`、地面は `SpotInterior.ground_items`、本体は `ItemAggregate` と 3 か所に分かれ、まとめて確かめる型が無い | — | ドメインの規則 |
| 作用で消す品が足りなければ全体を取り消す | `spot_interaction_service.py:956`、`spot_interaction_application_service.py:1404-1418` | ドメイン例外 → application 例外 | 両方 | ドメインの規則 |

### 3-4. 物体・作用・フラグ・出来事

| 規則の文 | どこで | 守り方 | 層 | 分類 |
|---|---|---|---|---|
| 物体の名前は空でない | `spot_object.py:76` | ドメイン例外 | domain | シナリオの宣言 |
| 物体の state の値の型 | 無し | **守っていない [確認]** (`with_state` は dict をそのまま入れる。プレイヤーと品の state は検証している) | — | 実装の都合 |
| 置き換える物体・サブロケーションは存在する | `spot_interior.py:35-36, 45-46` | 物体はドメイン例外、サブロケーションは **組み込み例外** | domain | 実装の都合 |
| パズルの種類と正解は空でない | `puzzle_state.py:23,25` | **組み込み例外** | domain | シナリオの宣言 |
| 作用の前提条件を満たさなければ実行しない | `spot_interaction_service.py:782, 883` | ドメイン例外 | domain | ドメインの規則 (条件の中身はシナリオ) |
| 作用の効果 (フラグ・物体・接続・雰囲気・テレポート・ダメージ・品の付与) | 判定は `spot_interaction_service.py` / `world_graph_effect_service.py`、適用は `spot_interaction_application_service.py:1301-1480` | ドメインが「何を変えるか」の仕様を返し、application がそれを読んで各集約を書き換える | 両方 | ドメインの規則 |
| 作用の再使用間隔 | `spot_interaction_application_service.py:466-515`、`interaction_cooldown_store.py:109-111` | application の例外・組み込み例外 | application | シナリオの宣言を実行に移している |
| フラグはただの文字列の集合 | `world_flag_registry.py` | 守るものが無い | domain | — |
| 準備した行動はフラグ `prepared:{action}:{player}` で表す。行動名に `:` を含めない | `prepared_action_registry.py:34-36` | **組み込み例外** | application | 実装の都合 (区切り文字) |
| 同期行動の準備は `sync_prep:{action}:{player}:{tick}` | `synchronized_action_registry.py:65-67` | 組み込み例外 | application | 実装の都合 |
| 出来事は 1 度だけ発火する | `spot_graph_scenario_event_progress_store.py:13-19` | 保存先が覚える | application | シナリオの宣言を実行に移している |
| 終了条件に要る欄がある | `game_end_condition_evaluator.py:78-309` | ドメイン例外。**評価のたびに**確かめる | domain | シナリオの宣言を確かめているだけ |
| シナリオの宣言の検証全般 | `infrastructure/scenario/parse_*.py` (raise が約 350 か所) | 読み込み時の例外 | infrastructure | シナリオの宣言を確かめているだけ |

### 3-5. 会議

| 規則の文 | どこで | 守り方 | 層 | 分類 |
|---|---|---|---|---|
| 会議中にもう一度始めない、会議中でなければ終えない | `game_phase_store.py:231, 251` | ドメイン例外 `GamePhaseTransitionException` (application のクラスが投げる) | application | ドメインの規則 |
| 会議を始めるとき前回の票を捨てる | `game_phase_store.py:236` | 保存先の操作 | application | ドメインの規則 |
| 1 人 1 票、会議中だけ投票できる | `meeting_command_service.py:136-148` | application が失敗の DTO を返す | application | ドメインの規則 |
| 全員が投票したら集計して終える | `meeting_command_service.py:165` | application | application | ドメインの規則 |
| 緊急ボタンは 1 人の回数まで、世界共通の待ち時間 | `game_phase_store.py` の `has_emergency_button` / `is_meeting_on_cooldown` | 保存先の問い合わせ | application | ドメインの規則 |
| 同じ死体で 2 度会議を開かない | `game_phase_store.py` の `is_body_reported` | 保存先の問い合わせ | application | ドメインの規則 |

### 3-6. モンスター

| 規則の文 | どこで | 守り方 | 層 | 分類 |
|---|---|---|---|---|
| 出現中にもう一度出現しない | `monster_aggregate.py:401` | ドメイン例外 | domain | ドメインの規則 |
| 生きているときだけ傷つく・回復する・攻撃を記録する | `monster_aggregate.py:434-435, 692, 698, 717, 736, 817-818` | ドメイン例外 | domain | ドメインの規則 |
| 未出現は「DEAD で最後に死んだ tick が無い」で表す | `monster_aggregate.py:122-124, 433-434` | 状態の組み合わせで表す | domain | 実装の都合 |
| 空腹は 0〜1 | `monster_lifecycle_state.py:36` | ドメイン例外 | domain | ドメインの規則 |
| 死んだモンスターはグラフから自動では外れない | `spot_attack_orchestrator.py:281` のコメント | 呼び出し側 | application | — |

---

## 4. CLAUDE.md の集約の決まりから外れているもの

決まり: (a) ID を持ち中身が変わる、(b) 状態を変える操作は値を返さない、(c) ID を持つ集約を frozen にしない、(d) application が値を取り出して分岐しない。

### (a)(c) ID が無い・frozen で、中身が丸ごと差し替えられるもの **[確認]**

- `SpotInterior`: 地面のアイテム・物体の状態という、世界でいちばん頻繁に変わる状態を持つのに frozen の値で、ID を持たない。保存先がスポット ID をキーに持ち、application が `save(spot_id, new_interior)` で差し替える。
- `SpotNode`・`SpotConnection`: frozen。集約の中で `replace` して差し替える。集約の中の部品なので決まりの直接の対象ではないが、`SpotObject.state: dict` と `SpotConnection.passage_conditions: list` は frozen なのに中身を書き換えられる。
- `SpotNode.interior` と `ISpotInteriorRepository` の二重化: シナリオ読込は `SpotNode.interior=None` で作り、中身は別の保存先に入れる。表示側は両方を見る (`application/observation/services/formatters/_spot_graph_formatter_helpers.py:69-83`)。
- `PlayerStatusAggregate` と `PlayerInventoryAggregate` が同じ `PlayerId` を ID にしている。

### (b) 状態を変えて値を返す操作 **[確認]**

- `SpotGraphAggregate.set_connection_passage(_state)` → `bool`
- `PlayerStatusAggregate.apply_needs_decay_tick` → `NeedsDecayTickResult`
- `PlayerInventoryAggregate.reserve_item` → `ItemInstanceId`、`remove_item_for_placement` → `ItemInstanceId` (しかもイベントを出さない)
- `ItemAggregate.advance_spoilage` → `SpoilageAdvanceResult`、`ItemInstance.use` → `bool`
- `MonsterAggregate.tick_chase_search_timer` → `bool`
- `PlayerOutcomeRegistry.set_outcome` → `bool`
- application の保存先: `GamePhaseStore.begin_meeting/end_meeting` → `GamePhaseState`、`FallenBodyRegistry.record` → 記録、`PreparedActionRegistry.prepare` → フラグ名、`InMemorySpotExplorationProgressStore.increment_and_get` → 回数

### (d) application が値を取り出して判断している箇所 (代表) **[確認]**

- 作用の結果の適用: `SpotInteractionService` が「何を変えるか」の仕様の束 (`new_flags`、`passage_state_updates`、`teleport_specs`、`atmosphere_update_specs`、`destroy/create_connection_specs`、`damage_specs` …) を返し、`spot_interaction_application_service.py:1301-1480` が 1 つずつ読んで、フラグ・`SpotInterior`・グラフ・持ち物・状態の集約を書き換える。docstring に「以前は消費者が居らず dead code だった」が 3 回出てくる。仕様を返す形が、適用漏れを静かな失敗にしやすい。
- 生死: `world_runtime.py:3652-3664` が終局の値と `is_down` を取り出して「全員動けない」を判断する。`spot_graph_item_transfer_service.py:497-501` は `getattr(status, "is_down", False)`。
- 追放: `world_runtime.eject_player` (`:2477`) と `meeting_command_service.py:224` が同じ後始末 (`unplace_entity`) を別々に持つ。`unplace_entity` の docstring は「テストや管理用途。本番ロジックでは move_entity を使うこと」と書いてある。
- 投票の規則 (会議中か、投票済みか) を application が分岐して DTO を返す (`meeting_command_service.py:136-148`)。
- 発言: `player_speech_service.py:101-124` が「倒れていて退場扱いか」で分岐し、退場者のときは集約の `speak` を通さず `status.add_event(PlayerSpokeEvent...)` で外からイベントを積む。
- snapshot の codec が集約の private 属性を直接書き換える (`agg._hp = ...`、`graph._entity_spot[...] = ...`、`inst._quantity = 0`)。「コンストラクタを通すと不変条件チェックが入りうるので、すり替える」と書いてある (`player_vitals_codec.py:80-82`)。読み直しでは不変条件が確かめられない。

### ドメイン層で組み込み例外を投げている箇所 **[確認]**

`grep "raise (ValueError|TypeError|KeyError|RuntimeError)"` の件数: `world/value_object/game_date_time.py` 9、`player/value_object/agent_need.py` 4、`world_graph/event/spot_graph_event.py` 3、`world/service/world_time_config_service.py` 3、`monster/value_object/spot_spawn_table.py` 3、`world_graph/value_object/trap_def.py` 2、`puzzle_state.py` 2、`spot_interaction_service.py` 2、`spot_graph_aggregate.py` 2、ほか 1 件ずつ (`discovery_condition.py`、`world_graph_effect_service.py`、`trap_evaluation_service.py`、`spot_interior.py`、`world/value_object/time_of_day.py`、`item/value_object/item_effect.py`)。

---

## 5. 状態を持っているのに集約になっていないもの

### 5-1. `WorldRuntime` の属性 (`application/world_runtime/world_runtime.py:485-680`)

| 属性 | 中身 | snapshot |
|---|---|---|
| `_current_weather` | `{"state": WeatherState}` の dict | 入る |
| `_tick` | 時間の提供元の写し | 入らない (提供元は入る) |
| `_pending_spoiled` / `_pending_spoiled_day` | 日次でまとめる腐敗通知 | 入る |
| `_distant_cue_states` | 遠景の手がかりの境界状態 (dict の dict) | 入る |
| `_execution_turns` | プレイヤーごとの実行ターン数 | 入る (SNS の codec の中) |
| `_scenario_predicate_random` | 確率条件の乱数 | 入る |
| `_meeting_enabled` | 会議を使うか (シナリオ由来) | 不要 |
| `_cumulative_travel_ticks_by_player` / `_cumulative_meeting_ticks` | trace 用の集計 | 入らない (観測値とコメントあり) |

### 5-2. application の保存先・登録簿 (中身が変わる世界の状態)

| クラス | 中身 | 置き場所 |
|---|---|---|
| `MutableWorldFlagState` | フラグ集合 (準備・同期行動の印もここに文字列で入る) | `application/world_graph/world_flag_state.py` |
| `GamePhaseStore` | フェーズ・履歴・緊急ボタン・報告済み死体・票 | `application/world_graph/game_phase_store.py` |
| `InteractionCooldownStore` | 行為の最後の成功 tick | `application/world_graph/interaction_cooldown_store.py` |
| `InMemorySpotExplorationProgressStore` | 探索回数 | `application/world_graph/spot_exploration_progress_store.py` |
| `InMemorySpotGraphScenarioEventProgressStore` | 発火済み・予約中の出来事 | `application/world_graph/spot_graph_scenario_event_progress_store.py` |
| `PreparedActionRegistry` / `SynchronizedActionRegistry` | 状態はフラグに書く (自分では持たない) | `application/world_graph/` |
| `FallenBodyRegistry` | 倒れた身体 | `application/player/services/fallen_body_registry.py` |
| `DepartedPositionStore` | 退場者の居場所 | `application/player/services/departed_position_store.py` |
| `PlayerDeathGraceTimer` | 倒れた tick | `application/player/services/player_death_grace_timer.py` |
| `DownedIncidentLog` | ダウンに至った出来事の文 | `application/player/services/downed_incident_log.py` |
| `InMemoryEncounterMemory` | 初対面・再訪の記録 (プレイヤーごと) | `application/encounter/in_memory_encounter_memory.py` |
| `UnifiedRecentEventStore` | 未処理の観測・直近の行動の結果 | (短期記憶の codec が保存) |
| `InMemoryPendingTradeOfferStore` / `InMemoryMarketBoardStore` | 取引提案・板 | `application/trade/services/` |
| `SpotGraphDayNightStageService._current` | 現在の昼夜の段 | `application/world_graph/spot_graph_day_night_stage_service.py` |
| `SpotGraphEnvironmentStageService._random` | 天候の乱数 | `application/world_graph/spot_graph_environment_stage_service.py` |

### 5-3. domain のサービスが持つ状態

- `PlayerOutcomeRegistry` (`domain/player/service/`)。

### 5-4. 1 つの事実が何か所にもある

**[確認]** プレイヤーの居場所は次の 5 か所にある。

1. `SpotGraphAggregate._entity_spot` (表示・移動・配信が「唯一の真実源」として読む。`spot_graph_item_transfer_service.py:570-572` のコメント)
2. `PlayerSpotNavigationState.current_spot_id` (移動の段が進める)
3. `PlayerStatusAggregate._current_spot_id`。コンストラクタで出現スポットを入れたあと、**書き換える操作が無い**。それなのに `player_speech_service.py:92,123` が `PlayerSpokeEvent.spot_id` に入れ、`shop_command_service.py:111`、`quest_command_service.py:159`、`player_audience_query_service.py:73` (グラフが無いとき) が読む。今の観測の整形は `event.spot_id` を読まないので、表には出ていない **[確認: player_formatter と speech の受け手の解決はグラフを読む]**
4. `DepartedPositionStore` (退場者)
5. `FallenBodyRegistry` (倒れた場所)

**[確認]** モンスターの居場所は `MonsterAggregate._spot_id` と `SpotGraphAggregate._monster_spot` の 2 か所にある。`_spot_id` は出現時 (`_initialize_status`) にしか書かれない。`move_monster` は集約を変えない (`spot_monster_behavior_tick_service.py:27` に明記)。そのため `MonsterDiedEvent.spot_id` は出現スポットになる (`monster_aggregate.py:781`)。観測の受け手は、死亡イベントの `spot_id` を優先する (`monster_recipient_strategy.py:150`)。歩き回ったあとに死ぬと、**出現スポットの人に死が届く [推測。歩き回る設定のモンスターで実際に起きるかは試していない]**。

**[確認]** 生死は 5 か所にある: `PlayerStatusAggregate._is_down`、`PlayerOutcomeRegistry` (DEAD/EJECTED)、`FallenBodyRegistry`、`PlayerDeathGraceTimer`、`DepartedPositionStore`。読むときは `PlayerLifeQuery` と `PlayerPerceptionPolicy` (application) が組み合わせる。

**[確認]** tick は `InMemoryGameTimeProvider` と `WorldRuntime._tick` の 2 か所にある。

---

## 6. コードで使われている言葉

### 6-1. ドメインの語彙の候補 (今の run で使われているもの)

世界・スポット (Spot)・エリア (area)・サブロケーション (SubLocation)・接続 (Connection)・通り道 (Passage: 開口・壁・扉・障壁)・通行条件 (PassageCondition)・雰囲気 (Atmosphere: 明るさ・気温・危険度・環境音)・物体 (SpotObject)・作用 (Interaction: 前提条件と効果)・地面のアイテム (GroundItem)・見つかるアイテム (DiscoverableItem)・罠 (Trap)・パズル (Puzzle)・フラグ (WorldFlag)・出来事 (ScenarioEvent)・反応する束縛 (ReactiveBinding)・続いている状況 (OngoingCondition)・同期行動 (SynchronizedAction)・準備 (prepare)・遠景の手がかり (DistantCue)・天候・昼夜の段 (phase)・tick・プレイヤー・ダウン (down)・死 (DEAD)・追放 (EJECTED)・退場 (departed)・倒れた身体 (fallen body)・終局 (outcome)・欲求 (need: 空腹・疲労)・持ち物 (inventory)・品の仕様 (ItemSpec)・品の個体 (ItemInstance)・腐敗 (spoilage)・会議 (meeting)・票 (ballot)・緊急ボタン・死体の報告・陣営 (team)・役割 (role)・モンスター・出現 (spawn)・追跡 (chase)・逃走 (flee)・探索 (explore)・聞き耳 (listen)・発言・囁き (speech / whisper)・再使用間隔 (cooldown)。

### 6-2. 同じものを別の名前で呼んでいる箇所 **[確認]**

| もの | 名前 |
|---|---|
| グラフ上のプレイヤー | `PlayerId`、`EntityId` (`EntityId.create(int(player_id))`)、世界 snapshot の `player_id`、Being 側の `BeingId`、表示の名前。`EntityId` はプレイヤー専用で、モンスターは `MonsterId` |
| 品の個体 | `ItemAggregate` と、その中の `ItemInstance`。codec の名前は `item_instance`、保存先は `InMemoryItemRepository` |
| 場所 | Spot、SpotNode、Location (`LocationAreaId`・`LocationEstablishment`)、area、room (`_room_occupancy_message`)、`SpotPosition`、旧 `Coordinate` |
| 物体 | `SpotObject`、旧 `WorldObjectId` (モンスターの `behavior_target_id`・`attacker_id` に残る)、旧 `ObjectTypeEnum` |
| 時刻 | `TimeOfDay` が 2 つある: `domain/world/value_object/time_of_day.py` (朝・昼・夕・夜の Enum。モンスターの活動時間と SQLite codec が使う) と `domain/world_graph/value_object/time_of_day.py` (tick から計算する時刻のスナップショット)。ほかに `GameDateTime`、`WorldTick`、`int` の tick |
| 段階・フェーズ | `GamePhase` (自由時間/会議)、昼夜の `phase_name`、`IntentPhase`、ターンの Phase A / B |
| 倒れた/死んだ | `is_down` / downed、`DEAD`、`is_eliminated`、`departed`、`fallen body`、死体 (corpse)、モンスターの `MonsterStatusEnum.DEAD` (未出現も DEAD) |
| 状態 | `state` が 4 種類: `SpotObject.state`、`ItemInstance.state`、`PlayerStatusAggregate._state` (自由 state)、`Passage` の state。ほかに `*_state` の値オブジェクト多数 |
| 天候 | `WeatherState`、`WeatherZone` (未使用)、環境の段 (`SpotGraphEnvironmentStageService`)、シナリオの `environment.weather` |
| 世界の識別子 | `WorldId` (`PlayerBeings`)、`SpotGraphId` (グラフ集約)、Being 側の環境の識別子 (D1928-2) |
| 終わり方 | `GameEndCondition` の win/lose/end、`GameResultEnum`、`PlayerOutcomeEnum`、`PlayerOutcomeRule` |
| 置き場所の言葉 | `Store`、`Registry`、`Repository`、`Log`、`Timer`、`Memory` が、どれも「中身が変わる状態の入れ物」に使われている |

---

## 7. 分からなかったこと、食い違い

### 7-1. 食い違い

1. **[確認]** `SpotGraphAggregate.unplace_entity` の docstring は「テストや管理用途。本番ロジックでは使わない」と言うが、追放の本番経路が 2 か所で使っている。
2. **[確認]** `PlayerStatusAggregate.current_spot_id` は出現スポットのまま更新されない。`spot_graph_item_transfer_service.py:571` のコメントは「tile-map 由来で更新されない」と書くが、発言のイベントは今もこの値を入れている。
3. **[確認]** `MonsterAggregate.spot_id` は移動で更新されない (上記 5-4)。
4. **[確認]** 品と人の state は JSON の素の値に限るが、物体の state は確かめていない。
5. **[確認]** snapshot の codec は、snapshot に無い欄の扱いが揃っていない。`spot_interior` はシナリオに無いスポットを info ログで飛ばす。`player_vitals` は居ないプレイヤーを黙って飛ばす。`player_position` はスポットが無ければ止める。
6. **[確認]** `docs/game/world_architecture.md` は「世界 snapshot にはモンスターの HP・行動状態・位置の codec が無い」と書いている。接続の状態・雰囲気・動的接続・猶予タイマー・票・一部の乱数も入っていないが、文書には書かれていない (2-1)。
7. **[確認]** `PlayerStatusAggregate.apply_damage` は、もう倒れている人がさらに傷を受けても、もう一度 `PlayerDownedEvent` を積む (`player_status_aggregate.py:441` は「HP が 0」だけを見て、前から倒れていたかを見ない)。欲求の tick は倒れた人を飛ばすが、ほかの経路 (接触ダメージの作用など) では二重に出る **[推測]**。
8. **[確認]** `PlayerBeings` の docstring は「#1339 で環境を集約にし直すときに、環境の集約に移す」と書いており、今は暫定の置き場所。

### 7-2. 分からなかったこと

- 動かす前の 5 tick だけを数えたので、エージェントの行動で初めて作られる型 (モンスター個体・技能・ドロップ表の使用・取引) が実際の run で作られるかは、trace を見ていない。`var/runs/` の trace は確かめていない。
- `PlayerDeathGraceTimer` を読み直しのあとに倒れた身体から作り直す経路が別の場所にあるか。`application/being/` には無かった。
- `runtime._tick` が読み直し直後に同期されるか。`experiment_snapshot_session.py` に `_tick` を書く行は無かった。
- 束縛を持たない接続の状態が変わるシナリオが、今の 2 つにあるか (作用の `CHANGE_PASSAGE` 系の宣言を数えていない)。
- 品が「持ち物か地面のどちらか 1 か所だけ」にあることを保証する検査が、テストや application のどこかにあるか。domain には無かった。
- `ScenarioLoadResult` が `SpotGraphAggregate` を infrastructure (`infrastructure/scenario/`) で組み立てている。シナリオの宣言の検証がドメインに無く infrastructure に約 350 か所あることを、環境とシナリオの作り直しでどう扱うか。
