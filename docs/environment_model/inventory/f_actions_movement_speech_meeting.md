# 行為の洗い出し (担当 B): travel_to / attack / speak / listen / wait / report_body / vote / say_inline

- 読んだ版: origin/main `f231eb62a` (detached)。コードは書き換えていない。実 API・run・テストは使っていない
- 土台: `docs/environment_model/inventory/c_interactions_effects.md` (以下「C 調査」)、`b_world_tick.md` (以下「B 調査」)
- パスの略記 (`src/ai_rpg_world/` 以下):
  - `CAT` = `application/llm/services/tool_catalog/spot_graph.py`
  - `EXE` = `application/llm/services/executors/spot_graph_tool_executor.py`
  - `RES` = `application/llm/services/_argument_resolvers/spot_graph_resolver.py`
  - `DSP` = `application/llm/services/world_llm_turn/tool_dispatch.py`
  - `PB` = `application/llm/services/world_llm_turn/phase_b.py`
  - `TT` = `application/llm/services/world_llm_turn/turn_trigger.py`
  - `SH` = `application/llm/services/world_llm_turn/speech_handler.py`
  - `SID` = `application/llm/services/world_llm_turn/say_inline_delivery.py`
  - `EXP` = `application/llm/tool_exposure.py`
  - `WR` = `application/world_runtime/world_runtime.py`
  - `MOV` = `application/world_graph/spot_graph_movement_application_service.py`
  - `TRS` = `application/world_graph/spot_graph_travel_stage_service.py`
  - `SGA` = `domain/world_graph/aggregate/spot_graph_aggregate.py`
  - `NAV` = `domain/world_graph/service/spot_graph_navigation_service.py`
  - `ATK` = `application/world_graph/spot_attack_orchestrator.py`
  - `PAS` = `domain/monster/service/spot_player_attack_service.py`
  - `MCS` = `application/world_graph/meeting_command_service.py`
  - `GPS` = `application/world_graph/game_phase_store.py`
  - `PSS` = `application/speech/services/player_speech_service.py`
  - `PSA` = `domain/player/aggregate/player_status_aggregate.py`
  - `SRS` = `application/observation/services/recipient_strategies/spot_graph_speech_recipient_strategy.py`
  - `GRS` = `application/observation/services/recipient_strategies/spot_graph_recipient_strategy.py`
  - `PF` = `application/observation/services/formatters/player_formatter.py`
  - `UI` = `application/llm/services/spot_graph_ui_context_builder.py`
- 【事実】はコードで読んだこと。【推測】は読んだ範囲からの見立てで、実行や試験では確かめていない。印の無い記述は【事実】

---

## 0. 全行為に共通する入口 (先に読む)

担当の行為は、どれも同じ経路を通る。行為ごとの節では、ここと違う点だけを書く。

1. **誰に手番が来るか** (`TT:378-399`, `application/player/services/player_life_query.py:72-99`)
   - 結果が確定した人 (EJECTED / RESCUED / STRANDED、去った主体が無効な世界の DEAD) には来ない
   - 倒れている人 (`can_act()` が偽) には来ない
   - 去った主体 (DEAD かつシナリオが去った主体を有効にした世界) には来る
   - **移動中の人には来ない**。到着の観察者が起こす (`TRS:180-204`)
2. **どのツールを出すか** (`EXP`、`WR:1570-1636`)
   - シナリオの `disabled_tools` で消える (`EXP:207-221`)
   - `vote` / `report_body` は会議機構を宣言した世界にだけ在る (`EXP:81`, `:214`)
   - フェーズ共通: `speak` / `listen` / `wait` (`EXP:98`)。会議中に残るのはこれと `tend_to_player`・SNS だけ
   - 会議中だけ: `vote` (`EXP:156`)。投票済みの人には出さない (`EXP:257-258`, `WR:1638-1658`)
   - 自由時間だけ: `travel_to` / `attack` / `report_body` ほか (`EXP:292-311`)
   - 去った主体に出すのは `speak` / `travel_to` / `interact` / `listen` / `wait` だけ (`EXP:106`, `:250-252`)
   - 1 人ずつの行の出し分け (同じ場所にモンスターがいるか等) は無い。`attack` は自由時間なら常に出る
3. **出していないツールは実行しない** (`DSP:1148-1216`)。プロンプトを組んだ時点で出していたが今は出せないなら `TOOL_BECAME_UNAVAILABLE`、そもそも出していないなら `TOOL_NOT_OFFERED_NOW`。どちらも say_inline は出さない
4. **名前の解決** (LLM 層。`RES`)。ラベルは、そのターンのプロンプトに並べた候補 (`ToolRuntimeContextDto.targets`、`UI`) からだけ引く。どこにも無い名前は、型付き判断の口が配線されていれば意味で選び直す (`RES:630-685`)
5. **移動の中断** (`PB:237`, `DSP:991-1032`): `speak` / `listen` / `wait` / `explore` 以外は、移動中なら先に移動を取り消す。行為が失敗したら戻す (`PB:268-293`)。【推測】移動中の人には手番が来ないので (上の 1)、通常の経路ではこの中断は起きない
6. **行動の記録** (`PB:353-381`): 成功した `travel_to` / `interact` / `explore` は do_* 側で記録済みなので Phase B では記録しない。それ以外は結果 DTO から 1 件記録する
7. **失敗の観測**: 失敗 DTO は本人だけに `「{tool} を試みたが失敗した: …」` の観測になる (`PB:418-419`, `application/intent/action_failed_observation_emitter.py:89-145`、`observation_category="self_only"`)。周りには届かない
8. **次の手番** (`TT:297-323`): 成功し `was_no_op` でなければ次の tick に手番を回す。回さないのは `wait` (`rests_until_woken`)、倒れた・去れなくなった人、移動中の人
9. **say_inline** は、schema に `say_inline` を持つツールのハンドラを包んで、ハンドラが返った後に出す (`DSP:423-457`, `SID:26-44`)。詳しくは §8

