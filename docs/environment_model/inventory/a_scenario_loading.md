# A. シナリオの読み込みが今していること

調べた版: origin/main `21a33e4c9`。読むだけで、リポジトリは書き換えていない。

## 読み方

- パスの略記: `L/` = `src/ai_rpg_world/infrastructure/scenario/`、`D/` = `src/ai_rpg_world/domain/`、`RT` = `src/ai_rpg_world/application/world_runtime/world_runtime.py`
- 行番号は上の版のもの
- **[確認]** はコードを読んだか、手元で読み込みを実行して確かめた事実。**[推測]** は確かめていない見立て
- 実行による確認は、最小のシナリオを `ScenarioLoader().load_from_dict` に通す使い捨ての調査スクリプトで行った (スクリプトは残していない)。実 LLM は呼んでいない

## 0. 全体の形 [確認]

```
data/scenarios/*.json
  └─ ScenarioLoader.load_from_file(path, random_seed, round_number)   L/scenario_loader.py:152
       └─ load_from_dict(raw)                                          L/scenario_loader.py:164-357
            ├─ 書式の版の確認と、廃止キーの拒否
            ├─ round_assignment を生の JSON に書き込む (以降はこの JSON を読む)
            ├─ ScenarioIdMapper を作り、文字列 ID → 連番の整数を名前空間ごとに振る
            ├─ parse_* がキーごとにドメインの値オブジェクト・エンティティ・集約へ変換
            ├─ キーをまたぐ検査 (reject_unreachable_* / validate_*)
            └─ ScenarioLoadResult (frozen dataclass、45 欄) にまとめ、
               validate_feature_consistency で組合せを検査して返す
  └─ create_world_runtime(scenario_path, ...)                          RT:4047
       ├─ ScenarioLoader().load_from_file(...)                          RT:4100-4104
       ├─ ScenarioLoadResult の欄を、リポジトリ・サービス・プロンプト部品へ配る
       └─ WorldRuntime(scenario=scenario, ...)                          RT:5727 / 6770
            WorldRuntime は ScenarioLoadResult 全体を self.scenario として持ち続け、
            tick の中でも直接読む (終了判定 RT:3683-3760、disabled_tools RT:1535 など)
```

- 読み込みは 1 回きりで、結果は不変の DTO (`ScenarioLoadResult`) である。ただし中に可変の集約 `SpotGraphAggregate` と `ScenarioIdMapper` を抱えている (L/models.py:488-498)
- `ScenarioLoadResult` は infrastructure の型だが、application の `WorldRuntime`・`ToolExposure`・`being_contract` が直接受け取る

## 1. シナリオが宣言できるもの

実物の 19 本で使われているトップレベルのキーは 31 種。読み込み側が読むキーは次の 36 種 (使われていない `round_assignment`・`public_sns_enabled`・`public_sns_push_budget_chars` と、拒否するだけの `outcome_resolution` を含む)。

| キー | 何を宣言するか | 読む関数 → 型 | 世界の何になるか (create_world_runtime 以降) |
|---|---|---|---|
| `scenario_format_version` | 書式の版。`"1.0"` だけ | scenario_loader.py:171 | 読み込みの可否だけ |
| `metadata` | id, title, description(作者向け), theme, difficulty, estimated_ticks, author, tags, llm_public_intro, llm_objective_text, show_world_map, limits_actions, role_labels, player_outcome_messages | parse_world.py:341 → `ScenarioMetadata` (models.py:44) | system prompt の世界紹介・目的文・地図の有無・「行動の制限」の行、終局の観測文、`EnvironmentEntry.environment_name` (= title) |
| `spots[]` | 場所。id, name, description, category, parent_id, atmosphere, is_outdoor, position, area_id, interior | parse_map.py:62 → `SpotNode` を `SpotGraphAggregate` に追加 | 世界の地図 (`InMemorySpotGraphRepository`) |
| `spots[].interior` | objects / sub_locations / discoverable_items | parse_map.py:349 → `SpotInterior` | 場所の中身 (`InMemorySpotInteriorRepository`) |
| `spots[].interior.objects[]` | 物体。state, interactions, description_variants, is_visible, is_visible_in_dark, unavailable_hint, hidden_state_keys, state_display, object_type | parse_map.py:423 → `SpotObject` | 物体と `interact` の操作 |
| `connections[]` | 道。from, to, name, description, travel_ticks, is_bidirectional, passage, passage_conditions | parse_map.py:520 → `SpotConnection` (+逆向き) | グラフの辺 |
| `areas[]` | 遠景の単位。id, name, visible_name, prominence, position, description(作者向け), distant_descriptions | parse_map.py:139 → `AreaDef` (models.py:196) | 遠景の候補 |
| `distant_cues[]` | 遠くに見える兆候。source(object_state のみ), origin.area_id, visible_name, prominence, ambient_descriptions, appear_event | parse_map.py:214 → `DistantCueDef` | 遠景に混ぜる動的な兆候 |
| `item_specs[]` | 品目。name, description, category, is_light_source, spoils_after_ticks, consume_effect, fatigue_recovery, usage_hint, event_removal_message, interactions | parse_economy.py:424 → `ItemSpecDefinition`、parse_economy.py:301 → `ItemInteractionRegistry` | RT:4236-4262 で `ItemSpec` に変換 (`max_stack_size=1`、`rarity=COMMON`、consume_effect があれば CONSUMABLE、無ければ QUEST) |
| `loot_tables[]` | 抽選表 | parse_economy.py:50 → `ScenarioLootTableDefinition` | `InMemoryLootTableRepository` (RT:4464) |
| `player_attributes` | 人の属性。visibility (public/secret/hidden), mutable, values (配列か 値→呼び名) | parse_economy.py:696 → `PlayerAttributeSpecs` | 自分の状態の表示、伏せるキー |
| `players[]` | 人物。id, name, spawn_spot, initial_items, initial_state, persona_prompt, objective, initial_gold, knows_at_start, appearance, first_person | parse_actors.py:354 → `PlayerSpawnConfig` (models.py:130) | `PlayerStatusAggregate` (RT:4290-4330)、持ち物 (RT:4348)、グラフへの配置 (RT:4355-4359)、Being の `Persona` (RT:6722)、入るときの紹介 `EnvironmentEntry` (RT:6731-6733) |
| `round_assignment` | 回ごとの役と初期配置の枠 | parse_round_assignment.py:31 → 生 JSON を書き換え + `RoundSlotAssignment` | trace の `round_assignment` (RT:700-710) |
| `mutually_known_roles` | 同じ role 同士が仲間と知る | parse_actors.py:44 → `tuple[str]` | 入るときの紹介の「あなたと同じ側」 |
| `role_personas` | role ごとの共通の文 | parse_actors.py:71 → `Mapping[str,str]` | system prompt の人物像の後ろに連結 |
| `teams[]` | チーム。id, name, member_state, win | parse_teams.py:33 → `ScenarioTeam` | 勝敗の判定 (RT:3559-3640, 3708-3722) |
| `game_end_conditions` | win / lose / end | parse_world.py:541 → `GameEndCondition` | 毎 tick の終了判定 (RT:3683-3760) |
| `player_outcome_rules[]` | 個人の結果 (RESCUED / STRANDED) の規則 | parse_scenario_events.py:174 → `PlayerOutcomeRule` | 個人結果の判定 (RT:5578) |
| `initial_flags` | 初めから立っている世界の旗 | scenario_loader.py:247 (`tuple(...)` するだけ) | `WorldFlagRegistry` (RT:4432) |
| `ongoing_conditions[]` | 進行中の異常。flag, message, blocks_emergency_button, resolution, on_meeting_start | parse_world.py:77 → `OngoingConditionDef` | user prompt 末尾の表示、会議での解除 |
| `scenario_events[]` | 世界の側の出来事。trigger, once, conditions, effects, observation, next_event_id, delay_ticks | parse_scenario_events.py:74 → `ScenarioEventDef` | tick ごとの出来事 (RT:5337) |
| `reactive_bindings` | passages / objects。条件の真偽で通路の状態・物体の state を切り替える | parse_reactive_bindings.py:23 / 94 → `ReactivePassageBinding` / `ReactiveObjectStateBinding` | RT:5352 / 5359 |
| `synchronized_action_groups[]` | 二人以上で合わせる操作 | parse_sync_groups.py:67 → `SynchronizedActionGroup` | RT:5366 |
| `player_interactions[]` | 人を対象にする操作 | parse_interactions.py:311 → `InteractionDef` | 対人の操作 |
| `monsters` | templates / initial_placements (spawn_condition 付き) | parse_actors.py:99 → `ScenarioMonsterTemplate` / `ScenarioMonsterPlacement` | 即時配置 (RT:4373-4428)、条件付きは tick ごと (RT:5467-5483) |
| `merchants[]` | NPC 商人 | parse_economy.py:128 → `ScenarioMerchantDefinition` | 売買ツールの露出と商人 |
| `market` | 掲示板の市場 | parse_economy.py:621 → `ScenarioMarketConfig` | RT:4712-4779 |
| `player_trade` | 人同士の取引の有無と提案の期限 | parse_world.py:294 → `bool`, `int|None` | ツールの露出 (`ToolExposure`) |
| `needs` | 空腹・疲労・飢餓の調整値 | parse_economy.py:517 → `ScenarioNeedsConfig` | RT:5395 |
| `environment.weather` | 天候 | parse_world.py:481 → `ScenarioWeatherConfig` | RT:4873 |
| `environment.day_night` | 昼夜 | parse_world.py:399 → `ScenarioDayNightConfig` (`DayNightCycleDef`) | RT:4885、1 tick の分数 (RT:442-454) |
| `meeting` | 会議の有無と調整値 | parse_world.py:323 / 238 | 会議と投票のツール |
| `death` | grace_ticks, announce_globally, victim_learns_killer | parse_world.py:269 → `DeathSemantics` | 死の扱い |
| `departed_agents_enabled` | 死後も別位置で手番を持つ | parse_helpers.py:335 | `PlayerLifeQuery` など |
| `disabled_tools` | この世界で出さないツール | parse_world.py:505 | `ToolExposure` |
| `public_sns_enabled` / `public_sns_push_budget_chars` | 公開 SNS | scenario_loader.py:297-306 | 有効なら起動時に `PublicSnsNotSupportedError` (RT:4105-4111) |
| `outcome_resolution` | 廃止 | scenario_loader.py:176-181 | 書けば拒否 |

