# 範囲 C: エージェントの行動が世界を変える経路 (働きかけと効果)

- 読んだ版: origin/main `21a33e4c9` (Merge #1935)
- パスは特記がなければ `src/ai_rpg_world/` からの相対。行番号はこの版のもの
- 【事実】はコードを読んで確かめたこと。【推測】は読んだ範囲からの見立てで、実行や試験では確かめていない
- 観測 (Observation) への変換は、ドメインイベントを `publish_all` / `context.collect_all` に渡すところまでを書いた

---

## 0. 全体の見取り図 (要約)

【事実】働きかけの経路は 1 本ではなく、入口ごとに別の application サービスがある。効果 (`InteractionEffect`) を使うのはそのうち 6 か所で、どれも同じドメインサービス `WorldGraphEffectService.apply_effects` を呼び、返ってきた「指示書 (spec)」を各自で世界へ当てている。

| 入口 (LLM ツール) | application の実行者 | 効果の仕組み | 確定境界 (CommandScope) |
|---|---|---|---|
| `interact` (物体) | `SpotInteractionApplicationService.execute_interaction` | `SpotInteractionService.execute_interaction` → `apply_effects` | あり (CALL_MEETING 宣言時だけ無し) |
| `interact` (所持道具) | `SpotInteractionApplicationService.execute_item_interaction` | `SpotInteractionService.execute_declared_interaction` → `apply_effects` | あり (同上) |
| `interact` (相手プレイヤー) | `PlayerInteractionApplicationService.execute` | `can_interact` + `apply_effects` を直接 | あり |
| (tick) scenario_events | `SpotGraphScenarioEventStageService._apply_event` | `apply_effects` を直接 | あり (event 1 件ごと) |
| (tick) 同期行動の解決 | `SynchronizedActionResolverStageService` | `apply_effects` を直接 | 呼び出し元次第 (未確認) |
| (会議開始) 異常の解決 | `MeetingCommandService._resolve_ongoing_conditions` と `WorldRuntime._resolve_ongoing_conditions_on_meeting_start` | `apply_effects` を直接 | 前者は scope 内 |
| `travel_to` | `SpotGraphMovementApplicationService` | 効果を使わない。`SpotGraphAggregate.move_entity` | あり |
| `drop_item` / `pickup_item` / `give_item` | `SpotGraphItemTransferService` | 効果を使わない | あり |
| `attack` (対モンスター) | `SpotAttackOrchestrator.execute_player_attack` | 効果を使わない | **無し** |
| `use_item` (消費) | `SpotGraphToolExecutor._execute_use_item_in_scope` (LLM 層) | `ItemEffect` (別の効果体系) を `ConsumableUsedEvent` のハンドラで当てる | あり |
| `speak` / `say_inline` | `PlayerSpeechService.speak` | 効果を使わない。`PlayerStatusAggregate.speak` がイベントを積むだけ | **無し** (即 publish) |
| reactive_bindings (tick) | `ReactiveObjectStateBindingStageService` / `ReactivePassageBindingStageService` | 効果を使わない。application が state を直接書く | あり |

ドメインの `apply_effects` は「物体 (`SpotInterior`) と旗 (`flags`) は自分で書き換えた新しい値を返す」「アイテムと PlayerStatus は渡された集約を in-place で書き換える」「それ以外 (ダメージ・転移・接続・欲求・gold・会議…) は spec を積んで返すだけ」の 3 通りが混在している (§2)。

---

## 1. 行動 1 件の処理の流れ (物体への `interact` を代表に)

### 1-A. LLM のツール呼び出しから application まで

1. Phase B が LLM の tool_call を取り出し、`action` trace を残す — `application/llm/services/world_llm_turn/phase_b.py:192-230`
2. 移動中 (busy) なら、重い行動の前に移動を中断して状態を控える — `phase_b.py:237` (`maybe_interrupt_busy`)
3. `execute_tool` が「今回のプロンプトで出していないツールは実行しない」を 1 か所で守る — `application/llm/services/world_llm_turn/tool_dispatch.py:1178-1194`。ハンドラが無ければ `UNSUPPORTED_TOOL` — `:1196-1216`
4. resolver がラベル (`target_label` 等) を内部 ID (`object_id`, `action_name`) に置き換える。解決できなければ失敗 DTO — `tool_dispatch.py:813-908`
5. ハンドラ `SpotGraphToolExecutor._interact`:
   - 疲労上限なら止める — `application/llm/services/executors/spot_graph_tool_executor.py:900-902`
   - 引数で分岐: `target_player_id` → 対人、`item_spec_id` → 道具操作 — `:905-908`
   - 準備行動 (同期行動の一部) なら `_prepare_action` へ — `:926-927`
   - `runtime.do_interact` を呼ぶ — `:946-953`
   - 成功後に疲労を加算 (確定境界の外、別保存) — `:955`
   - `InteractionNotAllowedException` → 前提条件失敗の結果文、`InteractionNotFoundException` → 使える操作の一覧 — `:971-1014`
6. `WorldRuntime.do_interact` が `SpotInteractionApplicationService.execute_interaction` を呼び、終わったら `_process_graph_events` (グラフに残ったイベントを観測パイプラインへ) と行動記録 — `application/world_runtime/world_runtime.py:2359-2400`
7. ハンドラの後で `say_inline` (行動に添えた発言) を出す。行動が失敗しても出す — `application/llm/services/world_llm_turn/say_inline_delivery.py:26-40`
8. Phase B に戻り、失敗なら中断した移動を元に戻す — `phase_b.py:279-294`。行動結果の記録、ループ検知、失敗観測 — `:353-418`

### 1-B. application: `SpotInteractionApplicationService`

9. CALL_MEETING を宣言した操作なら、scope を開かずに別経路 — `application/world_graph/spot_interaction_application_service.py:1044-1063`
10. それ以外は `CommandScope` を開き、scope 専用の repository と「イベントを context に集める publisher」を使う — `:1067-1097`。`_CommandContextEventPublisher.publish_all` は `context.collect_all` するだけ — `:160-167`
11. `_execute_interaction_with_repositories` (以下この中):
    1. グラフを読み、行為者の居場所を決める (去った主体は `DepartedPositionStore`、それ以外はグラフの presence) — `:1131-1133`, `:285-296`
    2. interior / inventory を読む。無ければ `ApplicationException` — `:1135-1147`
    3. 所持品目 (集合と個数)、世界フラグ、acting/target の item instance、PlayerStatus、時刻帯、天候、同席人数、表示名、実効照明を集める — `:1149-1237`
    4. 待ち時間 (cooldown) が残っていれば断る — `:1243`, `:466-488`
    5. 主体の存在層 (生者 / 去った主体) が許されているか — `:1244-1245`
    6. **ドメイン呼び出し** `SpotInteractionService.execute_interaction` — `:1248-1266`
       - 物体と操作を探す。無ければ `UnknownSpotObjectException` / `InteractionNotFoundException` — `domain/world_graph/service/spot_interaction_service.py:757-762`
       - 前提条件を宣言順に評価し、最初の不成立で `InteractionNotAllowedException` (パズルの入力欠けは `InteractionParameterMissingException`) — `:763-782`, `:241-267`, `:79-91`
       - 効果が要求する品目削除を全量で先に検算し、足りなければ `InsufficientEffectItemsException` — `:784-791`, `:931-956`
       - `WorldGraphEffectService.apply_effects` — `:793-805`
       - `WorldGraphEffectResult` を `InteractionExecutionResult` に詰め替える — `:806-830`
    7. 前提条件で断られたら、失敗観測を (scope 内では) 保留し、例外を上げる — `spot_interaction_application_service.py:1272-1295`。scope が rollback した後、確定状態から `SpotObjectInteractionFailedEvent` を発行 — `:1099-1108`, `:998-1024`
    8. 在室数表示 (`SHOW_ROOM_OCCUPANCY`) の文面を作る — `:1297`
    9. CALL_MEETING なら会議招集 command に任せて終わる — `:1299-1301`, `:1631-1657`
    10. 永続化の前の検算: 未予約品で削除全量を確保できるか (`_require_removable_items`)、gold を払えるか (`_require_payable_gold`、取引で凍結中の gold を除く) — `:1303-1304`, `:1659-1687`, `:1716-1735`
    11. 世界フラグを結果で置き換える — `:1306-1312`
    12. interior を保存 — `:1314-1315`
    13. gold を払う (`PlayerStatusAggregate.pay_gold`) — `:1316-1321`, `:1689-1714`
    14. 通路の状態 → `graph.set_connection_passage_state` — `:1323-1334`
    15. 転移 → `graph.teleport_entity` (去った主体は `DepartedPositionStore.move`) — `:1344-1379`
    16. 雰囲気 → `graph.update_spot_atmosphere` — `:1386-1393`
    17. 品目付与 → `grant_item_specs_to_inventory` (溢れは overflow sink へ) — `:1395-1403`
    18. 品目削除 → `remove_items_of_specs_from_inventory`、失敗なら `ApplicationException` — `:1405-1421`
    19. item instance / PlayerStatus の自由 state が変わっていれば保存 — `:1425-1447`
    20. 接続の削除と作成 (新しい ID は application が採番) — `:1449-1465`
    21. ダメージ → `PlayerStatusAggregate.apply_damage`、集約イベント (`PlayerDownedEvent`) を回収 — `:1488-1499`
    22. 状態異常 → `add_status_effect` (期限 = 現在 tick + duration を application が計算) — `:1505-1534`
    23. 欲求回復 → `satisfy_need` — `:1537-1556`
    24. グラフのイベントを回収し、転移の到着文を差し替え、グラフを保存 — `:1559-1562`
    25. `SpotObjectInteractedEvent` を application が組み立て、`PUBLIC_OBSERVABLE` 効果から `SpotPublicEffectObservedEvent` 系を作り、グラフ・ダメージのイベントと一緒に publish (= context へ集める) — `:1565-1610`
    26. 待ち時間の起点を記録 (成功のときだけ) — `:1619`
    27. `SpotInteractionResultDto` を返す — `:1621-1629`
12. scope を抜けると、集めたイベントを同期ハンドラで処理 → commit → commit 後の配送へ渡す — `application/common/command_scope.py:263-321`。どこかで例外が出れば repository の transaction と、世界フラグ・待ち時間・去った主体の位置の rollback 参加者がまとめて戻る — `infrastructure/unit_of_work/interaction_rollback_participants.py:172-190`

### 1-C. ドメイン: `apply_effects` の中

- `RESOLVE_ONGOING_CONDITION` を、シナリオの `ongoing_conditions[].resolution` に宣言された効果列へ展開 (循環は例外) — `domain/world_graph/service/world_graph_effect_service.py:88-118`
- 可変の作業領域 `EffectApplicationState` を作る — `:175-189`, `domain/world_graph/service/effect_application/context.py:34-74`
- 効果を宣言順に 1 件ずつ `dispatch_effect` — `world_graph_effect_service.py:191-192`, `effect_application/registry.py:33-42`
- item instance / PlayerStatus の state が前後で変わったかを比べ、効果サマリを可視性で 3 つに分けて返す — `world_graph_effect_service.py:194-235`

---

## 2. 効果の種類の一覧

凡例 — 「書き方」: **直** = ドメインの handler が値を書き換える / **集** = ドメインの handler が渡された集約を in-place で書き換える / **指** = spec を積むだけで、書き換えは application。

| 効果 | 変える状態 | 状態の持ち主 (集約 / 保存先) | 書き方 | 守っている規則 (根拠) |
|---|---|---|---|---|
| SET_FLAG / CLEAR_FLAG | 世界フラグの集合 | `MutableWorldFlagState` (application、`WorldFlagRegistry` を内包) | 直 (集合を返す) → app が丸ごと置換 | flag_name が文字列でなければ黙って無視 (`handlers/flags.py:17-26`)。CLEAR は無くても成功 |
| RESOLVE_ONGOING_CONDITION | (展開先の flag 効果に依る) | 同上 | 展開 | 参照先 resolution が無い・循環は例外 (`world_graph_effect_service.py:100-117`) |
| SHOW_MESSAGE | 本人向け文面 | なし (結果文) | 直 | 文字列以外は無視 (`handlers/messages.py:49-52`) |
| SHOW_ROOM_OCCUPANCY | 本人向け文面 | なし | 指 (`RoomOccupancyDisplaySpec`) | interaction 以外では読み込みで拒否 (`infrastructure/scenario/parse_interaction_effects.py:328-332`) |
| WRITE_PLAYER_TEXT | 物体 state (本文・書き手・tick) | `SpotInterior` (`ISpotInteriorRepository`) | 直 | 本文必須 (欠ければ `InteractionParameterMissingException`)、200 字で切り詰め + 本人に通知、3 キーを自動で隠しキーに (`messages.py:59-93`) |
| SHOW_PLAYER_TEXT | 本人向け文面 | なし | 直 | 未記入なら既定文 (`messages.py:96-106`) |
| CHANGE_OBJECT_STATE | 物体 state (部分上書き) | `SpotInterior` | 直 | 対象が解決できなければ黙って何もしない (`handlers/object_state.py:175-197`) |
| INCREMENT_OBJECT_STATE | 物体 state の整数 | `SpotInterior` | 直 | state_key 必須 (無ければ警告ログでスキップ)。現在値が整数でなければ 0 から (`object_state.py:40-82`) |
| CONSUME_OBJECT_STOCK | 物体 state (`stock`, `stock_tick`) | `SpotInterior` | 直 | 経過 tick から再生を算出して減算、0 未満にしない (`object_state.py:137-172`, `service/stock_pool_regen.py`) |
| RECORD_OBJECT_STATE_TICK | 物体 state に現在 tick | `SpotInterior` | 直 | tick が無ければ警告でスキップ。書いたキーを隠しキーに (`object_state.py:218-239`) |
| REVEAL_OBJECT | 物体の `visible` | `SpotInterior` | 直 | 同じ interior に無ければ黙って何もしない (`object_state.py:200-206`) |
| REVEAL_SUB_LOCATION | 小区画の発見済み | `SpotInterior` | 直 | 同上 (`object_state.py:209-215`) |
| DEPOSIT_ITEM_TO_OBJECT | 物体 state の累積 + 行為者の所持品削除 | `SpotInterior` + `PlayerInventoryAggregate` | 直 + 指 (削除リスト) | 削除数と加算数を同じ値から作る。所持数を超えて預けない (`handlers/items.py:90-119`, `item_transfer.py:131-166`)。interaction 以外では読み込みで拒否 |
| DEPOSIT_GOLD_TO_OBJECT | 物体 state の累積 + 行為者の gold | `SpotInterior` + `PlayerStatusAggregate` | 直 + 指 (`DepositGoldSpec`) | 読み込み時に `PLAYER_GOLD_AT_LEAST` の閾値 ≧ 納額を強制 (`parse_interactions.py:35-74`)。永続化前に凍結分を除いた残高で再検算 (`spot_interaction_application_service.py:1659-1687`)。不足は `InsufficientGoldException` (`player_status_aggregate.py:588-608`) |
| GIVE_ITEM | 所持品 (付与) | `PlayerInventoryAggregate` + `ItemAggregate` (新規生成) | 指 (付与リスト。行為者用 / 対象用) | `target=TARGET_PLAYER` なのに対象が無ければ例外 (`item_transfer.py:106-128`)。品目を実行時引数で決める場合は引数必須 (`item_transfer.py:51-80`)。quantity は負を 0 に (`:30-42`) |
| GIVE_FROM_LOOT_TABLE | 所持品 (抽選付与) | 同上 + `LootTableRepository` (item 文脈) | 指 | repository 未注入・ID 不正・表が無いときは警告でスキップ。times は 1..100 に丸める (`items.py:53-74`)。常に行為者へ |
| REMOVE_ITEM | 所持品 (削除) | `PlayerInventoryAggregate` / `ItemRepository` | 指 | 実行前に全量を検算 (`spot_interaction_service.py:931-956`)。適用時に足りなければ `ApplicationException` (`spot_interaction_application_service.py:1412-1420`) |
| COMBINE_ITEMS | 入力の削除 + 出力の付与 | 同上 | 指 | 入力全量の検算は REMOVE と共通 (`item_transfer.py:201-202`) |
| CHANGE_ITEM_INSTANCE_STATE / RECORD_ITEM_INSTANCE_STATE_TICK | 使う側の item instance state | `ItemAggregate` (`ItemRepository`) | 集 | 集約が渡されていなければ警告でスキップ (`handlers/item_instance.py:29-80`)。acting と target が同一 instance なら `ValueError` (`world_graph_effect_service.py:165-169`) |
| CHANGE_TARGET_ITEM_INSTANCE_STATE / RECORD_TARGET_… | 使われる側の item instance state | 同上 | 集 | 同上 (`item_instance.py:83-134`) |
| CHANGE_PLAYER_STATE / RECORD_PLAYER_STATE_TICK | 行為者の自由 state | `PlayerStatusAggregate` (`PlayerStatusRepository`) | 集 | 値は JSON の素の型に限る (`player_status_aggregate.py:303-307`)。集約が無ければ警告でスキップ (`handlers/player_state.py:29-76`)。変えられない属性への書き込みは読み込みで拒否 (`parse_interaction_effects.py:192-225`) |
| APPLY_DAMAGE | HP、倒れ (`is_down`) | `PlayerStatusAggregate` | 指 (`DamageSpec`、行為者用 / 対象用) | 0 以下は no-op。HP 0 で `PlayerDownedEvent` (`player_status_aggregate.py:431-449`)。対象が無い `TARGET_PLAYER` は例外 (`item_transfer.py:83-103`) |
| APPLY_STATUS_EFFECT | 状態異常の一覧 | `PlayerStatusAggregate` | 指 (`StatusEffectSpec`) | 種類名が空か期間 ≦ 0 なら黙って無視 (`handlers/cross_domain.py:79-101`)。種類名の妥当性は読み込みで確かめていない (§6) |
| SATISFY_NEED | 欲求 | `PlayerStatusAggregate` | 指 (`SatisfyNeedSpec`) | 量 ≦ 0 は無視 (`cross_domain.py:209-229`)。その欲求を持たないプレイヤーなら黙って何もしない (`player_status_aggregate.py:204-208`) |
| TELEPORT_ENTITY | 行為者の居場所 | `SpotGraphAggregate` (presence) / `DepartedPositionStore` | 指 (`TeleportSpec`) | 接続も通行条件も見ない。同じ場所なら何もしない (`spot_graph_aggregate.py:324-399`)。visibility 指定は読み込みで拒否 (`parse_interaction_effects.py:386-404`) |
| CHANGE_ATMOSPHERE | 場所の明るさ・気温・危険度 | `SpotGraphAggregate` (SpotNode) | 指 (`AtmosphereUpdateSpec`) | enum 名は読み込みで検証 (`parse_interaction_effects.py:464-500`) |
| CREATE_CONNECTION | 接続の追加 | `SpotGraphAggregate` | 指 (`CreateConnectionSpec`) | passage 省略時は開いた通路として警告 (`cross_domain.py:159-190`)。ID 重複・端点不明は集約が例外 (`spot_graph_aggregate.py:249-275`) |
| DESTROY_CONNECTION | 接続の削除 (双方向なら逆向きも) | `SpotGraphAggregate` | 指 | 未知の接続は集約が例外 (`spot_graph_aggregate.py:637-659`) |
| CHANGE_PASSAGE_STATE | 通路 (扉・壁) の状態 | `SpotGraphAggregate` (`SpotConnection.passage`) | 指 (`PassageStateUpdateSpec`) | kind を保ったまま状態遷移 (`spot_graph_aggregate.py:611-635`)。通れるかが変わったときだけ `ConnectionStateChangedEvent` |
| CALL_MEETING | ゲームの段階 (会議) | `GamePhaseStore` 他 (会議 command) | 指 (trigger 文字列) | 単独の効果としてしか宣言できない (`value_object/interaction_def.py:100-106`)。trigger は許可値のみ (`interaction_effect.py:14`, `cross_domain.py:46-54`) |

### 2-1. 入口ごとに「どの spec を当てるか」が違う

【事実】`apply_effects` はどの入口でも全種類の spec を作り得るが、当てる側は入口ごとに部分集合しか当てない。

| spec | 物体 interact | 道具 interact | 対人 | scenario_event | 同期行動 | 会議開始 |
|---|---|---|---|---|---|---|
| flags | ○ | ○ | ○ | ○ | ○ | ○ |
| messages | ○ | ○ | ○ | ○ | ○ | ○ |
| interior (物体 state) | ○ | ○ (明示対象の部屋) | 捨てる (空 interior) | ○ (取っ掛かりの物体の部屋だけ) | 捨てる (警告) | 捨てる |
| grant / remove | ○ | ○ | ○ (行為者・対象) | **全プレイヤー**に付与・削除 | 無視 | 無視 |
| damage | ○ | ○ | ○ (行為者・対象) | **黙って無視** | 無視 | 無視 |
| status_effect | ○ (未知種は警告スキップ) | ○ (未知種は `ValueError`) | **無視** | **黙って無視** | 無視 | 無視 |
| satisfy_need | ○ (未知種は警告スキップ) | ○ (未知種は `ValueError`) | **無視** | **黙って無視** | 無視 | 無視 |
| teleport | ○ | ○ | **無視** | 警告して無視 | 無視 | 無視 |
| atmosphere | ○ | ○ | 無視 | ○ | 無視 | 無視 |
| create/destroy connection | ○ | ○ | 無視 | ○ | 無視 | 無視 |
| passage | ○ | ○ | 無視 | ○ | ○ | 無視 |
| deposit_gold | ○ | ○ | 無視 | (読み込みで拒否) | — | — |
| meeting_call | ○ (別 command) | ○ (別 command) | 無視 | 無視 | 無視 | 無視 |
| item instance / player state | ○ | ○ (acting のみ) | player state のみ | (集約を渡さないので handler が警告スキップ) | 同 | 同 |

根拠: 物体 `spot_interaction_application_service.py:1297-1610`、道具 `:813-960`、対人 `application/world_graph/player_interaction_application_service.py:971-1077`、scenario_event `application/world_graph/spot_graph_scenario_event_stage_service.py:326-432`、同期行動 `application/world_graph/synchronized_action_resolver_stage_service.py:252-293`、会議 `application/world_graph/meeting_command_service.py:557-585`, `application/world_runtime/world_runtime.py:2567-2601`。

読み込みが拒否している組み合わせ (【事実】):
- `target=TARGET_PLAYER` を取れるのは GIVE_ITEM / REMOVE_ITEM / APPLY_DAMAGE だけ。APPLY_STATUS_EFFECT / SATISFY_NEED / TELEPORT_ENTITY / CHANGE_PLAYER_STATE / RECORD_PLAYER_STATE_TICK は「未配線」として拒否 — `parse_interaction_effects.py:27-43`, `:118-167`
- interaction 以外 (scenario_event 等) では `TARGET_PLAYER`、SHOW_ROOM_OCCUPANCY、DEPOSIT_*、scenario_event の RECORD_PLAYER_STATE_TICK を拒否 — `:142-147`, `:275-280`, `:328-372`
- `ongoing_conditions[].resolution` は SET_FLAG / CLEAR_FLAG だけ — `infrastructure/scenario/parse_world.py:99-161`
- 対人行為は `TARGET_PLAYER` の効果を 1 つ以上持つ必要がある — `parse_interactions.py:351-358`

読み込みが拒否していない組み合わせ (【事実】: 拒否するコードが見つからなかった): 対人行為の `target=ACTOR` の APPLY_STATUS_EFFECT / SATISFY_NEED / TELEPORT_ENTITY / CHANGE_ATMOSPHERE / 接続系 / CALL_MEETING、scenario_event の APPLY_DAMAGE / APPLY_STATUS_EFFECT / SATISFY_NEED / CHANGE_PLAYER_STATE / CALL_MEETING。いずれも上表のとおり当てる側が無視する。

### 2-2. 効果を使わない行動の状態変更

| 行動 | 変える状態 | 持ち主 | 守っている規則 (根拠) |
|---|---|---|---|
| travel_to 開始 | 移動予定 (`PlayerSpotNavigationState`) | `PlayerStatusAggregate` | 移動中は二重に始めない、経路が無ければ断る、各区間が今通れるか (`application/world_graph/spot_graph_movement_application_service.py:197-264`) |
| travel 1 tick | 居場所 (presence) と移動予定 | `SpotGraphAggregate` + `PlayerStatusAggregate` | 接続の始点に居ること、通行条件 (`spot_graph_aggregate.py:401-449`)。途中で通れなくなったら出発側で止める (`movement…:307-331`) |
| drop_item | 所持品 → 地面 | `PlayerInventoryAggregate` + `SpotInterior.ground_items` | 空のスロットは断る (`application/world_graph/spot_graph_item_transfer_service.py:312-386`) |
| pickup_item | 地面 → 所持品 | 同上 | 地面に無ければ断る、満杯なら断る (`:414-483`) |
| give_item | 所持品 → 相手の所持品 | `PlayerInventoryAggregate` ×2 | 自分には渡せない、相手が死亡・倒れていれば断る、同じ場所、相手が満杯なら断る (`:535-609`) |
| attack (対モンスター) | モンスター HP、攻撃した相手の記録 | `MonsterAggregate` + `SpotGraphAggregate` (イベント) + `PlayerStatusAggregate` | 判定はドメインの `try_attack` (`application/world_graph/spot_attack_orchestrator.py:270-321`)。疲労上限で止める (`spot_graph_tool_executor.py:2718-2720`) |
| use_item (消費) | 数量、所持品、HP / 欲求 | `ItemAggregate` + `PlayerInventoryAggregate` + `PlayerStatusAggregate` | CONSUMABLE 種別だけ。腐っていればダメージ + 空腹の一部回復 (`spot_graph_tool_executor.py:1272-1369`)。新鮮なら `ConsumableUsedEvent` → `application/world/handlers/consumable_effect_handler.py:68-135` |
| speak | 状態は変えない。`PlayerSpokeEvent` を積む | `PlayerStatusAggregate` (イベントだけ) | 倒れていれば話せない、空文不可、囁きは宛先必須 (`domain/player/aggregate/player_status_aggregate.py:761-796`)。去った主体は application が直接イベントを積む (`application/speech/services/player_speech_service.py:101-118`) |
| reactive object binding | 物体 state | `SpotInterior` | 述語の真偽に応じて部分上書き、値が同じなら保存しない (`application/world_graph/reactive_object_state_binding_stage_service.py:115-195`) |
| reactive passage binding | 通路の状態 | `SpotGraphAggregate` | 目標状態ならスキップ。双方向は 1 回だけ通知 (`reactive_passage_binding_stage_service.py:82-146`) |

### 2-3. 会話の届く範囲 (入口まで)

【事実】`PlayerSpokeEvent` の配信先は `SpotGraphSpeechRecipientStrategy` が決める — `application/observation/services/recipient_strategies/spot_graph_speech_recipient_strategy.py`。
- 囁き: 宛先が同じ場所にいるときだけ宛先 1 人
- 発言・叫び: `SoundPropagationService.resolve_recipients` (ドメイン) の音の伝わり方
- 去った主体 (幽霊) が話す / 聞くときは、`outcome_between_spots` で場所どうしの伝わり方を見る
- 話者の場所は `DepartedPositionStore` → グラフの presence の順に引く

---

## 3. 不変条件

「層」: D = domain、A = application、L = 読み込み (infrastructure/scenario)。「分類」: ドメイン = ドメインの規則 / 宣言 = シナリオの宣言を確かめているだけ / 都合 = 実装の都合。

| # | 規則の文 | どこで守るか | 守り方 | 層 | 分類 |
|---|---|---|---|---|---|
| 1 | 今プロンプトで出していないツールは実行できない (会議中に隠した interact 等) | `tool_dispatch.py:1185-1194` | 例外ではなく失敗 DTO | A (LLM) | ドメイン (行為の可能性と実行の一致) |
| 2 | 前提条件は宣言順の AND。最初の不成立で止まる | `spot_interaction_service.py:241-267` | 例外 (`InteractionNotAllowedException`) | D | ドメイン |
| 3 | 未知の前提条件の種類は不成立 | `spot_interaction_service.py:731` | 不成立として断る | D | 都合 |
| 4 | 判定材料 (時刻帯・天候・照明・現在地・PlayerStatus) が渡されていなければ、その条件は不成立 (成立に倒さない) | `spot_interaction_service.py:555, 576, 643, 661, 707, 724` 等 | 不成立 | D | 都合 (配線漏れの静かな成功を防ぐ) |
| 5 | 個数 > 1 を要る所持条件では個数表が必須 | `spot_interaction_service.py:221-237` | `ValueError` | D | 都合 |
| 6 | 対象所持条件は、対象の所持品が渡されていなければ不成立 | `spot_interaction_service.py:184-191` (説明), `:340-367` | 不成立 | D | 都合 |
| 7 | 効果が要求する削除品目は、適用前に全量そろっていること | `spot_interaction_service.py:931-956` (所持数)、`spot_interaction_application_service.py:1716-1735` (未予約品) | 例外 → `ApplicationException` に変換 | D + A (二段) | ドメイン |
| 8 | 削除は全量できるか、何もしないか (部分削除しない) | `spot_interaction_application_service.py:1412-1420` | `ApplicationException` → scope rollback | A | ドメイン |
| 9 | 納める gold は凍結分を除いた残高で払えること | `spot_interaction_application_service.py:1659-1687` | `InteractionNotAllowedException` | A | ドメイン |
| 10 | DEPOSIT_GOLD には納額以上の `PLAYER_GOLD_AT_LEAST` が要る | `parse_interactions.py:35-74` | 読み込み失敗 | L | 宣言 |
| 11 | 物体の state 加算と所持品 / gold の差し引きは同じ値から作る | `handlers/items.py:90-119`, `handlers/object_state.py:85-134` | 構造で保証 | D | ドメイン |
| 12 | `TARGET_PLAYER` の効果は、対象が無ければ行為者に倒さず止める | `item_transfer.py:83-128` | 例外 (`InteractionEffectValidationException`) | D | ドメイン |
| 13 | `TARGET_PLAYER` を取れる効果は 3 種類だけ | `parse_interaction_effects.py:27-43, 155-167` | 読み込み失敗 | L | 宣言 (配線の都合を宣言で塞ぐ) |
| 14 | 使う側と使われる側の item instance は別物 | `world_graph_effect_service.py:165-169`, `spot_interaction_service.py:211-215`, `spot_interaction_application_service.py:1173-1180` | `ValueError` / `ApplicationException` (三重) | D + A | ドメイン |
| 15 | CALL_MEETING は単独の効果としてのみ宣言できる | `interaction_def.py:100-106` | ドメイン例外 | D | ドメイン |
| 16 | 全効果種別に handler と既定の可視性があること | `effect_application/registry.py:21-30`, `effect_application/visibility.py:83-90` | 起動時 `AssertionError` | D | 都合 |
| 17 | 物体の効果対象 (`object_id`) が interior に無ければ、操作した物体に当たる | `effect_application/object_target.py:23-33` | **黙って補う** (別の物体を書き換える) | D | 都合 (§6 で問題視) |
| 18 | 1 回の道具操作で効果を当てる物体は 1 部屋に限る | `spot_interaction_application_service.py:756-787` | `ApplicationException` | A | 都合 |
| 19 | 看板の本文は 200 字まで | `handlers/messages.py:36, 70-83` | 切り詰め + 本人に通知 | D | ドメイン |
| 20 | 看板の本文・書き手・tick は第三者に見せない | `messages.py:46, 80, 91` | 隠しキーに自動追加 | D | ドメイン |
| 21 | 待ち時間 (cooldown) が残っている間は実行できない。起点は成功したときだけ更新 | `spot_interaction_application_service.py:466-514, 1619`、`player_interaction_application_service.py:906-908, 1136` | 例外 | A | ドメイン |
| 22 | 実行できる主体の存在層 (生者 / 去った主体) が宣言されたものだけ | `spot_interaction_application_service.py:361-370, 1244`、`player_interaction_application_service.py:835-837` | 例外 | A (判定は `InteractionDef.allows_actor_plane` D) | ドメイン |
| 23 | 対人行為は自分を対象にできない | `player_interaction_application_service.py:838-844`、give は `spot_graph_item_transfer_service.py:547-551` | 例外 | A | ドメイン |
| 24 | 対人行為と give は同じ場所にいる相手だけ (倒れた相手は身体の位置) | `player_interaction_application_service.py:846-868`, `spot_graph_item_transfer_service.py:573-582` | 例外 | A | ドメイン |
| 25 | 対人行為で受け取る側に空きが無ければ、何も動かす前に断る | `player_interaction_application_service.py:984-1001` | 例外 | A | ドメイン |
| 26 | 対人の奪取は「対象から取り上げ → 行為者へ渡す」の順 | `player_interaction_application_service.py:1010-1042` | 構造 (scope 内) | A | 都合 |
| 27 | 効果で与えた品が持ちきれなければ足元に落とす (行動は成功) | `application/world_graph/overflow_sinks.py:1-15`, `spot_inventory_helpers.py:184-229` | 黙って補う (設計上) | A | ドメイン |
| 28 | HP 0 で倒れ、`PlayerDownedEvent` を出す。イベントは保存より前に回収する | `player_status_aggregate.py:431-449`、回収 `spot_interaction_application_service.py:1488-1499` | 集約 + application の順序 | D + A | ドメイン |
| 29 | 1 回の働きかけは全部当たるか、全部戻る | `command_scope.py:263-321`, `interaction_rollback_participants.py:172-190` | 例外で rollback | A | ドメイン (transaction) |
| 30 | 前提条件で断られた事実は、rollback 後の確定状態から同席者に観測される (秘匿条件と引数欠けは除く、同じ失敗は 24 tick 抑止) | `spot_interaction_application_service.py:1099-1108, 2036-2127` | 黙って抑止 | A | ドメイン (観測の規則) |
| 31 | 転移は接続も通行条件も見ない。同じ場所なら何もしない | `spot_graph_aggregate.py:324-399` | 何もしない | D | ドメイン |
| 32 | 移動は接続の始点にいるときだけ、通行条件を満たすときだけ | `spot_graph_aggregate.py:401-449` | ドメイン例外 | D | ドメイン |
| 33 | 移動中は二重に移動を始めない | `movement…:221-222` | 例外 | A (状態は PlayerStatus) | ドメイン |
| 34 | 移動予定の現在地はグラフの居場所に合わせる | `movement…:212-219` | 黙って補う | A | 都合 (二重管理の帳尻) |
| 35 | 倒れた主体は話せない。空の発言は不可。囁きは宛先必須 | `player_status_aggregate.py:780-785` | ドメイン例外 | D | ドメイン |
| 36 | 去った主体の発言は空でなければよい (倒れていても話せる) | `player_speech_service.py:101-118` | 例外 | A | ドメイン (A に置かれている) |
| 37 | 囁きは同じ場所の宛先にだけ届く | `spot_graph_speech_recipient_strategy.py` (resolve の WHISPER 分岐) | 届けない | A (観測) | ドメイン |
| 38 | 品目が無いか ID が数値でない対象所持条件は「持っていない」 | `spot_interaction_service.py:270-292` | 不成立 | D | ドメイン |
| 39 | 品目を実行時引数で決める効果は、その引数が必須 | `item_transfer.py:51-80` | 例外 | D | 宣言 |
| 40 | 状態異常・欲求の種類名が正しいこと | 物体 `spot_interaction_application_service.py:1515-1525, 1541-1555` / 道具 `:938-949` | 物体: 警告でスキップ / 道具: `ValueError` で全体 rollback / 読み込み: **守っていない** | A | 宣言 |
| 41 | その欲求を持たないプレイヤーへの SATISFY_NEED は何もしない | `player_status_aggregate.py:204-208` | 黙って何もしない | D | 都合 |
| 42 | 未知の visibility は既定値に倒す | `parse_interaction_effects.py:292-299`, `visibility.py:111-122` | 黙って補う (実行時は警告) | L + D | 都合 |
| 43 | 世界フラグの変更は、因果 (入口・行為者) つきで通知される | `application/world_graph/world_flag_state.py:82-117` | 構造 | A | 都合 (trace 用) |

---

## 4. ドメインに置くべき規則が application にあるもの

印 ★ は「ドメインの規則が application にある」と見立てたもの。【事実】は置き場所、★ の判断は【推測】(見立て)。

1. ★ **spec を世界へ当てる規則の全部**。ダメージ・状態異常の期限計算 (`current_tick + duration`)・欲求・転移・雰囲気・接続の採番・通路・gold 支払い。しかも 4〜6 か所に写しがある。
   - 物体 `spot_interaction_application_service.py:1314-1556`、道具 `:829-950`、対人 `player_interaction_application_service.py:1002-1077`、scenario_event `spot_graph_scenario_event_stage_service.py:333-430`、同期行動 `synchronized_action_resolver_stage_service.py:271-292`
   - 写しの間で、未知の種類名の扱い (§2-1)・接続 ID の採番 (`_next_connection_id` と `max_connection_id_value()+1` / `+2`)・保存の順序がずれている
2. ★ 待ち時間 (cooldown) の規則と記録 — `application/world_graph/interaction_cooldown_store.py`、判定 `spot_interaction_application_service.py:383-514`、`player_interaction_application_service.py:332-381`
3. ★ 主体の存在層の拒否 — 判定の核は `InteractionDef.allows_actor_plane` (D) だが、存在層を決める `actor_plane_for` と拒否は A (`spot_interaction_application_service.py:361-370`)
4. ★ 対人行為の成立条件 (自分は不可、同じ場所、対象が行動可能か、受け取り側の空き) — `player_interaction_application_service.py:835-1001`
5. ★ give / pickup / drop の成立条件 (同じ場所、満杯、相手の死亡・倒れ) と、`PlayerDroppedItemEvent` 等を application が組み立てて `aggregate_type="SpotGraphAggregate"` を名乗らせている — `spot_graph_item_transfer_service.py:368-377, 465-474`
6. ★ `SpotObjectInteractedEvent` / `PlayerInteractedWithPlayerEvent` / `SpotObjectInteractionFailedEvent` / 公開効果イベントを application が組み立てる — `spot_interaction_application_service.py:1584-1606, 2116-2127`、`player_interaction_application_service.py:1113-1132`。集約が起こした事実ではない
7. ★ reactive object binding が物体 state を書き、`SpotObjectStateChangedEvent` を `graph.add_event` で外から積む — `reactive_object_state_binding_stage_service.py:156-195`
8. ★ gold の「使える残高」(凍結分を除く) — `spot_interaction_application_service.py:1659-1687` (`_available_gold_provider`)
9. ★ 未予約品で削除全量を確保できるか — `spot_interaction_application_service.py:1716-1735`, `spot_inventory_helpers.py:103-155`
10. ★ 消費アイテムの使用 (腐敗時のダメージと空腹回復、数量 0 で削除) が LLM のツール実行者の中にある — `spot_graph_tool_executor.py:1272-1393`
11. ★ 去った主体の発言を application が `PlayerSpokeEvent` として集約に積む — `player_speech_service.py:101-118`
12. ★ scenario_event の GIVE_ITEM / REMOVE_ITEM を「全プレイヤー」に当てる規則 — `spot_graph_scenario_event_stage_service.py:409-430`
13. ★ 世界フラグの状態本体 (`MutableWorldFlagState`) が application にある。値オブジェクト `WorldFlagRegistry` は D — `world_flag_state.py:41-91`。準備行動はフラグ名の接頭辞 `prepared:{id}:` で表現 (`spot_interaction_service.py:465-471`)
14. ★ 同席人数 (`PLAYERS_AT_SPOT` の材料) を application が数えて渡す — `spot_interaction_application_service.py:1217`
15. ★ 失敗観測の重複抑止の記憶 (`_failure_observation_last_tick`) がサービスの属性 — `spot_interaction_application_service.py:2095-2116`。rollback 参加者でもない

### 4-1. effect handler / ドメインサービスが他文脈の集約・リポジトリを直接触る箇所 【事実】

- `EffectApplicationState` が item 文脈の `ItemAggregate` ×2、player 文脈の `PlayerStatusAggregate` ×2、item 文脈の `LootTableRepository` を持つ — `effect_application/context.py:60-68`
- `handlers/item_instance.py:44-45, 80, 98-99, 134` — `ItemAggregate.merge_state` を in-place で呼ぶ
- `handlers/player_state.py:43, 76` — `PlayerStatusAggregate.merge_state` を in-place で呼ぶ
- `handlers/items.py:64, 70` — `LootTableRepository.find_by_id` と `LootTable.roll` (ドメインサービス内からリポジトリを引く)
- `item_transfer.py:83-128` — 対象の有無の判定に `PlayerStatusAggregate` を使う (中身は見ない)
- `SpotInteractionService` の前提条件評価が `ItemAggregate.state`、`PlayerStatusAggregate` の HP・欲求・gold・state を読む — `spot_interaction_service.py:494-629, 681-694`
- `world_graph_effect_service.py:171-202` — 渡された集約の state を前後で比べて「変わったか」を返し、保存の要否を application に知らせる

【推測】ドメインサービスが「書き換える集約」と「書き換えずに spec で返す集約」の境界に原則が見当たらない。item instance と player の自由 state は直接、HP・欲求・状態異常・所持品は spec。履歴的に後から足した効果ほど直接書く形になっているように読める。

---

## 5. コードの言葉 (ドメインの語彙の候補) と呼び名の揺れ

### 5-1. 語彙の候補

| 概念 | コードの名前 | 補足 |
|---|---|---|
| 働きかけの定義 | `InteractionDef` (action_name, display_label, preconditions, effects, witness_policy, notify_target, cooldown_*, allowed_actor_planes) | 物体・道具・対人で共有 |
| 前提条件 | `InteractionCondition` (`InteractionConditionTypeEnum`) | scenario_event 側は `ScenarioEventCondition`、共通の核は `ScenarioPredicateEvaluator` (D) |
| 効果 | `InteractionEffect` (`effect_type`, `parameters`, `visibility`, `target`) | |
| 効果の結果 | `WorldGraphEffectResult` → `InteractionExecutionResult` → `SpotInteractionResultDto` / `PlayerInteractionResultDto` | 同じ中身を 3 段で詰め替える |
| 世界への指示書 | `DamageSpec`, `TeleportSpec`, … (`cross_domain_effect_spec.py`) | |
| 効果の要約 | `AppliedEffectSummary` (`AppliedEffectKind`, `state_delta`) | 観測の材料 |
| 可視性の 3 軸 | `EffectVisibility` (効果が届くか)、`WitnessPolicy` (第三者に届くか)、`notify_target` (対象本人に届くか) | `interaction_def.py:42-62` |
| 主体の存在層 | `InteractionActorPlane` (LIVING / DEPARTED…) | |
| 待ち時間 | `cooldown_ticks`, `cooldown_group`, `cooldown_key`, `InteractionCooldownScope` (ACTOR / WORLD) | |
| 世界フラグ | `world_flags`, `WorldFlagRegistry`, `MutableWorldFlagState`, `WorldFlagMutationSource` | |
| 場所 | `SpotGraphAggregate`, `SpotNode`, `SpotInterior`, `SubLocation`, `SpotConnection`, `Passage` | |
| 物 | `SpotObject` (state, hidden_state_keys, visible), `GroundItem`, `DiscoverableItem` | |

### 5-2. 同じものを別の名前で呼んでいる / 1 つの名前が複数を指す 【事実】

- **行為者**: `actor` / `acting` / `player_id` / `entity_id` (`EntityId`) / `speaker_player_id` / `attacker` / `from_player_id` / `actor_player_id`。日本語でも「行為者」「本人」「あなた」
- **対象**: `target` が 4 つの意味を持つ。`EffectTarget` (効果の適用先 ACTOR / TARGET_PLAYER)、`target_object` / `target_spot` / `target_connection` (JSON の引数名、読み込みで `object_id` / `spot_id` / `connection_id` に改名 — `parse_interaction_effects.py:307-322`)、`target_item_aggregate` (使われる側の道具)、`target_player_id`
- **居場所**が 5 か所にある: グラフの presence (`SpotGraphAggregate._entity_spot`)、`PlayerStatusAggregate.current_spot_id`、`PlayerSpotNavigationState.current_spot_id`、`DepartedPositionStore`、倒れた身体の位置 (`fallen_body_registry`)
- **働きかけ (interaction)** は、物体への操作、道具の操作 (「登録簿由来」`execute_declared_interaction`)、対人行為 (`player_interactions`) の 3 つを指す。ツール名は全部 `interact`
- **効果 (effect)** が 2 体系ある: `InteractionEffect` (world_graph) と `ItemEffect` (`ItemSpec.consume_effect`、`ConsumableUsedEvent` のハンドラが当てる)
- **state** が 3 つ: 物体 state (`SpotObject.state`)、道具 state (`ItemAggregate.state`)、プレイヤーの自由 state (`PlayerStatusAggregate.state`)。JSON では `new_state` が `state_updates` の別名 (`parse_interaction_effects.py:305-306`)。通路は `passage.state` (`new_state`)
- **trigger**: CALL_MEETING の `trigger` (`emergency_button`)、scenario_event の `trigger` (`ON_TICK`)、会議の `GamePhaseChangedEvent.trigger`
- **倒れている**: `is_down` / `incapacitated` / `target_incapacitated` / `has_reportable_body` / `TARGET_PLAYER_IS_INCAPACITATED` / 「行動不能」「倒れている」。結果の段階は `PlayerOutcome` (`is_eliminated`)。
- **結果文**: `messages` / `result_message` / `result_text` / `message`
- **待ち時間**: 「待ち時間」「再使用間隔」「間を置く」「cooldown」
- **区画**: 「スポット」「部屋」「場所」「区画」(在室数)、`spot` / `interior` / `sub_location`
- イベントの `aggregate_type="SpotGraphAggregate"` を、グラフ集約が起こしていないイベント (drop / pickup / give / interacted) も名乗る

---

## 6. 分からなかったこと、食い違い

### 6-1. 食い違い (コードから読めた事実)

1. **物体の効果対象のすり替え**: `resolve_target_object` は `object_id` が interior に無いとき、操作した物体を返す (`object_target.py:28-33`)。物体経路は行為者の部屋の interior しか渡さないので、別の部屋の物体を `target_object` にした CHANGE_OBJECT_STATE / INCREMENT / CONSUME_STOCK / WRITE_PLAYER_TEXT は、**操作した物体を書き換える**。道具経路だけは明示対象の部屋を探す (`spot_interaction_application_service.py:756-787`)。scenario_event も取っ掛かりの物体の部屋 1 つしか渡さない (`spot_graph_scenario_event_stage_service.py:304-342`)。読み込みに「同じ部屋」を確かめるコードは見つからなかった
2. **入口ごとに無視される spec** (§2-1)。対人行為の `target=ACTOR` の状態異常・欲求・転移、scenario_event のダメージ・状態異常・欲求・会議は、宣言は通るが何も起きない。警告が出るのは scenario_event の TELEPORT と同期行動だけ
3. **未知の状態異常・欲求の種類名**: 物体経路は警告でスキップ、道具経路は `ValueError` で全体 rollback。読み込みは確かめていない (`parse_interaction_effects.py` に検証が無い)
4. **`PlayerStatusAggregate.current_spot_id` が更新されない**: 代入は `__init__` だけ (`player_status_aggregate.py:107`)。発言イベントの `spot_id` はこれを使う (`player_speech_service.py:123`)。配信先はグラフの presence で決めるので、【推測】配信には効かないが、`PlayerSpokeEvent.spot_id` と `PlayerAudienceQueryService` (`application/observation/services/player_audience_query_service.py:50, 73`) は出発地点の値を見ている可能性がある
5. **転移と移動予定のずれ**: `teleport_entity` は presence だけ動かし、`PlayerSpotNavigationState` を触らない。docstring 自身が「移動中の entity を飛ばすと次の tick で例外」と書いている (`spot_graph_aggregate.py:353-361`)。次の travel 開始時に黙って帳尻を合わせる (`movement…:212-219`)
6. **CHANGE_PASSAGE_STATE は指定した向きだけ変える**: reactive passage binding は読み込みで逆向きにも自動で当てる (`parse_reactive_bindings.py:66-81`) が、効果は `connection_id` 1 本だけ (`cross_domain.py:232-256`, `spot_graph_aggregate.py:611-635`)。【推測】双方向の扉を効果で開けると片側だけ開く
7. **確定境界の外にある状態変更**: 攻撃 (`SpotAttackOrchestrator` は monster → player → graph を個別に保存、`spot_attack_orchestrator.py:314-320`)、発言 (即 publish)、interact / attack 後の疲労 (`spot_graph_tool_executor.py:955, 2781`)、CALL_MEETING 経路 (`spot_interaction_application_service.py:1044-1063`)
8. **会議開始の異常解決が 2 か所**: `MeetingCommandService._resolve_ongoing_conditions` と `WorldRuntime._resolve_ongoing_conditions_on_meeting_start` (`world_runtime.py:2562-2601`)。どちらが本番で走るか、両方走るかは確かめていない
9. **ドメイン層の組み込み例外**: `ValueError` を `world_graph_effect_service.py:166`, `spot_interaction_service.py:212, 234`, `spot_graph_aggregate.py:222, 262`, `entity/spot_interior.py:47` で投げている (CLAUDE.md の規約と食い違い)
10. **gold 不足の失敗観測**: `_require_payable_gold` の `InteractionNotAllowedException` は前提条件の try の外で上がるので、`deferred_failure_reasons` に積まれず、同席者への失敗観測が出ない (`spot_interaction_application_service.py:1099-1108, 1304`)。【推測】意図かどうかは不明
11. `can_interact` は 64 か所から呼ばれる互換の入口として残っている (`spot_interaction_service.py:111-120`)。対人行為はこれを使い、`PredicateResult` (失敗した条件) を捨てている (`player_interaction_application_service.py:924-946`)

### 6-2. 分からなかったこと

- 同期行動の解決 (`SynchronizedActionResolverStageService`) が CommandScope の中で走るか (呼び出し元を追っていない)
- `apply_damage` を既に倒れたプレイヤーへ当てたとき `PlayerDownedEvent` が二重に出るか。`Hp.damage` の 0 での振る舞いを見ていない (`player_status_aggregate.py:438-449` は `is_alive()` だけ見る)
- 同期の sync dispatcher に登録されたハンドラ (commit 前に走るもの) の全体。`PlayerDownedOutcomeHandler` と `ConsumableUsedEvent` のハンドラは commit 前と読める (`world_runtime.py:5998, 6123`) が、一覧は作っていない
- `hidden_interaction_filter` (役割で隠す条件) と候補表示の詳細。範囲外として読んでいない
- `_prepare_action` / 同期行動の準備 (prepared flag) の確定の仕方の細部