---

## 1. travel_to — 隣の場所へ移動を始める

| 項目 | 内容 |
|---|---|
| 主体 | 生きている人 (自由時間)。去った主体も可 (`EXP:106`)。会議中は出ない (フェーズ固有)。倒れている人・移動中の人には手番が来ない |
| 対象 | 場所。`destination_label` に行き先の場所の **名前** (表示名、同名は `#N`) を書く。道 (接続) の名前を書いても、隠し候補として行き先に飛ばす (`UI:730-746`)。現在地の名前は隠し候補として受け付ける (`UI:684-707`)。resolver が内部の `destination_spot_id` (int) に置き換える (`RES:1509-1539`) |
| 引数 | `destination_label` (必須)。`say_inline` あり、`inner_thought` あり (`CAT:59-87`) |

**前提条件**

シナリオが宣言する条件 (道ごと):
- 通路の状態が通れること (`passage.traversable`)。閉じた扉・壁は「接続が閉鎖されています」(`NAV:76-77`)
- `passage_conditions` (宣言順の AND): `ALWAYS` / `ITEM_REQUIRED` (品目を持っている) / `FLAG_SET`・`PUZZLE_SOLVED` (世界フラグが立っている)。失敗文はシナリオの `failure_message`、無ければコードの既定文 (`NAV:84-113`)。未知の種類は不成立

コードの決まり:

| 規則 | 層 | 根拠 |
|---|---|---|
| ツールが今出ていること | LLM 層 | `DSP:1185-1194` |
| 疲労 100 なら断る (`EXHAUSTED`) | LLM 層 (ツール実行器) | `EXE:661-663`, `EXE:524-544`, `domain/player/value_object/fatigue_exertion.py:42-47` |
| 行き先が、プロンプトに並べた接続先の名前であること。隣接しない既知の場所は `DESTINATION_NOT_ADJACENT` | LLM 層 (resolver) | `RES:267-291`, `RES:1509-1539` |
| すでに移動中なら断る (`SpotTravelAlreadyInProgressException`) | application | `MOV:233-234` |
| 通れる接続だけで経路があること (BFS)。無ければ `SpotTravelUnreachableException` | domain (経路) + application | `NAV:42-67`, `SGA:140-147`, `MOV:240-248` |
| 経路の各区間に「通れる」最初の接続があり、その通行条件を今満たすこと | application が domain の `can_pass` を呼ぶ | `MOV:252-268`, `SGA:149-155` |
| 移動予定の現在地をグラフの居場所に合わせる (黙って補う) | application | `MOV:225-231` |

**世界の変化**

- 始めたとき (ツールの手番、確定境界の中): `PlayerStatusAggregate` の `spot_navigation_state` を `begin_travel(route, leg_connection_ids, leg_travel_ticks)` にして保存 (`MOV:270-275`)。**居場所はまだ動かない**。疲労 +1 (確定境界の外、別保存。`EXE:697`, `EXE:546-570`)
  - 行き先が現在地なら、何も変えずに保存だけする (`MOV:236-238`)。疲労は +1 される (`EXE:697` は do_move の結果を見ない)
- 進むとき (毎 tick の `travel` 段、人ごとに確定境界): `nav.advance_one_world_tick()` で渡り切った区間ごとに、通行条件を **もう一度** 見る。通れれば `SpotGraphAggregate.move_entity` で居場所 (presence) を移し `EntityLeftSpotEvent` → `EntityEnteredSpotEvent` を積む。移った先に環境音があれば `SpotSoundHeardEvent` も (`MOV:284-358`, `SGA:401-449`)。`move_entity` 自身も通行条件を見る (`SGA:417-419`)
  - 途中で通れなくなったら、出発側で `at_rest` にして止める (`MOV:313-330`)
  - 去った主体は `DepartedPositionStore.move` だけで、グラフのイベントを積まない (`MOV:331-337`)
  - 倒れた・退場した人の移動予定は、進める前に取り消す (`TRS:119-131`)
- 終わるとき: 到着で `is_traveling` が偽になり、到着の観察者が呼ばれる (`TRS:180-204`) → 行動履歴に「「X」に着いた / ここから次の行動を選べる。」を積み (`WR:5270-5308`)、手番を積む

**本人に返るもの**