実物の例:
- `mine_village_v1.json`: 21 場所、`player_attributes` (team は hidden かつ不変、aboard は hidden で可変)、`teams` 2 つ (`member_state: {"team": ...}`、`win: ALL_MEMBERS_HAVE_OUTCOME RESCUED`)、`game_end_conditions.end: ALL_PLAYER_OUTCOMES_RESOLVED`、`player_outcome_rules` (昇降機の旗で RESCUED / STRANDED)、天候 SNOW と 48 tick の昼夜、`monsters` の配置は旗による条件付き、`knows_at_start` と `appearance` で「最初は互いを知らない」を宣言
- `station_drill.json`: 8 人の `initial_state.role` (crew / keeper)、`mutually_known_roles: ["keeper"]`、`role_personas`、`meeting`、`ongoing_conditions` (power_out など)、`synchronized_action_groups`、`death.grace_ticks: 0` と `disabled_tools` に `tend_to_player`、`win: FLAGS_SET_AT_LEAST 16 件中 12 件` と `SURVIVING_PLAYERS_WITH_STATE_AT_MOST {"role":"keeper"} 0`

## 2. 振る舞い: 読み込みで起きること

### 2.1 読む

- ファイルを UTF-8 の JSON として読む (scenario_loader.py:159-160)。読み込みのエラーには `declaring(f"{path}:")` でファイル名が前に付く (scenario_loader.py:161、declaration_site.py:41-51)。付くのは `ScenarioLoadError` だけ [確認]
- 読む順序には依存がある [確認]
  1. `round_assignment` を最初に適用する (scenario_loader.py:182)。以降の検査は割り当て後の player に対して走る (D1514-2)
  2. `pre_register_ids` で spot / object / sub_location / connection (双方向なら `<id>__reverse` も) / player / item_spec の ID を先に登録する (parse_world.py:360-396)。効果が宣言順に関係なく他の物を指せるようにするため
  3. `player_attributes` を効果より先に読む (scenario_loader.py:189-192)。「変えられない属性を書く効果」を落とす検査に要る
  4. `loot_tables` を場所より先に読む (scenario_loader.py:194-197)。効果の `loot_table` を ID に変えるため
  5. `merchants` は spot と item_spec の登録後 (scenario_loader.py:221-223)
  6. `mutually_known_roles` / `role_personas` / `teams` は players の後 (scenario_loader.py:224-226)
  7. `ongoing_conditions` は、シナリオ全体から `SET_FLAG` と `initial_flags` を拾ってから読む (scenario_loader.py:248-253、parse_world.py:45-74)
  8. 最後に `validate_feature_consistency` (scenario_loader.py:356)

### 2.2 ID を振る [確認]

- `ScenarioIdMapper` は 9 つの名前空間 (spot, connection, object, sub_location, item_spec, player, monster_template, loot_table, merchant) に、登録順の連番 (1 始まり) を振る (scenario_id_mapper.py:50-66, 22-29)
- `register` は同じ文字列に同じ番号を返す (冪等、scenario_id_mapper.py:23-24)。**このため、ID の重複そのものは mapper では検出されない**
- 双方向の道は逆向きの辺に `"<id>__reverse"` という文字列 ID を作って番号を振る (parse_world.py:392、parse_map.py:556-560)
- グラフの ID は常に `SpotGraphId.create(1)` (parse_map.py:69)
- モンスター個体の `MonsterId` と `SkillLoadoutId` は読み込みではなく `create_world_runtime` が 1 から数える (RT:4389-4426)
- mapper は `ScenarioLoadResult.id_mapper` として世界に残り、実行中も文字列 ID と番号の行き来に使われる (RT:682、RT:2316, 2344, 2954, 3626, 3639, 4362、`spot_graph_tool_executor.py:688, 936`)

### 2.3 既定値を入れる・黙って補う [確認]

| 項目 | 書かなかったとき | 根拠 |
|---|---|---|
| metadata.description / theme / author / tags | 空 | parse_world.py:345-350 |
| metadata.difficulty | `"medium"` | parse_world.py:347 |
| metadata.estimated_ticks | 100 (`int()` で変換) | parse_world.py:348 |
| metadata.show_world_map | False | parse_helpers.py:44-46 |
| metadata.limits_actions | True | parse_helpers.py:54-56 |
| spot.category | `OTHER` | parse_map.py:80 |
| spot.is_outdoor | False | parse_map.py:92-95 |
| spot.atmosphere | 空・未指定なら None。指定すれば lighting=BRIGHT、temperature=NORMAL が既定 | parse_map.py:338-346 |
| spot.interior | 無ければ `SpotInterior.empty()` | parse_map.py:110-111 |
| interior.ground_items | 常に空 (宣言できない) | parse_map.py:377 |
| object.object_type | `OTHER` | parse_map.py:463 |
| object.is_visible / is_visible_in_dark | True / False | parse_map.py:467-474 |
| object.hidden_state_keys | 宣言 + 手番を記録する効果 (`RECORD_OBJECT_STATE_TICK`) が書く key を自動で足す。道具から遠隔で書く key も足す | parse_map.py:448-458、parse_helpers.py:193-258 |
| discoverable_items.discovery_condition | 無ければ ALWAYS | parse_map.py:492-494 |
| connection.travel_ticks | 1 | parse_map.py:550 |
| connection.is_bidirectional | True | parse_map.py:530-533 |
| connection.passage | 無ければ OPEN (`Passage.from_dict`) | parse_map.py:542、D/world_graph/value_object/passage.py:291-305 |
| area.position | 書かなければ所属 spot の重心。spot に位置が無ければ None | parse_map.py:170-178 |
| item.category | `"GENERAL"` | parse_economy.py:470 |
| item.fatigue_recovery | 0 | parse_economy.py:445 |
| player.initial_state | 空 | parse_actors.py:596-597 |
| player.persona_prompt | 空白だけなら None (黙って畳む) | parse_actors.py:388-389 |
| player.objective | 空白だけなら None。警告ログを出して共通の目的文へ戻す | parse_actors.py:552-562 |
| player.initial_gold | 0 | parse_actors.py:532-533 |
| player.knows_at_start | 無ければ None = 自分以外の全員を紹介 | parse_actors.py:507-508 |
| interaction.witness_policy | SAME_SPOT | parse_interactions.py:137-138 |
| interaction.cooldown_ticks / scope | 0 / ACTOR | parse_interactions.py:242-243, 257 |
| interaction.allowed_actor_planes | `["LIVING"]` | parse_interactions.py:159 |
| effect.target | ACTOR | parse_interaction_effects.py:129-130 |
| effect.visibility | 知らない値は **黙って None** (既定に戻す) | parse_interaction_effects.py:290-299 |
| `CHANGE_OBJECT_STATE.new_state` | `state_updates` に読み替え | parse_interaction_effects.py:305-306 |
| `parameters.visibility` | 直下の `visibility` に吸い上げる (過渡期の互換) | parse_interaction_effects.py:284-288 |
| condition.required_quantity | 1 | parse_helpers.py:396-397 |
| scenario_event.trigger / once / recipients | ON_TICK / True / all_players | parse_scenario_events.py:99, 150-153, 105 |
| scenario_event.observation.category / schedules_turn / breaks_movement | environment / True / False | parse_scenario_events.py:156-166 |
| reactive passage の apply_to_reverse | True。逆向きの辺があれば同じ binding を自動で生やす | parse_reactive_bindings.py:66-90 |
| sync group.window_ticks | 1 | parse_sync_groups.py:135 |
| `synchronized_action_groups` が配列でない | 黙って空 | parse_sync_groups.py:88-89 |
| `reactive_bindings` が object でない | 黙って空 | parse_reactive_bindings.py:41-42, 112-113 |
| `monsters` が object でない | 黙って空 | parse_actors.py:134-135 |
| monster template の base_stats / reward / respawn / race / faction / vision_range / flee_threshold | max_hp 30 など / exp 0 / 50 tick 自動 / WOLF / ENEMY / 5 / 0.2 | parse_actors.py:166-218 |
| needs | 飢餓 0、空腹 +1/tick、疲労 0 | models.py:376-380 |
| day_night | `enabled` 既定 False。ticks_per_day 24、starting_tick_in_day 0、announce True | parse_world.py:430-445 |
| weather | `enabled` 既定 False。initial は FOG 0.6、更新 6 tick、announce True。`initial` が object でなければ黙って `{}` | parse_world.py:485-501 |
| meeting | ブロックがあれば enabled 既定 True | parse_world.py:335 |
| player_trade | ブロックがあれば enabled 既定 True | parse_world.py:311 |
| market.reach | AT_SPOT | parse_economy.py:685-686 |
| death | grace_ticks None (= engine の既定)、announce_globally True、victim_learns_killer True | parse_world.py:287-291 |
| public_sns_push_budget_chars | 6000 | scenario_loader.py:298 |
| 文字列の前後の空白 | 多くの文字列を strip する (flag, message, 名前, appearance, first_person, role など) | 各所 |