- 成功: `「{行き先}へ移動しました。」` (コードが作る文。`EXE:713`)。行動履歴には別の文が残る: 出発なら `「A」から「B」へ向かって出発した` / `「B」へ移動中。到着までは他の行動はできない。`、現在地を指定したら `「B」へ移動しようとした` / `「B」には既に居る` (`WR:2963-2999`)
- 失敗: ドメイン例外を `exception_result` で変換した文 (`EXE:727-728`)。通行条件の失敗はシナリオの `failure_message` が文になる。名前の解決の失敗は、接続先の一覧を添えた専用の文 (`DSP:638-684`)
- 途中で止められたとき: 本人だけに `travel_blocked` の観測 (`schedules_turn=True`) と行動履歴 (`WR:896-960`)。文は `travel_blocked_cue` が作る (コード)

**周りに見えるもの**

- 区間を渡ったとき: 出た場所の他の人に「X が〈道〉を通って B の方へ…」、入った場所の他の人に「X が「A」から〈道〉を通ってやってきた。」(`application/observation/services/formatters/_spot_graph_movement_handler.py:44-170`、配信先は出来事の場所の本人以外 `GRS:168-174`)。`schedules_turn` は立てない
- 出発の時点・失敗したときは、周りには何も届かない
- 去った主体の移動は、誰にも観測されない (グラフのイベントを積まないため)

**時間**: 始めるのは 1 手。移動そのものは接続の `travel_ticks` の合計だけ tick を使い、その間は手番が来ない。到着の tick に手番が戻る

**【推測】**
- 行き先は隣の場所に限られる (resolver) が、直結の道が閉じていると BFS は通れる道だけで迂回路を探す (`SGA:140-147`) ので、隣の場所へ複数区間で回り込むことがある
- `find_first_passable_connection_between` は「状態が通れる」最初の接続を選び、通行条件はその後で見る (`MOV:252-262`)。同じ 2 地点に条件の違う道が複数あると、条件を満たす別の道があっても断られうる
- 去った主体の「既に居る」判定は、グラフの居場所 (身体の位置) と比べている (`WR:2960-2965`)。幽霊が今いる場所を指定したときに「出発した」と記録しうる

---

## 2. attack — 同じ場所のモンスターを 1 回殴る

| 項目 | 内容 |
|---|---|
| 主体 | 生きている人、自由時間だけ (フェーズ固有。`EXP:292-311`)。去った主体には出ない (`EXP:106`)。倒れている人には手番が来ない。domain でも `attacker.is_down` を見る |
| 対象 | モンスター。`target_label` に名前 (同種は `#N`)。候補はプロンプトの「同じ場所に居るモンスター」(死骸も並ぶ。`UI:994-1040`)。resolver が `monster_id` と表示名に置き換える (`RES:1475-1507`) |
| 引数 | `target_label` (必須)。`say_inline` あり、`inner_thought` あり (`CAT:463-494`) |

**前提条件** (シナリオが宣言する条件は無い。すべてコード)

| 規則 | 層 | 根拠 |
|---|---|---|
| ツールが今出ていること | LLM 層 | `DSP:1185-1194` |
| 名前がプロンプトのモンスター候補にあること (人・物の名前なら `INVALID_TARGET_KIND`) | LLM 層 | `RES:1475-1507` |
| 疲労 100 なら断る | LLM 層 | `EXE:2719-2721` |
| 攻撃の部品が配線されていること (`UNSUPPORTED_TOOL`) | LLM 層 | `EXE:2722-2735` |
| モンスター・攻撃者が保存先にいること | LLM 層 | `EXE:2747-2761` |
| 攻撃者が倒れていない (`attacker_down`) | domain | `PAS:58-59` |
| モンスターが ALIVE (`target_dead`) | domain | `PAS:61-62` |
| ダメージが 0 より大きい (`zero_damage`) | domain | `PAS:64-68` |

- **同じ場所にいるかは、実行時には確かめていない。** プロンプトの候補が同じ場所のモンスターだけ、という LLM 層の前提に頼る (`PAS:7-9` の docstring、`ATK:270-321` に場所の比較が無い)
- 暗さ・視認も実行時には見ない (`PAS:7-9`)
- docstring は「cooldown」を失敗に挙げるが、`try_attack` に待ち時間の判定は無い (`EXE:2713-2716` と `PAS:38-82`)

**世界の変化** (確定境界なし。c 調査 §6-1 の 7)
- `MonsterAggregate.apply_damage(base_stats.attack)`。HP 0 で死ぬ (`MonsterDiedEvent` は集約が積む) (`PAS:70-74`)
- `MonsterAggregate.record_attacked_by_in_spot` で「誰に殴られたか」を残す (後の tick で追う・逃げるの判断に使う) (`ATK:298-301`)
- `SpotGraphAggregate` に `PlayerAttackedMonsterInSpotEvent` を積む (`ATK:302-312`)
- monster → player → graph の順に個別に保存 (`ATK:313-320`)
- 疲労 +5 (成功したときだけ、別保存。`EXE:2779-2780`)
- ダメージは `PlayerStatusAggregate.base_stats.attack` そのまま。状態異常による補正 (`compute_effective_stats`) も装備も見ない (`PAS:64`, `PSA:149-156`)

**本人に返るもの** (すべてコードが作る文)
- 成功: `「{名前}に {n} のダメージを与えた。」`、倒したら `「 致命傷で倒した。」` を足す (`EXE:2775-2782`)
- 失敗 (domain): `「{名前}を攻撃できなかった ({reason})。」`、`ATTACK_FAILED`。**reason は内部の英字コード** (`attacker_down` 等) がそのまま入る (`EXE:2770-2774`)
- 相手の HP の数値は返さない。プロンプトの健康 3 段階で見る (`CAT:466-470`)

**周りに見えるもの**
- 同じ場所の他の人へ `PlayerAttackedMonsterInSpotEvent` (`GRS:256-262`, `GRS:481`)
- `MonsterDamagedEvent` / `MonsterDiedEvent` は「その場所と攻撃者」へ届ける規則がある (`application/observation/services/recipient_strategies/monster_recipient_strategy.py:177-179`)
- 【推測】このツールの経路は `_process_graph_events` を呼ばない。グラフに積んだイベントは、次の tick の確定後フック `graph_event_flusher` (`WR:5598-5600`、B 調査 H1) か、同じ tick の別の行為が呼ぶ `_process_graph_events` で流れる。モンスター集約に積んだイベントは、確定境界の外の保存では UoW に集められない (`infrastructure/repository/in_memory_repository_base.py:107-112`) ので、いつ・どこで流れるかは **確かめていない**
- 失敗したときは、周りには何も届かない

**時間**: 1 手で 1 発。反撃はこのツールではなく、tick の `monster_behavior` 段で起きる (B 調査の段 11)

---

## 3. speak — 声に出して話す (囁き / 発言 / 叫び)

| 項目 | 内容 |
|---|---|
| 主体 | 生きている人と去った主体。フェーズ共通 (会議中も可)。倒れている人は domain が断る |
| 対象 | `channel` で範囲を選ぶ。`whisper` だけは人 1 人 (`target_label` に同じ場所の人の名前)。`say` / `shout` は対象なし |
| 引数 | `channel` (`whisper` / `say` / `shout`、必須)、`content` (必須)、`target_label` (whisper のとき必須、ほかは無視)。**`say_inline` は持たない**。`inner_thought` あり (`CAT:212-252`) |

**実行経路**: 世界の手番では `SH.handle_speech` → `WR.do_speech` → `PSS.speak` (`application/llm/services/world_llm_turn/wiring.py:232`, `SH:41-137`, `WR:1128-1156`)。resolver を通さず、ハンドラが自分でラベルを解決する。

**前提条件** (シナリオが宣言する条件は無い)

| 規則 | 層 | 根拠 |
|---|---|---|
| `channel` が 3 つのどれか (`INVALID_SPEECH_CHANNEL`) | LLM 層 | `SH:54-62` |
| `content` が空でない (`INVALID_SPEECH_CONTENT`) | LLM 層 + domain | `SH:63-69`, `PSA:783-784` |
| whisper: 宛先の名前がプロンプトの同じ場所の人にあること (`INVALID_WHISPER`、候補一覧つき) | LLM 層 | `SH:79-95`, `SH:140-168` |
| whisper: 宛先が退場していないこと。ただし話し手も宛先も去った主体なら通す (`INVALID_WHISPER`) | LLM 層 | `SH:96-118` |
| whisper: 宛先があること | application + domain | `PSS:96-99`, `PSA:785-786` |
| 話し手の PlayerStatus と `current_spot_id` があること | application | `PSS:88-93` |
| 話し手が倒れていない (`SPEAKER_DOWN`)。同じ tick に先行者に倒された場合もここで断る | domain | `PSA:781-782`, `SH:122-131` |
| 去った主体は倒れていても話せる。空でないことと、去った位置があることだけ見る | application | `PSS:101-118` |

**世界の変化**
- 状態は変えない。`PlayerSpokeEvent` を `PlayerStatusAggregate` に積み、すぐに publish する (確定境界なし) (`PSS:120-139`, `PSA:762-796`)
- 去った主体の発言は、application が `PlayerSpokeEvent` を作って集約に積む。場所は去った位置 (`PSS:104-118`)
- 会議中なら、沈黙上限の起点を今にする (`GamePhaseStore.note_activity`) (`WR:1156-1161`, `GPS:256-263`)

**本人に返るもの** (コードが作る文)
- 成功: `「（N 名に届いた）」` などの届いた範囲の要約。会ったことのない聞き手は数えない (`SH:171-198`, `application/speech/services/audience_feedback.py:94-123`)。0 人のときは channel ごとの次の手の提案つき
- 失敗: 上の表の各文