### 2.4 変換する [確認]

- 文字列 ID を整数の型付き ID へ変える。効果の `parameters` では `item_spec`→`item_spec_id`、`target_object`→`object_id`、`target_sub_location`→`sub_location_id`、`target_connection`→`connection_id`、`target_spot`→`spot_id`、`loot_table`→`loot_table_id` (parse_interaction_effects.py:307-322)。**作者が書くキー名と、ドメインが持つキー名が違う**
- `CREATE_CONNECTION` の `from_spot_id` / `to_spot_id` はこの変換表に無い。読み込みでは文字列のまま通る (手元の実行で、存在しない spot を書いても読み込みは通った)
- 出来事の条件の糖衣 `all_of` / `any_of` / `not_` を `AND` / `OR` / `NOT` + `children` に直す (parse_scenario_events.py:254-300)
- `consume_effect` の dict / list を `ItemEffect` (複数なら `CompositeItemEffect`) に変える (parse_economy.py:359-421)
- `initial_items` の文字列と `{spec, state}` を `InitialItemSpec` にそろえる (parse_economy.py:485-514)
- `round_assignment`: シードと回の番号から作った乱数で枠を並べ替え、player の `spawn_spot` を上書きし、`initial_state` に枠のキーを足す (parse_round_assignment.py:44-68)
- 物体の `interactions` から、手番を記録する key を導いて hidden に足す (parse_map.py:448-458)
- 場所を足したあと・道を足したあとに `graph.clear_events()` で集約のドメインイベントを捨てる (parse_map.py:113, 564)。`create_world_runtime` でももう一度捨てる (RT:4428)
- `create_world_runtime` での変換 (深追いしていない):
  - `ItemSpecDefinition` → `ItemSpec`。種類 (CONSUMABLE / QUEST)、`Rarity.COMMON`、`MaxStackSize(1)` は runtime が決める (RT:4236-4262)
  - 人の能力値 (HP 100、MP 50 など) は全員同じ値を runtime が直書きする。シナリオに書く場所は無い (RT:4290-4330 付近)
  - 1 tick の分数は昼夜の宣言から計算し、無ければ 5 分 (RT:433, 442-454)
  - 勝ち筋の点検数は `win_conditions` の最初の `min_set_count` から取る (RT:457-466)。勝つ役は `task_winner_role="crew"` と直書き (RT:4144)
  - 「勝敗のある世界か」を win / lose / end / player_outcome_rules の有無で決める (RT:469-482)

### 2.5 検査する

検査は 4 つの段にある [確認]。

1. 項目ごとの検査 (parse_* の中)。型・空・範囲・列挙値・知らないキー
2. 参照の解決。mapper が知らない文字列は `ScenarioIdMappingError` (scenario_id_mapper.py:31-35)
3. キーをまたぐ検査。`reject_unreachable_team_outcomes`、`reject_unreachable_synchronized_action_names`、`validate_ongoing_condition_resolution_references`、teams と win/lose の排他など
4. 組合せの検査 `validate_feature_consistency` (validate_features.py:105-189)。生の JSON を再帰で舐めて (`iter_mappings`) 条件型・効果型の使用を数える

加えて、ドメインの値オブジェクト・集約の `__post_init__` や操作が、作られた時点で自分の不変条件を検査する。各規則は 3 章。

`spot_map_validator.py` (閉路・到達性・大事な場所への 2 経路・距離と移動時間の整合など 40 種のコード) は **読み込みからは呼ばれない**。`scripts/validate_spot_map.py`、`scripts/render_spot_map.py`、`scripts/check_mine_village_map.py` だけが使う [確認]。

### 2.6 失敗の形 [確認]

- 想定した書き間違いは `ScenarioLoadError` (load_error.py:8) で止める。これは `Exception` の直下で、ドメイン例外の階層の外にある
- ところが次は `ScenarioLoadError` にならずに素通りする。`declaring` が場所を前に付けないので、どのファイルのどこかが分からない
  - 必須キーの欠け: `KeyError` (例: `metadata.title`、`spots[].name`、`connections[].name`、`item_specs[].name`)
  - 列挙値の綴り違いのうち一部: `KeyError` (例: `spots[].category`、`atmosphere.lighting`、`object_type`、`environment.weather.initial.weather_type`、`passage_conditions[].condition_type`)
  - 知らない文字列 ID: `ScenarioIdMappingError` (例: `players[].spawn_spot`、`connections[].to`、`parent_id`、`initial_items`)。出来事の条件の中だけは包み直す (parse_scenario_events.py:417-425)
  - ドメインの検査: `DuplicateSpotException`、`DuplicateConnectionIdException`、`SpotConnectionValidationException`、`GameEndConditionValidationException`、`DayNightCycleValidationException`、`PassageValidationException`、`SynchronizedActionGroupValidationException` など。包み直しているのは `StateDisplayRuleValidationException`、`PlayerOutcomeRuleValidationException`、`ScenarioEventConditionValidationException`、`ScenarioTeamValidationException`、`MonsterTemplateValidationException`、`PlayerAttributeSpecValidationException` だけ
  - 組み込みの `ValueError`: `persona_prompt` / `objective` の型、`goal_locked` (parse_actors.py:384-386, 551, 577-581)、`item_specs` の `spoils_after_ticks` / `fatigue_recovery` / `usage_hint` / `event_removal_message` / `consume_effect` (parse_economy.py:389-457)。`needs` だけは `ValueError` を包み直す (parse_economy.py:532-535)
- 手元の実行で確かめた例: `metadata.title` 欠け → `KeyError: 'title'`、`category: "NOPE"` → `KeyError: 'NOPE'`、weather の綴り違い → `KeyError: 'SUNNYY'`、知らない spawn_spot → `ScenarioIdMappingError`、`persona_prompt: 3` → `ValueError`
- 黙って続けるもの: 警告ログだけを出す `reactive_bindings.objects` の無音の binding (parse_reactive_bindings.py:163-172) と、空白だけの `objective` (parse_actors.py:557-561)
- これは Issue #1522 の範囲 (「必須キーの欠け、値の綴り違い、包む層のキー」、docs/scenario_engine_capabilities.md:15) と重なる [確認: 文書の記述]

## 3. 不変条件

列の意味:
- **守り方**: `SLE` = `ScenarioLoadError`、`MapErr` = `ScenarioIdMappingError`、`KeyErr` = 組み込みの `KeyError`、`VE` = 組み込みの `ValueError`、`DomEx` = ドメイン例外 (型名を添える)、`補う` = 黙って補う、`警告` = ログだけ、`×` = 守っていない (手元の実行で通ることを確かめたもの)
- **層**: I = infrastructure、A = application、D = domain
- **見立て**: **ド** = ドメインの規則 (世界の決まりとして成り立つべきこと)、**宣** = シナリオの宣言を確かめているだけ (書式、書き間違い、宣言どうしの参照)、**実** = 実装の都合
- ★ = 4 章で「ドメインに置くべき」と見立てたもの