**周りに見えるもの** (`SRS:75-134`, `PF:335-482`)
- whisper: 宛先が同じ場所にいるときだけ宛先 1 人に `「X が囁いた: 「…」」`
- say: 同じ場所 + 1 hop、shout: 2 hop まで。音の伝わり方 (`SoundPropagationService`) で明瞭さが決まり、ぼんやりは内容の断片、かすかは内容なし。方向 (〈道〉の向こうから) を添える
- 話し手本人には三人称の観測を出さない (`PF:345-347`)
- 聞いた人の手番を積む (`schedules_turn=True`)
- 会ったことのない話し手は名前を伏せる (`subject_name` / `if_subject_unknown`)
- 去った主体の発言は、生きている人には届かない (`application/player/services/player_perception_policy.py:42-48`, `:73-82`)。去った主体は生きている人の声を聞ける
- 倒れている人には届かない (配信先の出口で落とす。`application/observation/services/observation_recipient_resolver.py:106-146`)
- 失敗したときは、周りには何も届かない

**時間**: 1 手。移動を中断しない (`DSP:126-133`)。成功すれば次の tick に手番が来る

**【事実】使われていない別実装**: `SpeechToolExecutor` (`application/llm/services/executors/speech_executor.py`) と `SpeechArgumentResolver` / `DefaultToolArgumentResolver` は、`src` と `scripts` の中で組み立てている箇所が見つからなかった (export だけ)。疲労で発話を伏字にする処理 (`speech_executor.py:46-77`, `:204-215`) はこちらにしか無い。【推測】世界の手番では、疲労による発話の朦朧化は効いていない

---

## 4. listen — 耳を澄まして周りの音と気配を聞く

| 項目 | 内容 |
|---|---|
| 主体 | 生きている人と去った主体。フェーズ共通 |
| 対象 | なし (今いる場所と隣の場所) |
| 引数 | なし。`say_inline` は持たない。`inner_thought` あり (`CAT:290-312`) |

**前提条件**: シナリオの条件は無い。コードは「runtime が配線されていること」だけ (`EXE:2826-2832`)。グラフに居場所が無ければ `EntityNotInGraphException` が `exception_result` になる (`SGA:465-490`, `EXE:2833-2836`)

**世界の変化**: 状態は変えない。`SpotGraphAggregate.emit_listen_carefully` がグラフにイベントを積み、`_process_graph_events` ですぐ流す (`WR:2862-2886`)
- 今の場所の環境音 → `SpotSoundHeardEvent` (減衰なし)
- 隣の場所ごと (最も音を通す接続の hop 数で減衰) → `SpotSoundHeardEvent` (SILENT なら出さない)
- 隣の場所ごとの「動ける人」の気配 → `SpotPresenceListenedEvent`。hop 1 なら人数、hop 2 なら「いる/いない」、hop 3 以上は不明。モンスターは数えない (`SGA:465-540`)
- 動ける人 = 倒れていない人 (`WR:2876-2880`)

**本人に返るもの**
- ツールの結果: `「耳を澄まし、周囲の音や人の気配を確かめた。」` (コードの固定文。`EXE:2837-2845`)
- 中身は観測として本人だけに届く (`GRS:306-312`, `:483-484`)。音の強さの文言はコード (`application/observation/services/formatters/_spot_graph_sound_handler.py`)、場所の音の強さはシナリオの `atmosphere.sound_intensity`
- 他の人の発言は聞こえない (発言は話した瞬間に配る。`CAT:296-303`)

**周りに見えるもの**: なし

**時間**: 1 手。移動を中断しない。成功すれば次の tick に手番が来る

**【推測】** `do_listen` はグラフの居場所 (`graph.get_entity_spot`) を使い、`DepartedPositionStore` を見ない (`WR:2874-2884`)。去った主体のグラフ上の居場所は身体の位置のまま (死亡時に `DepartedPositionStore.place` するだけで、グラフから外していない。`application/player/services/player_death_grace_tick_stage.py:177-184`) なので、幽霊が listen すると身体のある場所の音を聞く

---

## 5. wait — その場で様子を見る

| 項目 | 内容 |
|---|---|
| 主体 | 生きている人と去った主体。フェーズ共通。疲労 100 でも使える (回復の主な手段) |
| 対象 | なし |
| 引数 | `reason` (任意)。`say_inline` あり、`inner_thought` あり (`CAT:180-197`) |

**前提条件**: シナリオの条件は無い。コードは「runtime が配線されていること」だけ (`EXE:2861-2867`)

**世界の変化**
- 世界の状態は変えない。tick も進めない (`WR:3004-3030`)
- 疲労を 20 回復 (確定境界の外、別保存) (`EXE:2873`, `fatigue_exertion.py:24`)。去った主体も回復の対象から外していない (`EXE:590-607`)

**本人に返るもの**: `「しばらく行動を控えて、様子を見た（理由: …）」` (コードの固定文 + 本人の `reason`) (`EXE:2874-2885`)

**周りに見えるもの**: なし (say_inline を添えれば §8 のとおり届く)

**時間**: 1 手。**次の手番を自分では積まない** (`rests_until_woken=True`、`TT:307-308`)。起こすのは `schedules_turn` の観測か、待ち時間のタイマー (最後の活動から既定 6 tick。B 調査 H2)。移動を中断しない

---

## 6. report_body — 倒れている相手を見つけたと知らせ、会議を始める