### 3.1 書式と全体

| # | 規則の文 | どこで | 守り方 | 層 | 見立て |
|---|---|---|---|---|---|
| G1 | 書式の版は `"1.0"` だけ | scenario_loader.py:171-175、load_error.py:5 | SLE | I | 宣 |
| G2 | 廃止した `outcome_resolution` は書けない | scenario_loader.py:176-181 | SLE | I | 宣 |
| G3 | トップレベルの知らないキーは拒否する | (検査なし) | × (`spotz` を足しても通る) | - | 宣 |
| G4 | `metadata.id` と `metadata.title` は必須 | parse_world.py:343-344 | KeyErr | I | 宣 |
| G5 | 世界には場所が 1 つ以上ある | (検査なし) | × (spots 空で通る) | - | ド [推測: 必要かは要判断] |
| G6 | 世界には人物が 1 人以上いる | (検査なし。目的文の検査が間接的に関わる RT:2068-2079) | × | - | ド [推測] |

### 3.2 場所・道・地図

| # | 規則の文 | どこで | 守り方 | 層 | 見立て |
|---|---|---|---|---|---|
| M1 | 場所の id は世界で一意 | `SpotGraphAggregate.add_spot` (D/world_graph/aggregate/spot_graph_aggregate.py:161-163) | DomEx `DuplicateSpotException` | D | ド |
| M2 | 場所の名前は空でない | `SpotNode.__post_init__` (D/world_graph/entity/spot_node.py:30-32)、キー欠けは parse_map.py:86 | DomEx / KeyErr | D / I | ド |
| M3 | 親の場所 `parent_id` は実在する場所 | parse_map.py:79 | MapErr | I | 宣 (前方参照は通る) |
| M4 | 場所の位置は有限の数の x, y だけ | parse_map.py:117-128、parse_helpers.py:272-278 | SLE | I | 宣 |
| M5 | 場所の `area_id` は空でない文字列 | parse_map.py:131-136 | SLE | I | 宣 |
| M6 | 場所の `area_id` は宣言した area を指す | spot_map_validator.py の `UNKNOWN_SPOT_AREA_ID` (スクリプトだけ) | × (読み込みでは通る) | I(script) | 宣 |
| M7 | 道の id は世界で一意 (逆向きの辺も含む) | `SpotGraphAggregate.add_connection` (spot_graph_aggregate.py:215-224) | DomEx `DuplicateConnectionIdException` | D | ド |
| M8 | 道の両端は実在する場所 | parse_map.py:527-528 (mapper)、spot_graph_aggregate.py:217-218 | MapErr / DomEx | I / D | ド ★ (D 側にもあり) |
| M9 | 双方向の道は逆向きの辺の ID を持つ | parse_map.py:556-560、spot_graph_aggregate.py:220-222 | 補う / VE | I / D | 実 |
| M10 | 移動の tick 数は 0 以上 | `SpotConnection.__post_init__` (D/world_graph/entity/spot_connection.py:36-38) | DomEx | D | ド |
| M11 | 廃止キー `initially_passable` / 接続直下の `sound_permeability` は書けない | parse_map.py:537-541 | SLE | I | 宣 |
| M12 | 通路の種類・状態は既知の値 | `Passage.from_dict` (passage.py:306-354) | DomEx / VE (`WallStateEnum(...)` など) | D | ド (ただし dict を読むのは D) |
| M13 | どの場所も出発点から行ける、閉路がある、大事な場所に 2 経路ある、距離と tick 数が合う | spot_map_validator.py:94-180 | × (読み込みでは見ない。スクリプトだけ) | I(script) | ド か 宣 [推測: 品質の目安で、規則ではない] |
| M14 | 同じ場所に同じ id の物体を 2 つ書かない | parse_world.py:376-381 | SLE | I | 宣 |
| M15 | 物体の id は **世界で** 一意 | (検査なし) | × (別の場所に同じ id を書くと同じ `SpotObjectId` を 2 つの物体が持つ) | - | ド ★ |
| M16 | 小部屋 (sub_location) の id は世界で一意 | (検査なし) | × | - | ド ★ |
| M17 | 小部屋から触れる物体は同じ場所の中の物体 | parse_map.py:397-407 | SLE | I | ド ★ |
| M18 | 物体の名前は空でない、`unavailable_hint` は空でない文字列 | parse_map.py:444-447、D/world_graph/entity/spot_object.py:74-79 | SLE / DomEx | I / D | ド (二重) |
| M19 | `state_display` の規則は key / text を持ち、`value` / `at_least` / `within_ticks` は排他、同じ規則を 2 度書かない | parse_helpers.py:130-171、`StateDisplayRule.__post_init__` (state_display_rule.py:48-74) | SLE / DomEx(包み直し) | I / D | ド ★ |
| M20 | `within_ticks` の表示は、手番を記録する効果が書く key にだけ付ける | parse_helpers.py:156-159 | SLE | I | ド ★ |
| M21 | 手番を記録する key はプロンプトに出さない (hidden にする) | parse_map.py:448-458 (足す)、spot_object.py の表示側でも生値を返さない | 補う | I / D | ド ★ |
| M22 | 同じ物体の操作の `action_name` は重ならない | (検査なし) | × (品目と対人には検査がある) | - | ド ★ |
| M23 | area の id は一意、name / visible_name は空でない、prominence は [0,1] | parse_map.py:151-168、parse_helpers.py:281-285 | SLE | I | 宣 |
| M24 | 遠景の兆候の source は `object_state` だけで、実在する物体を指す。origin は宣言した area | parse_map.py:286-335 | SLE | I | 宣 |
| M25 | 遠景の兆候の `appear_event` は空でない message と真偽値の `schedules_turn` を持つ | parse_map.py:265-283 | SLE | I | 宣 |

### 3.3 品目・経済

| # | 規則の文 | どこで | 守り方 | 層 | 見立て |
|---|---|---|---|---|---|
| E1 | 品目の id は世界で一意 | (検査なし) | × (同じ id の品目が 2 つ、同じ `ItemSpecId` で並ぶ。保存先で後勝ち [推測]) | - | ド ★ |
| E2 | 腐るまでの tick は正の整数 | parse_economy.py:438-440 (と `ItemSpec.__post_init__` [コメントによる]) | VE | I | ド ★ |
| E3 | 疲労回復は 0 以上の整数 | parse_economy.py:446-451 | VE | I | ド ★ |
| E4 | `usage_hint` / `event_removal_message` を書くなら空にしない | parse_economy.py:452-463 | VE | I | 宣 |
| E5 | 消費効果の種類は heal_hp / damage_hp / recover_mp / gold / exp / satisfy_need / revive のどれか。satisfy_need は need_type、revive は hp_rate を持つ | parse_economy.py:383-421 | VE | I | 宣 |
| E6 | 品目の操作の `action_name` は品目の中で重ならない | parse_economy.py:342-345 | SLE | I | ド ★ |
| E7 | 道具の操作で物体に作用する効果は対象の物体を明示する | parse_economy.py:346-353 | SLE | I | ド ★ |
| E8 | 抽選表は id を持ち、1 行以上、重みは 0 以上、数量は 1 以上で max >= min | parse_economy.py:72-108 | SLE | I | ド ★ |
| E9 | 商人の id・名前は一意、場所と品目は実在、売りか買いの少なくとも一方がある、同じ側に同じ品目を 2 度書かない、価格は 1 以上の整数 | parse_economy.py:149-298 | SLE | I | ド ★ |
| E10 | 市場の板には置き場所がある (届く範囲が global でも) | parse_economy.py:649-656 | SLE | I | ド ★ |
| E11 | 板の初期注文は実在の商人・品目、向きは sell / buy、数量・単価・期限は 1 以上の整数 | parse_economy.py:542-618 | SLE | I | ド ★ |
| E12 | 市場の届く範囲は既知の値 | parse_economy.py:679-693 | SLE | I | 宣 |
| E13 | 初期所持金は 0 以上の整数 | parse_actors.py:525-538 | SLE | I | ド ★ (`Gold` の下限と二重) |
| E14 | 初期の持ち物は所持枠 (`PlayerInventoryAggregate.DEFAULT_MAX_SLOTS`) に収まる | parse_actors.py:614-637 | SLE | I | ド ★ |
| E15 | 取引の提案の期限・注文の期限は 1 以上 | parse_world.py:314-319、parse_economy.py:660-665 | SLE | I | ド ★ |
| E16 | 納めるお金 (`DEPOSIT_GOLD_TO_OBJECT`) の合計は、同じ操作の `PLAYER_GOLD_AT_LEAST` 以下 | parse_interactions.py:35-74 | SLE | I | ド ★ |

### 3.4 人物・属性・役

| # | 規則の文 | どこで | 守り方 | 層 | 見立て |
|---|---|---|---|---|---|
| P1 | 人物の id は一意 | parse_round_assignment.py:81-84 (round_assignment があるときだけ) | SLE / × (round_assignment が無いと、同じ id の人物 2 人が同じ `player_id` で並ぶ) | I | ド ★ |
| P2 | 出発地は実在する場所 | parse_actors.py:364-365 | MapErr | I | 宣 |
| P3 | `initial_state` は文字列キーと JSON のプリミティブ値だけ | parse_actors.py:584-611 | SLE (と D の `PlayerStateValidationException` [コメントによる]) | I | ド ★ |
| P4 | `initial_state` の値は、宣言した属性の取りうる値の中にある | parse_actors.py:374-379、validate_attribute_values.py:46-72 | SLE | I | ド ★ |
| P5 | 属性の visibility は public / secret / hidden、mutable は真偽値、values は空でない文字列の配列か 値→呼び名 | parse_economy.py:712-752 (+ `PlayerAttributeSpec` の検査) | SLE | I / D | ド ★ |
| P6 | 変えられないと宣言した属性を書く効果は無い (`CHANGE_PLAYER_STATE` / `RECORD_PLAYER_STATE_TICK`) | parse_interaction_effects.py:192-224 | SLE | I | ド ★ |
| P7 | 効果や条件が書く・求める属性の値は、宣言した値の中にある | parse_interaction_effects.py:209-214、parse_interaction_conditions.py:100-108 | SLE | I | ド ★ |
| P8 | 人の名前は別の人の名前の一部にならない | parse_actors.py:458-466 | SLE | I | ド ★ (名前を見た目へ置き換える処理の都合も含む) |
| P9 | 見た目 (`appearance`) は空でなく、人ごとに違い、誰かの名前を含まない | parse_actors.py:426-433, 467-479 | SLE | I | ド ★ |
| P10 | 最初に名前を知らない相手は見た目を持つ。その相手の名前を自分の persona / objective に書かない | parse_actors.py:480-496 | SLE | I | ド ★ |
| P11 | `knows_at_start` は実在の人物の id だけ、自分を含まない、重複しない | parse_actors.py:499-522 | SLE | I | ド ★ |
| P12 | 一人称 `first_person` を書くなら空でない | parse_actors.py:436-443 | SLE | I | 宣 |
| P13 | `persona_prompt` / `objective` は文字列 | parse_actors.py:382-386, 549-551 | VE | I | 宣 |
| P14 | 廃止した `goal_locked` は書けない | parse_actors.py:566-581 | VE | I | 宣 |
| P15 | 共通の目的文が空なら、全員が個人の目的を持つ | RT:2041-2079 (`_resolve_scenario_llm_objective_text`、prompt を組むときに評価) | VE (読み込みではなく run 中) | A | ド ★ |
| P16 | 互いを知る role (`mutually_known_roles`) は 2 人以上いて、重複しない | parse_actors.py:44-68 | SLE | I | ド ★ |
| P17 | role 共通の文 (`role_personas`) の role は誰かが持つ role で、文は空でない | parse_actors.py:71-96 | SLE | I | ド ★ |
| P18 | `role` という `initial_state` のキーを、役として特別に扱う | parse_actors.py:64, 82、`move_translation.py:46-51`、RT:4144 (`"crew"`) | 暗黙の取り決め | I / A | ド ★ (役の概念がドメインに無い) |
| P19 | 回の番号は正の整数。round_assignment にはシードが要る。枠の数 = 人数、知らない人物や 2 度の割り当ては無い、枠は spawn_spot か initial_state を持つ | parse_round_assignment.py:37-43, 72-130 | SLE | I | ド ★ (回と割り当て) |

### 3.5 チーム・勝敗・個人の結果

| # | 規則の文 | どこで | 守り方 | 層 | 見立て |
|---|---|---|---|---|---|
| T1 | チームは 2 つ以上 | parse_teams.py:40-43 | SLE | I | ド ★ |
| T2 | チームの id は一意、name は空でない、member_state は空でない、win は 1 つ以上 | parse_teams.py:52-66、`ScenarioTeam.__post_init__` (D/world_graph/value_object/scenario_team.py:30-40) | SLE / DomEx(包み直し) | I / D | ド (二重) |
| T3 | 誰もがちょうど 1 つのチームに属する | parse_teams.py:67-91 | SLE | I | ド ★ |
| T4 | 所属の一致は真偽値と数を区別する (`True` と `1` を同じにしない) | parse_teams.py:119-124 | 実装 | I | ド ★ |
| T5 | チームがあるシナリオでは全体の win / lose を書かない | scenario_loader.py:227-233 | SLE | I | ド ★ |
| T6 | チームがあるシナリオには、どのチームも勝たずに終わる `end` が 1 つ以上ある | scenario_loader.py:241-246 | SLE | I | ド ★ |
| T7 | チームの win が待つ個人の結果 (RESCUED / STRANDED) は、それを付ける規則がある | parse_teams.py:100-116 | SLE | I | ド ★ |
| T8 | 終了条件の型ごとに置ける場所 (win / lose / end / team_win / team_end) が決まっている | parse_world.py:551-560、validate_features.py:87-99 | SLE | I | ド ★ |
| T9 | 終了条件の型ごとの必須項目 (FLAGS_SET_AT_LEAST の required_flags と min_set_count、FLAG_SET の target_flag、TICK_LIMIT の tick_limit、生存数条件の required_state と max_surviving、場所条件の target_spot、ALL_MEMBERS_HAVE_OUTCOME の outcome) | parse_world.py:588-679、`GameEndCondition.__post_init__` (D/world_graph/value_object/game_end_condition.py:36-127) | SLE / DomEx (包み直さない) | I / D | ド (二重) |
| T10 | 終了条件の項目に知らないキーを書かない | (検査なし) | × (station_drill は `description` を書いており、読まれない) | - | 宣 |
| T11 | 終了条件 `FLAG_SET` の旗は誰かが立てられる | (検査なし) | × | - | ド ★ (O1 と同じ検査が無い) |
| T12 | 個人結果の規則は id が一意、trigger は条件、player_conditions は条件の配列、once は明示の真偽値、outcome は既知 (RESCUED / STRANDED) | parse_scenario_events.py:174-239、`PlayerOutcomeRule.__post_init__` (player_outcome_rule.py:29-48) | SLE / DomEx(包み直し) | I / D | ド (二重) |
| T13 | 終局の観測文は既知の結果 (UNRESOLVED 以外) で、`{player_name}` を含み、それ以外の置き換えや書式指定を持たない | parse_helpers.py:69-111 | SLE | I | ド ★ |
| T14 | 勝敗の宣言が無い世界は終わらない (永続世界) | RT:469-482、design_decisions 26 | 導出 | A | ド |

### 3.6 世界の旗と異常

| # | 規則の文 | どこで | 守り方 | 層 | 見立て |
|---|---|---|---|---|---|
| O1 | 異常 (`ongoing_conditions`) の旗は `initial_flags` か `SET_FLAG` のどこかで立てられる | parse_world.py:45-74, 126-127 | SLE | I | ド ★ |
| O2 | 異常の旗は重複しない、message は空でない、`blocks_emergency_button` は明示の真偽値、知らないキーは書かない | parse_world.py:113-133 | SLE | I | ド ★ |
| O3 | 異常の解除 (`resolution`) は旗の効果だけで、自分の旗を CLEAR_FLAG する。書くなら空にしない | parse_world.py:134-161 | SLE | I | ド ★ |
| O4 | 会議の始まりの効果は RESOLVE_ONGOING_CONDITION と SHOW_MESSAGE だけで、自分の旗を参照し、resolution を前提にする | parse_world.py:162-196 | SLE | I | ド ★ |
| O5 | どこかの `RESOLVE_ONGOING_CONDITION` が指す旗には resolution がある | parse_world.py:210-235 | SLE | I | ド ★ |
| O6 | 前提条件・出来事の条件・終了条件・モンスターの出現条件が見る旗は、誰かが立てられる | (検査なし) | × (O1 だけにある) | - | ド ★ |
| O7 | `initial_flags` は空でない文字列の列 | (検査なし。`tuple(...)` するだけ) | × (`[1, None]` が通る) | - | 宣 |

### 3.7 操作・前提条件・効果