| 項目 | 内容 |
|---|---|
| 主体 | 生きている人、自由時間だけ。会議機構を宣言した世界だけ。去った主体には出ない |
| 対象 | 人 1 人。`target_player_label` に同じ場所の人の名前 (倒れている人・死んでいる人もプロンプトの同席者に並ぶ。`UI:920-993`)。空は断る (`RES:1385-1411`) |
| 引数 | `target_player_label` (必須)。**`say_inline` は持たない**。`inner_thought` あり (`CAT:555-578`) |

**前提条件** (シナリオが宣言するのは「会議機構があるか」だけ。他はコード)

| 規則 | エラー | 層 | 根拠 |
|---|---|---|---|
| 名前が空でなく、同席者の候補にあること | `INVALID_TARGET_LABEL` / `INVALID_TARGET_KIND` | LLM 層 | `RES:1385-1411` |
| 会議機構が有効 | `MEETING_NOT_AVAILABLE` | application | `MCS:375-380` |
| 会議中でない | `MEETING_ALREADY_STARTED` | application | `MCS:385-390` |
| 同じ相手をまだ報告していない | `BODY_ALREADY_REPORTED` | application | `MCS:391-396`, `GPS:177-183` |
| 報告者がグラフに居る | `TARGET_NOT_FOUND` | application | `MCS:461-472` |
| 相手の身体の位置 (倒れていれば身体の記録、そうでなければグラフ) が報告者と同じ場所 | `TARGET_NOT_HERE` | application | `MCS:473-506` |
| 相手が倒れている (`is_down`) | `TARGET_NOT_INCAPACITATED` | application | `MCS:507-515`, `application/player/services/player_life_query.py:135-141` |
| 倒れているのに身体の記録が無いのは不変条件違反 (`RuntimeError` → `SYSTEM_ERROR`) | — | application | `MCS:477-479`, `EXE:2952-2957` |

- 緊急招集と違い、待ち時間 (会議直後の 20 tick)・回数・異常中の禁止は見ない (`GPS:44`, `MCS:316-339` と比較)

**世界の変化** (1 つの確定境界の中。`MCS:381-409`)
- `GamePhaseStore` に報告済みとして記録 (`MCS:516`)
- 集合: 報告者以外で投票できる人 (退場しておらず倒れていない人) を、報告者の場所へ `SpotGraphAggregate.teleport_entity` で移し、移動予定を `at_rest` にする。去った主体と倒れている人は動かさない (`MCS:599-638`)
- `GamePhaseStore.begin_meeting` (票を空にし、会議フェーズへ) (`MCS:526-555`, `GPS:223-242`)
- 会議開始で解決すると宣言された異常 (`ongoing_conditions[].on_meeting_start`) を効果で解く (世界フラグ) (`MCS:557-586`)
- `GamePhaseChangedEvent` を集める

**本人に返るもの**: 成功 `「倒れている者を見つけたと知らせた。」`、失敗は上の表の文 (どれもコードの文)

**周りに見えるもの**
- 全員へ `GamePhaseChangedEvent`: 「X が倒れている者を見つけた…全員が集まる」系の文 (trigger ごとの文はコード) + 手番を積み、移動を止める (`GRS:284-294`, `:463`, `application/observation/services/formatters/_spot_graph_object_handler.py:248-290`)
- 異常の解決の通知 (commit 後) (`MCS:421-433`)
- 【推測】集合の teleport がグラフに積む `EntityLeftSpotEvent` / `EntityEnteredSpotEvent` は、確定境界の UoW か次の `graph_event_flusher` で流れ、集合先の人に「X がやってきた」と届く。どちらで流れるかは確かめていない
- 失敗したときは周りには届かない

**時間**: 1 手。会議は以後、全員の投票・沈黙上限 (既定 6 tick)・時間上限で終わる (`GPS:184-199`)

**【推測】** 会議が終わると身体の記録を全部消す (`MCS:264`)。会議の後もまだ倒れている (死んでいない) 人を報告すると、`has_reportable_body` は真なのに記録が無く、`RuntimeError` → `SYSTEM_ERROR` になりうる。会議の時間上限は死亡の猶予より短く決めてある (`GPS:51-60` 付近) ので、会議中に倒れた人や会議をまたいで倒れている人で起きうるかは確かめていない

---

## 7. vote — 会議で 1 票を投じる (棄権も 1 票)

| 項目 | 内容 |
|---|---|
| 主体 | 会議中の、まだ投票していない人。会議機構を宣言した世界だけ。去った主体には出ない |
| 対象 | 人 1 人か、なし (棄権)。`target_player_label` に同じ場所の人の名前。空文字・省略は棄権 (`RES:1360-1383`) |
| 引数 | `target_player_label` (任意)。**`say_inline` は持たない**。`inner_thought` あり (`CAT:528-552`) |

**前提条件** (シナリオの宣言は会議機構の有無だけ)