| # | 規則の文 | どこで | 守り方 | 層 | 見立て |
|---|---|---|---|---|---|
| I1 | `action_name` は engine 予約の接頭辞で始めない (`cooldown_group` も同じ) | parse_interactions.py:84-98, 221-230 (接頭辞は application の `interaction_cooldown_store`) | SLE | I | 実 |
| I2 | 操作は空でない `display_label` を持つ | parse_interactions.py:99-102 | SLE | I | ド ★ |
| I3 | 対人の操作の `action_name` は一意で、相手に効く効果を 1 つ以上持つ | parse_interactions.py:331-358 | SLE | I | ド ★ |
| I4 | 相手への通知 (`notify_target` / `target_observation_message`) は対人の操作だけが持ち、文を書くなら通知を立てる | parse_interactions.py:268-308 | SLE | I | ド ★ |
| I5 | `CALL_MEETING` は単独の効果で、trigger は既知の値。使うなら会議を宣言する | parse_interactions.py:114-117、parse_interaction_effects.py:373-380、validate_features.py:127-129 | SLE | I | ド ★ |
| I6 | 待ち時間は 0 以上の整数、共有単位は既知の値 | parse_interactions.py:234-265 | SLE | I | ド ★ |
| I7 | 操作できる側 (`allowed_actor_planes`) は LIVING / DEPARTED の空でない重複なしの列 | parse_interactions.py:159-169 | SLE | I | ド ★ |
| I8 | 旗の前提が外れたら隠す操作は、旗の前提条件を持つ | parse_interactions.py:170-185 | SLE | I | ド ★ |
| I9 | 目撃の方針は既知の値、目撃文は文字列 | parse_interactions.py:119-152 | SLE | I | 宣 |
| I10 | 前提条件の種類は既知で、その種類が読むキーだけを書く | parse_interaction_conditions.py:41-99 | SLE | I | 宣 |
| I11 | 前提条件の種類ごとの必須項目 (相手の所持条件の品目、所持金の閾値、整数 state の key、相手 state の required_state、明るさ・天候・場所の値) と列挙値 | parse_interaction_conditions.py:117-147, 190-260 | SLE | I | ド ★ |
| I12 | 必要数は 1 以上、hp 比は [0,1]、need_type は既知 | parse_helpers.py:356-406 | SLE | I | ド ★ |
| I13 | 時間帯の条件を使うなら昼夜を宣言し、時間帯の名前は宣言したもの | validate_features.py:131-172 | SLE | I | ド ★ |
| I14 | 天候の条件を使うなら天候を有効にする | validate_features.py:174-189 | SLE | I | ド ★ |
| I15 | 新しい前提条件の種類を足したら、環境の機能への依存を分類する | validate_features.py:110-117 (読み込みのたびに表と enum を突き合わせる) | SLE | I | 実 |
| I16 | 効果の種類は既知で、その種類が読む parameters だけを書く | parse_interaction_effects.py:249-273 | SLE | I | 宣 |
| I17 | `target: TARGET_PLAYER` は対人の操作の中だけで、GIVE_ITEM / REMOVE_ITEM / APPLY_DAMAGE だけが取れる | parse_interaction_effects.py:118-167 | SLE | I | ド ★ (一部は「配線がまだ」の実の都合、:35-43) |
| I18 | 行為者の要る効果 (SHOW_ROOM_OCCUPANCY、DEPOSIT_*、RECORD_PLAYER_STATE_TICK) は出来事の効果に書けない | parse_interaction_effects.py:275-280, 328-359 | SLE | I | ド ★ |
| I19 | DEPOSIT_ITEM_TO_OBJECT は品目・state_key・数量 (正の整数か all) を持ち、DEPOSIT_GOLD_TO_OBJECT は state_key と正の整数の amount を持つ | parse_interaction_effects.py:333-372 | SLE | I | ド ★ |
| I20 | 移動の効果は行き先を持ち、visibility を持たず、観測文は空でない文字列で `{actor}` 以外の波括弧を含まない | parse_interaction_effects.py:386-404, 420-461 | SLE | I | ド ★ |
| I21 | 環境を変える効果は対象の場所と、変える項目を 1 つ以上持ち、明るさ・温度は既知の値 | parse_interaction_effects.py:464-500 | SLE | I | ド ★ |
| I22 | 効果の visibility は既知の値 | parse_interaction_effects.py:290-299 | 補う (知らない値は None) | I | 宣 |
| I23 | 効果が指す品目・物体・小部屋・道・場所・抽選表は実在する | parse_interaction_effects.py:307-322 | MapErr | I | 宣 |
| I24 | `CREATE_CONNECTION` の両端は実在する場所 | (検査なし) | × | - | ド ★ |
| I25 | 二人で合わせる操作 (`required_action_names` の操作) の interaction は効果を持たない | validate_features.py:192-221 | SLE | I | ド ★ |
| I26 | 生き返らせられない世界 (`death.grace_ticks == 0`) では `tend_to_player` を出さない | validate_features.py:122-123 (application の `ToolExposure` を使う) | SLE | I | ド ★ |

### 3.8 出来事・反応・同期

| # | 規則の文 | どこで | 守り方 | 層 | 見立て |
|---|---|---|---|---|---|
| S1 | 出来事の id は一意で空でない | parse_scenario_events.py:82-91 | SLE | I | ド ★ |
| S2 | 出来事の trigger は ON_TICK / ON_CHAIN、配り先は all_players / players_at_spot。players_at_spot なら場所を持つ | parse_scenario_events.py:99-116 | SLE | I | ド ★ |
| S3 | `next_event_id` は実在の出来事、`delay_ticks` は 0 以上の整数 | parse_scenario_events.py:117-127 | SLE | I | ド ★ |
| S4 | 出来事の条件の種類は既知で、その種類が読むキーだけを書き、糖衣と `condition_type` を混ぜない | parse_scenario_events.py:254-318 | SLE | I | 宣 |
| S5 | 条件の種類ごとの必須項目と列挙値 (GAME_PHASE_IS、WEATHER_IS、PLAYERS_AT_SPOT、OBJECT_STATE_INT_GREATER_THAN_OTHER) | parse_scenario_events.py:319-352、`ScenarioEventCondition.__post_init__` (scenario_event_condition.py:94-114) | SLE / DomEx(包み直し) | I / D | ド (二重) |
| S6 | 反応する通路 (`reactive_bindings.passages`) は実在の道を指し、真と偽で違う状態を持つ | parse_reactive_bindings.py:47-65、`ReactivePassageBinding.__post_init__` (reactive_passage_binding.py:61-71) | SLE / MapErr / DomEx (包み直さない) | I / D | ド |
| S7 | 反応する通路の状態名は、その道の通路の種類が持つ状態 | (検査なし) | × (`"BOGUS"` が通る) | - | ド ★ |
| S8 | 反応する物体は実在の物体を指し、少なくとも一方の向きで state を変え、同じ key を重ねない | parse_reactive_bindings.py:119-134、`ReactiveObjectStateBinding.__post_init__` (reactive_object_state_binding.py:84-98) | SLE / MapErr / DomEx | I / D | ド |
| S9 | 状態を変える反応は、少なくとも一方の向きで観測を出す | parse_reactive_bindings.py:163-172 | 警告 | I | ド ★ |
| S10 | 同期の操作の名前は、どこかの interaction の `action_name` として宣言されている | parse_sync_groups.py:20-64、parse_helpers.py:415-439 | SLE | I | ド ★ |
| S11 | 同期のグループは id、名前の列、正の窓、1 つ以上の完了効果を持つ。旧キー `required_action_ids` は書かない | parse_sync_groups.py:94-107、`SynchronizedActionGroup.__post_init__` (synchronized_action_group.py:70-88) | SLE / DomEx (包み直さない) | I / D | ド (二重) |

### 3.9 モンスター・環境・会議・死

| # | 規則の文 | どこで | 守り方 | 層 | 見立て |
|---|---|---|---|---|---|
| X1 | モンスターの種別は id を持ち、race / faction は既知、能力値は数、攻撃時の状態異常は既知の種類 | parse_actors.py:148-258 | SLE | I | 宣 |
| X2 | モンスターの配置は実在の種別と実在の場所を指す | RT:4400-4406 (即時配置)、RT:5478-5483 (条件付きは tick の中) | VE / MapErr (読み込みでは見ない。条件付きは run 中に初めて見る) | A | ド ★ |
| X3 | モンスターの出現条件は知らないキーを持たず、天候は既知の値。時間帯の名前は検査しない | parse_actors.py:312-344 | SLE | I | ド ★ |
| X4 | 昼夜は 1 つ以上の時間帯を持ち、各時間帯は必須の 5 項目を持つ。1 日の tick 数・開始位置・時間帯の並び・名前の重複はドメインが見る | parse_world.py:446-459、`DayNightCycleDef.__post_init__` (day_night_cycle_def.py:37-57)、`DayNightPhaseDef` (day_night_phase_def.py:36-44) | SLE / DomEx (包み直さない) | I / D | ド (二重) |
| X5 | 天候の初期値は既知の天候 | parse_world.py:492 | KeyErr | I | 宣 |
| X6 | 空腹は 1 以上/tick、疲労・飢餓は 0 以上の整数 | models.py:382-405 (infrastructure の DTO の `__post_init__`)、parse_economy.py:523-535 | VE→SLE | I | ド ★ |
| X7 | 会議の調整値は 1 以上の整数、enabled は真偽値 | parse_world.py:238-266, 323-338 | SLE | I | ド ★ |
| X8 | 死の猶予は 0 以上、告知と加害者の通知は真偽値 | parse_world.py:269-291 | SLE | I | ド ★ |
| X9 | `disabled_tools` は空でない文字列の重複しない列。名前の実在は起動時に見る | parse_world.py:505-529、RT:1535-1545 | SLE / `ToolExposureConfigurationError` | I / A | 宣 |
| X10 | 公開 SNS の予算は 512〜24000 の整数。公開 SNS を有効にした世界は今は動かせない | scenario_loader.py:297-306、RT:4105-4111 | SLE / `PublicSnsNotSupportedError` | I / A | 実 |

## 4. 本来ドメインに置くべき規則が infrastructure / application にあるもの

3 章で ★ を付けた規則のうち、まとまりの大きいものを、置き先の候補ごとに並べる。置き先は [推測]。

| まとまり | 今ある場所 | 置き先の候補 [推測] | 理由 |
|---|---|---|---|
| ★ 物体・小部屋・品目・人物の ID の一意性 (M15, M16, E1, P1) | どこにも無いか、round_assignment のときだけ (I) | 世界 (環境) の集約が持つ「この世界の物の登録」 | 場所と道の一意性はグラフの集約が守っているのに、物体・品目・人物は守る持ち主がいない。mapper が冪等なので重複が黙って通る |
| ★ 人物の見た目・名前・最初に知っている相手 (P8〜P11, P15) | parse_actors.py (I)、RT:2041-2079 (A) | 人物 (登場人物) の集合を表す値オブジェクト | 「名前を知らない相手は見た目で出す」は世界の決まりで、読み込みの書式の話ではない |
| ★ 役 (`role`) と互いを知る役・役の共通文 (P16〜P18) | parse_actors.py (I)、`move_translation.py` (A)、RT:4144 の `"crew"` 直書き (A) | 役の概念をドメインの型にする | 今は `initial_state["role"]` という自由 state の 1 キーを、3 か所が別々に特別扱いしている |
| ★ 属性の宣言とそれに合う値・不変の属性を書かない (P4〜P7) | validate_attribute_values.py、parse_interaction_effects.py:192-224 (I) | `PlayerAttributeSpecs` | 値の集合は `PlayerAttributeSpecs` (D) が持つのに、「宣言に無い値を使うな」「不変を書くな」の判定は infrastructure が外から当てている (tell, don't ask に反する形) |
| ★ チームの組み分けと勝敗の成り立ち (T1, T3〜T8, T11, T13) | parse_teams.py、scenario_loader.py:227-246、parse_world.py:551-560 (I) | 勝敗の宣言を表す集約 (シナリオの「終わり方」) | `ScenarioTeam` (D) は自分 1 つの検査しか持たず、チームどうし・全体の終了条件との関係は infrastructure にある |
| ★ 異常の宣言 (O1〜O6) | parse_world.py:45-235 (I) | 異常の宣言の値オブジェクトと、旗を立てる側の集合 | `OngoingConditionDef` が infrastructure の models.py にある。「解けない異常」「誰も立てない旗」は世界の決まり |
| ★ 操作の定義の整合 (I2〜I8, I11, I17〜I21, I24, I25, E6, E7, E16, M22) | parse_interactions.py、parse_interaction_conditions.py、parse_interaction_effects.py、parse_economy.py:301-356 (I) | `InteractionDef` / `InteractionCondition` / `InteractionEffect` | これらの型は D にあるが、`InteractionDef.__post_init__` は 1 つの検査しか持たない (interaction_def.py:100-104)。効果の種類ごとの必須項目・対象の取り方は D の型が知るべきこと |
| ★ 出来事・反応・同期の参照の整合 (S1〜S3, S7, S9, S10) | parse_scenario_events.py、parse_reactive_bindings.py、parse_sync_groups.py (I) | 出来事の集合、同期の集合 | 1 つずつの値オブジェクトは D にあるが、集合としての一意性と参照先の実在は I にしか無い |
| ★ 経済の宣言 (E8〜E11, E13〜E15) | parse_economy.py (I)、models.py の `Scenario*Definition` (I) | 商人・市場・抽選表のドメインの型 | 商人・板・初期注文の型が infrastructure の models.py にあり、ドメインの型が無い |
| ★ 環境の機能の組合せ (I13, I14, I26, X3) | validate_features.py (I、application の `ToolExposure` を使う) | 世界の環境 (時計・天候) の宣言 | 「天候の無い世界で天候の条件を書かない」は世界の決まり |
| ★ 物体の表示と手番の key (M19〜M21) | parse_helpers.py:114-258、parse_map.py:448-458 (I) | `SpotObject` | `SpotObject` も表示時に生値を返さないよう守っているので、決まりが I と D の 2 か所にある |
| ★ needs の値 (X6) | models.py:382-405 (I の DTO の `__post_init__`、組み込みの `ValueError`) | needs の値オブジェクト | CLAUDE.md の「ドメイン層ではドメイン例外」の決まりの外にある |
| ★ モンスターの配置先の実在 (X2) | RT (A) | 世界の集約 | 読み込みでは見ず、条件付きの配置は run の途中まで見ない |

逆向きのもの (ドメインがシナリオの書式を知っている) [確認]:
- `Passage.from_dict` (D/world_graph/value_object/passage.py:291) は JSON の dict を読む。シナリオの書式を domain が知っている
- `Passage.from_dict` は効果の `CREATE_CONNECTION` の `passage` にも使われる [推測: キーの表 parse_interaction_effects.py:96 からの見立て]

層の依存の向き [確認]:
- infrastructure → application: `parse_interactions.py:7-10` (`interaction_cooldown_store` の接頭辞)、`validate_features.py:8` (`ToolExposure`)
- application → infrastructure: `world_runtime.py:394-401` (`ScenarioLoader`、`ScenarioLoadResult`、`PlayerSpawnConfig`、`ScenarioIdMapper`)、`move_translation.py:28` (`ScenarioLoadResult`)

## 5. コードの言葉 (ドメインの語彙の候補) と、呼び名の揺れ

### 5.1 使われている言葉 [確認]

- 世界の形: spot (場所)、connection (道)、passage (通路。kind と state を持つ)、interior (中身)、object (物体)、sub_location (小部屋)、discoverable item、area (遠景の単位)、distant cue (遠くに見える兆候)、atmosphere (明るさ・音・温度・匂い)、position
- 人: player (spawn)、persona_prompt、objective、appearance、first_person、knows_at_start、initial_state、role、player_attributes (visibility / mutable / values)、team、member_state
- 操作: interaction、action_name、display_label、precondition (`InteractionCondition`)、effect (`InteractionEffect`)、target (ACTOR / TARGET_PLAYER)、witness、cooldown、actor plane (LIVING / DEPARTED)
- 世界の進み: flag (world flag)、scenario_event、trigger (ON_TICK / ON_CHAIN)、reactive binding、synchronized action group、ongoing condition、meeting、tick
- 終わり方: game_end_conditions (win / lose / end)、team、player outcome (RESCUED / STRANDED / DEAD / EJECTED / UNRESOLVED)、player_outcome_rule
- 経済: item_spec、loot_table、merchant (sells / buys)、market (board, reach, initial_orders)、player_trade、gold
- 環境: weather、day_night (phase)、needs (hunger / fatigue / starvation)、death (grace)
- 回: round_assignment (group, slot)、round_number、random_seed
- Being との境目: `EnvironmentEntry(environment_name, imposed_goal, introductions)` (`move_translation.py:28-37`)、`Persona(name, first_person)` (RT:6722)

### 5.2 同じものを別の名前で呼んでいる箇所 [確認]

| 指すもの | 呼び名 | 場所 |
|---|---|---|
| 目的 | `objective` / `llm_objective_text` / `imposed_goal` / `goal` / `objective_text` | models.py:84, 156、move_translation.py:32-35、RT:2020-2158 |
| シナリオそのもの | `scenario` / `world` / `environment` (`environment_name = metadata.title`) / `ScenarioLoadResult` | move_translation.py:34、RT 全体 |
| 人物 | `player` / `spawn` / `PlayerSpawnConfig` / `participant` [推測: 他領域] / Being に入るときは `Introduction` | models.py:130、move_translation.py:49 |
| 人の性格の文 | `persona_prompt` (シナリオ) / `persona` (system prompt の block) / `Persona` (Being の人柄、name と first_person だけ) | parse_actors.py:380、RT:4189-4223, 6722 |
| 場所の ID のキー | `spawn_spot` / `spot` / `target_spot` / `board_spot` / `required_spot` / `from` `to` / `from_spot_id` `to_spot_id` / `parent_id` / `origin.area_id` | 各 parse_* |
| 物体の ID のキー | `target_object` (JSON) → `object_id` (ドメインの parameters) / `object_id` (distant_cues.source の JSON) / `target` (reactive_bindings.objects) | parse_interaction_effects.py:309-310、parse_map.py:297、parse_reactive_bindings.py:119 |
| 道の ID のキー | `target_connection` (効果) / `target` (reactive_bindings.passages) | parse_interaction_effects.py:313、parse_reactive_bindings.py:48 |
| 品目の ID のキー | `item_spec` / `required_item` / `required_items` / `spec` (initial_items の object 形) / `item_spec_id_parameter` / `item_spec_id_parameter_key` / `input_item_spec_ids` `output_item_spec_id` (COMBINE_ITEMS) | 各所 |
| 旗の名前のキー | `flag_name` (効果・前提・出来事) / `target_flag` (終了条件の FLAG_SET) / `flag` (ongoing_conditions、RESOLVE_ONGOING_CONDITION) / `required_flag` (description_variants) / `required_flags` `forbidden_flags` (モンスター・終了条件) / `unless_flag_set` (state_display) | parse_world.py:634-635 が名前の違いをエラー文で案内している |
| 状態の更新 | `state_updates` / `new_state` (CHANGE_OBJECT_STATE の旧名。CHANGE_PASSAGE_STATE では別の意味) / `on_true_state_updates` | parse_interaction_effects.py:301-306 |
| 条件 | interaction の `preconditions` (`InteractionCondition`、AND だけ) / 出来事の `conditions` と reactive の `predicate` と outcome の `trigger`・`player_conditions` (`ScenarioEventCondition`、木) / 終了条件 (`GameEndCondition`) / モンスターの `spawn_condition` / 道の `passage_conditions` / 発見の `discovery_condition` | 6 系統。同じ「旗が立っている」が `FLAG_SET` という同名で 3 系統に別々にある |
| 時間帯の名前 | `day_night_phases` (モンスター) / `required_time_of_day_phase` (前提) / `phases[].name` (宣言) | parse_actors.py:329、parse_interaction_conditions.py:174 |
| 天候の名前 | `weather_types` (モンスター、enum の name で照合) / `required_weather_type` (前提、enum の value で照合) / `weather_type` (出来事の条件、value で照合。初期値は name で引く) | parse_actors.py:337, parse_interaction_conditions.py:236, parse_scenario_events.py:330, parse_world.py:492 |
| 文字列 ID | `string_id` / `id` / `sid` / `*_str_id` | models.py 全体 |
| 宣言を表す型の接尾辞 | `Def` (`AreaDef`, `InteractionDef`, `ScenarioEventDef`) / `Definition` (`ItemSpecDefinition`, `ScenarioLootTableDefinition`) / `Config` (`PlayerSpawnConfig`, `ScenarioWeatherConfig`) / `Spec` (`InitialItemSpec`, `PlayerAttributeSpec`) / `Scenario*` の接頭辞 | models.py |
| 失敗 | `ScenarioLoadError` (I) と、各ドメイン例外 (`*ValidationException`) | 2.6 |

## 6. 分からなかったこと・食い違い

### 分からなかったこと

- **D1522 という設計判断のファイルは見つからなかった**。`docs/design_decisions/` に D1522 は無く、索引にも無い。#1522 は docs/scenario_engine_capabilities.md:3, 15 で「残る抜け道 (必須キーの欠け、値の綴り違い、包む層のキー)」の Issue として名前が出るだけ。2.6 の素通りの例外はこの Issue の範囲と重なる [確認: 文書の記述のみ。Issue 本文は読んでいない]
- 品目の id が重複したとき、`InMemoryItemSpecRepository.save` が後勝ちになるかは読んでいない [推測]
- 物体 id が別の場所で重複したときに、実行中に何が起きるか (どちらの物体が操作されるか) は確かめていない
- `CREATE_CONNECTION` の `from_spot_id` / `to_spot_id` が実行時にどう解決されるか (文字列のまま渡ったときに何が起きるか) は確かめていない
- `ItemSpec.__post_init__` と `PlayerStateValidationException` が二重に守っているというコメント (parse_economy.py:435-437、parse_actors.py:593-594) は、ドメイン側を開いて確かめていない
- `monster spawn_condition` の時間帯の名前が、宣言した時間帯と照合されないまま run に入ったとき (validate_features.py:157-172 は前提条件の `required_time_of_day_phase` だけを見る) にどうなるかは確かめていない [推測: 永久に出現しない]

### 食い違い・ちぐはぐ [確認]

1. **同じ種類の検査が経路によってあったり無かったりする**
   - `action_name` の重複: 品目 (parse_economy.py:342-345) と対人 (parse_interactions.py:338-341) は検査するが、物体の操作は検査しない (M22)
   - 旗を誰かが立てられるか: 異常 (O1) は検査するが、前提条件・出来事・終了条件・モンスター出現は検査しない (O6, T11)
   - 列挙値: 天候は前提条件・出来事の条件・モンスターでは `ScenarioLoadError` で止めるが、天候の初期値は `KeyError` (X5)。明るさは前提条件では止めるが、場所の `atmosphere.lighting` は `KeyError`
   - 知らないキー: 前提条件・効果・出来事の条件・チーム・round_assignment・ongoing は拒否するが、トップレベル・spots・objects・connections・players・item_specs・終了条件・metadata は黙って捨てる (G3, T10)。`players[]` は知らないキーを弾かないことが parse_actors.py:573-574 にも書いてある
   - 配列でないものを渡したとき: `scenario_events` / `player_interactions` / `merchants` は拒否するが、`synchronized_action_groups` / `reactive_bindings` / `monsters` は黙って空にする
2. **天候の名前の照合が name と value で分かれている**: モンスターの `weather_types` と天候の初期値は enum の name (`WeatherTypeEnum[w]`)、前提条件と出来事の条件は value。今は name と value が同じ綴りなので表に出ていない (weather_enum.py:9-10) [推測: 綴りがずれた enum を足すと片方だけ通る]
3. **`ScenarioIdMappingError` は `ScenarioLoadError` の子ではない**。`declaring` が場所を前に付けないので、存在しない spawn_spot を書くとファイル名もどの人物かも出ない。`parse_required_spot_id` (parse_interaction_conditions.py:253-260) と出来事の条件 (parse_scenario_events.py:417-425) だけが包み直している
4. **`ScenarioLoadError` の基底が `Exception` で、ドメイン例外と別の階層**。CLAUDE.md の「ドメイン層ではドメイン例外」の決まりは domain 層の話なので違反ではないが、読み込みの失敗の型が 4 系統 (SLE / MapErr / 組み込み / ドメイン例外) に割れている
5. **`ScenarioNeedsConfig.__post_init__` が infrastructure の DTO の中で組み込みの `ValueError` を投げる** (models.py:382-405)。他の宣言の型は検査を持たない
6. **`declared_action_names` は `connections[].interactions` を数える** (parse_helpers.py:435-437) が、`parse_connections` は道の `interactions` を読まない (parse_map.py:520-564)。`SpotConnection` に `interactions` の欄は無い。道に書いた操作は同期の名前の検査を通すのに、世界には現れない [確認: コードの読み。実物の 19 本に道の `interactions` を書いたものは無い]
7. **`spot_map_validator` は読み込みと別の規則を持つ**。`UNKNOWN_SPOT_AREA_ID` などは読み込みでは通る (M6)。同じ「area の宣言の整合」が 2 か所 (parse_map.py の area 検査と spot_map_validator.py:467-640) に別々に書かれている
8. **`description` のような作者向けの項目が、読まれる場所と捨てられる場所がある**。`metadata.description` と `areas[].description` は保持して表示しない (models.py:203-211)。終了条件の `description` (station_drill.json) は読まれずに捨てられる
9. **勝つ役 `"crew"` が runtime に直書き** (RT:4144)。シナリオの `metadata.role_labels` で呼び名は宣言できるのに、点検で勝つ役の識別子はシナリオから来ない
10. **`round_assignment` があるときだけ人物 id の重複を検査する** (parse_round_assignment.py:81-84)。無いシナリオでは同じ id の人物が 2 人通る (P1)。手元の実行で `[('p1', 1, 'アキ'), ('p1', 1, 'ベン')]` を確認した