| 規則 | エラー | 層 | 根拠 |
|---|---|---|---|
| 投票済みの人にはツールを出さない | `TOOL_BECAME_UNAVAILABLE` / `TOOL_NOT_OFFERED_NOW` | LLM 層 | `EXP:257-258`, `DSP:1185-1194` |
| 名前が同席者の候補にあること (空は棄権として通す) | `INVALID_TARGET_LABEL` / `INVALID_TARGET_KIND` | LLM 層 | `RES:1360-1383` |
| 会議機構が有効 | `MEETING_NOT_AVAILABLE` | application | `MCS:126-131` |
| 会議中 | `NOT_IN_MEETING` | application | `MCS:135-140` |
| まだ投票していない | `ALREADY_VOTED` | application | `MCS:141-146` |

- **投票者が投票できる人か (退場・倒れ) と、投票先が誰か (自分・退場者・倒れている人) は、実行時に確かめていない** (`MCS:121-171`, `GPS:156-158`)。候補を同席者に絞るのは LLM 層だけで、同席者の行には倒れている人・死んでいる人も並ぶ (`UI:920-993`)

**世界の変化** (1 つの確定境界の中)
- `GamePhaseStore._ballots[投票者] = 投票先 or None` (`GPS:156-158`)
- `MeetingVoteCastEvent` (残りの人数つき) を集める (`MCS:150-160`)
- 投票できる人 (`can_vote`: 退場しておらず倒れていない) が全員投じたら、その場で集計して閉じる (`MCS:161-166`, `:204-253`):
  - 集計は domain の純関数 `resolve_vote`: 最多が 1 人で、かつ棄権数より多いときだけ追放 (`domain/world_graph/service/vote_tally.py:55-83`)
  - 追放: `PlayerOutcomeRegistry` を EJECTED にし、グラフから外す (`unplace_entity`)
  - `MeetingVoteResolvedEvent` (誰が誰に入れたかまで)
  - `GamePhaseStore.end_meeting` で自由時間へ、身体の記録を全部消す、`GamePhaseChangedEvent`

**本人に返るもの**: 成功 `「投票した。」` (固定文)、失敗は上の表の文

**周りに見えるもの**
- 投票者以外の全員へ `「X が投票を済ませた。まだ N 人が投票していない。」` (投票先は伏せる)。手番を積む (`GRS:296-304`, `_spot_graph_object_handler.py:168-188`)。倒れている人は出口で落ちる。【推測】去った主体はこの出来事に行為者を持たないので知覚の規則を通り、受け取る
- 最後の票のとき、全員へ集計結果 (票数・棄権・追放・誰が誰に) と会議終了 (`_spot_graph_object_handler.py:190-246`)

**時間**: 1 手。会議は全員の投票か、沈黙上限 / 時間上限 (tick 段で判定) で終わる

---

## 8. say_inline — 行動しながらの一言

| 項目 | 内容 |
|---|---|
| 主体 | 親の行動ツールを出された人。生きている人と去った主体 (去った主体は `travel_to` / `interact` / `wait` に添えられる) |
| 対象 | なし。範囲は `say` 固定 (同じ場所 + 1 hop) (`application/llm/services/tool_catalog/say_inline.py:1-28`) |
| 引数 | 親ツールの `say_inline` (文字列、`maxLength: 200`)。担当分では `travel_to` / `attack` / `wait` が持ち、`speak` / `listen` / `vote` / `report_body` は持たない |

**いつ出すか** (`SID:26-84`, `DSP:423-457`, `DSP:1185-1216`)
- 親のハンドラが返った **後** に 1 回だけ出す。親が成功しても失敗しても出す (名前の解決・疲労・前提条件で断られても届く。D1601)
- 親のハンドラが例外を投げても出し、結果を例外に載せて Phase B に渡す
- 親が「今は出していないツール」「存在しないツール」で断られたときは出さない。そのときは `「（添えた発言は届かなかった）」` を結果文に足す
- 未指定・空白だけなら何もしない

**前提条件** (すべてコード)
- 文字列で、空白を除いて空でない (`EXE:740-745`)
- 200 字を超えたら切り詰める (schema の `maxLength` に加えて実行側でも) (`EXE:752-761`)
- 発言の部品が配線されていること
- 発言できること: `PSS.speak` の規則 (倒れていない、去った主体なら去った位置がある) (`PSS:86-139`)。断られたら親の結果は変えず、`「（添えた発言は届かなかった）」` を足す (`EXE:771-779`, `SID:47-62`)

**世界の変化**: `speak` の `say` と同じ (`PlayerSpokeEvent` を即 publish)。ただし `WR.do_speech` を通らず `PlayerSpeechApplicationService.speak` を直接呼ぶ (`EXE:762-770`)

**本人に返るもの**: 届いたときは何も足さない (trace に `say_inline_spoken=True`)。届かなかったときだけ `「（添えた発言は届かなかった）」`

**周りに見えるもの**: `speak` の `say` と同じ。聞いた人の手番を積む。【推測】親の行動のイベントより後に publish されるので、聞き手には「行動 → 一言」の順に届く。`travel_to` に添えた一言は、まだ出発地にいる (居場所は次の tick から動く) ので出発地の周りに届く

**時間**: 親の行動の 1 手に含まれる (追加の手番を使わない)

---

## 9. 担当の行為をまたいで見えたこと

### 同じことを違う形でやっている
- **発言の入口が 3 つ**: `speak` は `SH.handle_speech` → `WR.do_speech` → `PSS.speak`。`say_inline` は `EXE.speak_say_inline` → `PSS.speak` を直接。さらに使われていない `SpeechToolExecutor`。結果として:
  - 【事実】会議の沈黙上限の起点を進めるのは `WR.do_speech` だけ (`WR:1156-1161`)。**会議中に `wait` に say_inline を添えて話しても、会議の「活動」として数えない** (`wait` は会議中も出て say_inline を持つ)
  - 【事実】whisper の「宛先が退場していないか」は `SH` にしか無い
  - 【事実】疲労による発話の伏字化は使われていない `SpeechToolExecutor` にしか無い
- **身体の位置と主体の位置が 3 つ以上**: グラフの presence、`PlayerSpotNavigationState.current_spot_id`、`DepartedPositionStore`、`FallenBodyRegistry`。行為ごとにどれを見るかが違う: 移動は去った位置 (`MOV:124-137`)、発言の配信も去った位置 (`SRS:58-66`)、`listen` と `report_body` と移動の「既に居る」判定はグラフ (`WR:2874`, `MCS:461`, `WR:2960`)
- **行動履歴の書き手が 2 つ**: `travel_to` は `WR.do_move` が書き、Phase B は書かない (`PB:353-357`)。他は Phase B が結果 DTO から書く。そのため `travel_to` だけ、本人に返す結果文 (`「Xへ移動しました。」`) と履歴の文 (`「Xへ移動中。…」`) が違う

### 行為によって扱いが食い違う
- **確定境界**: `travel_to` (開始・進行)・`report_body`・`vote` は CommandScope の中。`attack`・`speak`・`say_inline` は外 (C 調査 §6-1 の 7 と同じ)。疲労の増減は全行為で外
- **実行時の再確認**: `vote` / `report_body` は会議中かを実行側でも確かめる (設計 doc H-6 の方針。`EXE:2906-2957`) が、`attack` は同じ場所にいるかを、`vote` は投票者・投票先の資格を、実行側で確かめていない。ツールの出し分けとプロンプトの候補に頼っている
- **去った主体と疲労**: 疲労を足す側は去った主体を除く (`EXE:555-560`) が、疲労 100 で断る側 (`EXE:524-544`) と回復する側 (`EXE:590-607`) は除かない。【推測】身体の疲労が 100 のまま死ぬと、幽霊は `travel_to` / `interact` を断られ続ける
- **失敗文の言葉**: `attack` は domain の内部コード (`attacker_down` 等) を本人向けの文にそのまま入れる (`EXE:2770-2774`)。他の行為は日本語の文を作っている
- **ツールの説明と実装のずれ**:
  - `attack` の説明は「装備している武器があればそれで威力が変わる」(`CAT:466`) が、ダメージは `base_stats.attack` そのまま (`PAS:64`)
  - `attack` の docstring は待ち時間 (cooldown) を失敗に挙げるが、判定は無い
  - `travel_to` の疲労のコメントは「1 leg = 1 fatigue」(`EXE:696`) だが、区間の数によらず 1 回のツール呼び出しにつき +1。行き先が現在地でも +1
- **say_inline を持つかどうか**: `speak` 以外の発話の無いツール (`listen` / `vote` / `report_body`) は持たない。`report_body` は会議を始める行為なのに一言を添えられない。`vote` / `report_body` の resolver は `{**args}` で全引数を通すが、包みが無いので添えても出ない

### シナリオの効果の仕組みを使わずに世界を変えている
- 担当の 7 行為のうち、`InteractionEffect` (`WorldGraphEffectService.apply_effects`) を使うのは `report_body` の「会議開始で異常を解く」部分だけ (`MCS:557-586`)。それ以外の世界の変化 (移動予定と居場所、モンスターの HP、会議フェーズ・票・追放・集合の teleport、疲労) は、各 application サービスが集約を直接呼んで変えている
- 移動の通行条件 (`PassageCondition`) は、物体の前提条件 (`InteractionCondition`) とは別の体系で、評価器も別 (`NAV:84-113`)。どちらも `ScenarioPredicateEvaluator` は使う
- 会議の状態 (フェーズ・票・報告済み・緊急ボタン) は application の `GamePhaseStore` が持つ。集計の規則だけが domain の純関数 (`resolve_vote`)
- 会議を始める・終える・追放する手順が `MeetingCommandService` と `WorldRuntime` (`begin_meeting`、`eject_player`、`_resolve_ongoing_conditions_on_meeting_start`) の 2 か所にある (`WR:2468-2567`)。C 調査 §6-1 の 8 と同じ。どちらが本番で走るかは確かめていない

### 分からなかったこと
- `attack` で積まれた `MonsterDamagedEvent` / `MonsterDiedEvent` / `PlayerAttackedMonsterInSpotEvent` が、いつどの経路で観測になるか
- `report_body` の集合の teleport が積むグラフのイベントが、確定境界の commit で流れるか、次の tick のフックで流れるか
- 会議を宣言した世界で、`GamePhaseStore` の票と報告済みの記録が snapshot に載るか (読んでいない)
