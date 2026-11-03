# 知覚の決まりの洗い出し: 誰に、何が、どう見えるか (聞こえるか)

- 読んだ版: origin/main `5b1fd8573` (detached)。コードは書き換えていない。実 API・run・テストは使っていない
- 土台: `docs/environment_model/inventory/b_world_tick.md` (以下 B 調査)、`c_interactions_effects.md` (C 調査)、`e_actions_objects_items_people.md` (E 調査)、`f_actions_movement_speech_meeting.md` (F 調査)、`g_actions_trade_market.md` (G 調査)、`docs/environment_model/design/` (設計)。各調査の「周りに見えるもの」は繰り返さず、行為をまたぐ決まりに絞った
- パスは `src/ai_rpg_world/` からの相対。略記:
  - `WR` = `application/world_runtime/world_runtime.py`
  - `PEP` = `application/world_runtime/pipeline_event_publisher.py`
  - `ORR` = `application/observation/services/observation_recipient_resolver.py`
  - `GRS` = `application/observation/services/recipient_strategies/spot_graph_recipient_strategy.py`
  - `SRS` = `application/observation/services/recipient_strategies/spot_graph_speech_recipient_strategy.py`
  - `OF` = `application/observation/services/observation_formatter.py`
  - `PF` = `application/observation/services/formatters/player_formatter.py`
  - `OH` = `application/observation/services/formatters/_spot_graph_object_handler.py`
  - `MH` = `application/observation/services/formatters/_spot_graph_movement_handler.py`
  - `APP` = `application/observation/services/observation_appender.py`
  - `PA` = `application/being/player_acquaintances.py`
  - `PPP` = `application/player/services/player_perception_policy.py`
  - `SB` = `application/world_graph/spot_graph_current_state_builder.py`
  - `LR` = `application/world_graph/spot_effective_lighting_resolver.py`
  - `SPS` = `domain/world_graph/service/spot_perception_service.py`
  - `SPR` = `domain/world_graph/service/sound_propagation_service.py`
  - `SIAS` = `application/world_graph/spot_interaction_application_service.py`
  - `PIAS` = `application/world_graph/player_interaction_application_service.py`
- 【確認】はコードで読んだ事実。【推測】は読んだ範囲からの見立てで、実行や試験では確かめていない。印の無い記述は【確認】

---

## 0. 要点

- 【確認】知覚の決まりは 1 か所に無い。観測の経路だけで 4 段 (受け手の戦略 → 受け手の出口 → 文を作る formatter → 記録の版を選ぶ appender) に分かれ、さらに「観測を通らない直接の配送」(`WR._emit_observation_directly`) と「毎ターンの場面」(`SB.build_snapshot`) が別に同じ種類の判断を書いている
- 【確認】受け手の出口 (`ORR._without_the_fallen`) にある「倒れている人には届けない」「生者は去った主体を知覚しない」は、パイプライン経由の観測だけに効く。直接の配送 (天候、腐敗、結果の知らせ、シナリオの出来事、遠景の手がかり、会議での異常の解決、死体・モンスターの初見) は出口を通らない
- 【確認】暗さは「受け手を決める」には一度も使われず、「文を変える」「場面から消す」にだけ使われる。しかも使う場所は 4 か所 (倒れた人の加害者名、対人行為の宣言文、転移の宣言文、場面の物体・モンスター・地面) に限られ、移動・発言・物体の操作・モンスターの攻撃 (第三者向け) は暗さを見ない
- 【確認】音の伝わり方の計算が 3 種類ある (発言、接続の状態変化、耳を澄ます/環境音)。発言の届く範囲は別々の 3 か所 (受け手の戦略、formatter、本人への「N 名に届いた」) で計算し直している
- 【確認】名前の伏せ方は 2 層。「会ったことがあるか」(`subject_name` / `if_subject_unknown`) は 5 種類の観測 (発言、倒れた、復帰した、死体の初見、結果の知らせ) にしか付かない。「名前を知っているか」(見た目への置き換え) は全観測に appender で後からかかるが、structured に名前が値として出ているものだけが対象

---

## 1. 観測が生まれてから Being の短期記憶に入るまで

### 1-1. 経路 (パイプライン経由)

| 段 | 何をするか | どこで |
|---|---|---|
| 1. ドメインイベントを集める | 集約がイベントを積む。グラフ集約の分は `WR._process_graph_events` が取り出して publisher へ (確定後フック H1 や行為の直後) | `WR:1783-1809` |
| 2. publisher | 受け手のハンドラ (`register_handler` で登録、確定後・BEST_EFFORT) を先に同期実行 → `ObservationPipeline.run` → `appender.append` → `scheduler.maybe_schedule`。SNS のいいね・フォローだけ別経路 | `PEP:156-188`, `PEP:63-76` |
| 3. 受け手を決める | `ObservationRecipientResolver.resolve`: 登録順の戦略で `supports` が真の先頭に任せ、重複を除き、出口で倒れている人と知覚できない人を落とす | `ORR:98-146`。戦略の並び `ORR:206-268` |
| 4. 受け手ごとの文 | `ObservationPipeline.run` が受け手ごとに `attention_level` を引いて `ObservationFormatter.format` を呼ぶ。下位 formatter を順に試し、最初の非 None を採る。None なら届けない | `application/observation/services/observation_pipeline.py:33-54`, `OF:140-169` |
| 5. 注意の水準で落とす | `FILTER_SOCIAL` は social を、`IGNORE` は self_only 以外を落とす | `OF:154-169` |
| 6. 記録の版を選ぶ | `ObservationAppender.append` → `recipient_view` (`PlayerAcquaintances.view_for`) が「名前を見せる版 / 伏せる版 / 届けない」を選び、続けて名前を知らない参加者を見た目に置き換える。届けないときは trace だけ残して False | `APP:82-137`, `APP:139-161`, `PA:148-171`, `PA:298-322` |
| 7. 預かる | `DefaultObservationContextBuffer.append` → `UnifiedRecentEventStore.append_pending_observation` (まだ Being には写さない) | `application/observation/services/observation_context_buffer.py:21-34`, `application/llm/services/unified_recent_event_store.py:85-88` |
| 8. trace と observer | trace `OBSERVATION` (伏せた名前も残す)。observer として遭遇の記録と `PlayerAcquaintances.on_observation` (入ってきた人と互いに会った記録、名乗り・呼びかけで名前を知る) | `APP:121-137`, `APP:172-218`, `WR:5815-5829`, `PA:173-197`, `PA:234-263` |
| 9. 手番を起こす | `ObservationTurnScheduler.maybe_schedule`: `schedules_turn` が真で、LLM が動かすプレイヤーなら `schedule_turn` | `application/observation/services/observation_turn_scheduler.py:26-41` |
| 10. 短期記憶へ写す | 手番の Phase A でプロンプトを組むときに buffer を drain して `append_observation` → listener `PlayerShortTermMemoryCopy.on_appended` → `observation_from_game` で契約の `Observation` に翻訳 → `ShortTermMemory.perceive` | `application/llm/services/prompt_builder.py:263-265`, `unified_recent_event_store.py:54-59`, `WR:6763-6772`, `application/being/player_short_term_memory_copy.py:96-172`, `application/observation/being_contract/observation_translation.py:133-180` |

- 【確認】Being に写るのは「その人の手番が来てプロンプトを組んだとき」だけ。手番が来ない人 (倒れている、確定した) の観測は buffer に残り続ける
- 【確認】翻訳は本文が空 (`EMPTY_BODY`) か時刻の札が無い (`MISSING_TIME_LABEL`) と写さず、trace `BEING_SHORT_TERM_MEMORY_NOT_COPIED` を残す (`observation_translation.py:144-147`, `player_short_term_memory_copy.py:106-116`)
- 【確認】翻訳は `structured.type` と `observation_category` から経路 (見聞き / 自分の体 / 環境の知らせ) を決め、主体の名前は本文に出ているものだけ写す (`observation_translation.py:286-310`)

### 1-2. パイプラインを通らない配送

| 経路 | 受け手を決める場所 | 通らないもの | 根拠 |
|---|---|---|---|
| `WR._emit_observation_directly` (appender → scheduler) | 呼び出し側がそれぞれ決める | 受け手の出口 (倒れている人・去った主体の除外)、注意の水準 | `WR:1811-1833` |
| 待ち時間のタイマー | 全 LLM プレイヤー (移動中を除く) | 同上 | `application/observation/services/heartbeat_observation_emitter.py:97-165` |
| 行動の失敗 | 本人 | 同上 (本人だけなので影響なし) | `application/intent/action_failed_observation_emitter.py:95-110` |
| 復帰の申し送り (`PlayerRevivedPostHocObservationHandler`) | 本人 | 同上。**scheduler を呼ばず、時刻の札も渡さない** | `application/player/handlers/player_revived_post_hoc_observation_handler.py:103-107` |
| 観戦者からの声 | 指定のプレイヤー | 同上。手番は直接積む | `presentation/spot_graph_game/runtime_manager.py:774-786` |

- 【推測】復帰の申し送りは `game_time_label` を渡さないので、翻訳で `MISSING_TIME_LABEL` になり Being の短期記憶に写らない (`observation_translation.py:146-147`)。プロンプトの「直近の出来事」は Being の作業記憶から組む (`prompt_builder.py:263-289`) ので、「倒れている間にされたこと」は本人に届いていない可能性が高い。試験・trace では確かめていない

### 1-3. 手番を起こすか (`schedules_turn`) を決める場所

【確認】起こすかは **観測を作った場所がそれぞれ決める**。決まりの表は無い。

| 決める場所 | 値 | 根拠 |
|---|---|---|
| 各 formatter | 種類ごとにべた書き。例: 発言・倒れた・復帰・対人行為・物体の操作・拾う・置く・会議・接続の変化・状態の公開 = 真。入退場・昼夜・失敗の目撃・持ち物を捨てた/装備 = 偽。環境音は LOUD のときだけ真、気配は偽 | `PF:156-161`, `PF:469`, `MH:84-88`, `MH:128-132`, `OH:186`, `OH:285-289`, `OH:310-314`, `OH:662-665`, `OH:901-904`, `application/observation/services/formatters/_spot_graph_sound_handler.py` の `schedules_turn=(event.intensity == ...LOUD...)` |
| シナリオの作者 | シナリオの出来事 (`scenario_event.observation.schedules_turn` / `breaks_movement`)、遠景の手がかり (`appear_event.schedules_turn`) | `WR:3029-3047`, `WR:3137` |
| world_runtime の直書き | 天候 = 真、腐敗 = 偽、結果の知らせ = 真、会議の異常解決 = 真、死体の初見 = 真、モンスターの初見 = 真、移動の取りやめ = 真 | `WR:3515-3530`, `WR:3500-3511`, `WR:5862-5878`, `WR:2602-2614`, `WR:5053-5065`, `WR:4985-4996`, `WR:906-920` |
| 待ち時間のタイマー | 真 | `heartbeat_observation_emitter.py:140-149` |

- 【確認】`breaks_movement` も観測に付くが、これを読む `MovementInterruptionService` / `ObservationEventHandler` は `src` と `scripts` のどこからも組み立てられていない (`grep` で定義以外 0 件)。【推測】観測の `breaks_movement=True` (倒れた本人、会議の開始、死体の初見、シナリオの出来事) は移動を止めていない。会議の開始は集合の teleport と `at_rest` で別に止めている (`application/world_graph/meeting_command_service.py:599-638`)
- 【確認】`AttentionLevel` を変える `set_attention_level` は `src` と `scripts` から呼ばれていない (snapshot の復元だけ)。【推測】注意の水準による絞り込み (`OF:154-169`) は常に FULL で、観測の `observation_category` は今は配送を変えていない (Being への翻訳の経路決めにだけ効く)

---

## 2. 受け手と見え方を決めている要素

### 2-1. 場所の範囲 (同じ場所 / 隣 / 全員)

| 要素 | どこで | どう決めているか | 効く出来事 | 根拠 |
|---|---|---|---|---|
| 同じ場所の他人 (行為者を除く) | GRS | グラフの居場所 + `DepartedPositionStore` の去った主体を合わせた人のうち、`entity_id` 以外 | 入退場、物体の操作の失敗、give、商人との売買、準備、探索、状態の公開 | `GRS:168-174`, `GRS:333-352`, 表 `GRS:420-445` |
| 同じ場所の全員 | GRS | 除外なし | 取引の持ちかけ・成立、取り落とし、モンスターの出現・攻撃・逃走・追跡ほか | `GRS:246-254`, `GRS:432-436`, `GRS:467-479` |
| 行為者が分かれば除く | GRS | `actor_entity_id` が None (tick 由来) なら全員 | 物体の状態変化、公開効果 | `GRS:264-273` |
| 接続の両端 + 音の漏れる隣 | GRS | 両端の全員。加えて両端から出る接続のうち `sound_permeability >= 0.1` の先の人 | 接続の状態変化 | `GRS:354-407` |
| 接続の両端 | GRS | 両端の全員 | 接続の生成・破棄 | `GRS:275-282` |
| 世界の全員 | GRS | `player_status_repository.find_all()` | 会議の開始・終了、投票の集計、昼夜 | `GRS:284-294`, `GRS:462-464` |
| 投票者以外の全員 | GRS | 同上から投票者を除く | 投票の進み | `GRS:296-304` |
| 本人だけ | GRS / Default | `entity_id` か `aggregate_id` | 耳を澄ます結果、環境音、板の品の置き場、所持金・持ち物・レベル | `GRS:306-322`, `GRS:440`, `application/observation/services/recipient_strategies/default_recipient_strategy.py:105-112` |
| 当事者だけ (場所を問わない) | GRS | 期限切れは持ち主、それ以外は `notify_entity_id` | 市場の板 | `GRS:180-209` |
| 本人 + 全プレイヤー | Default | 「既知の全プレイヤー」は全員 (`all_known_players`)。近いか遠いかは formatter が分ける | 倒れた、復帰した | `default_recipient_strategy.py:114-140` |
| 同じ場所の他人 (別実装) | ItemUse | グラフの居場所だけで自前に計算 (去った主体の位置を見ない) | 品を使った | `application/observation/services/recipient_strategies/item_use_recipient_strategy.py:44-63` |
| モンスターの場所 + 攻撃者/倒した人 | Monster | 場所の全員に加え、離れていても攻撃者・倒した人 | モンスターの被弾・死 | `application/observation/services/recipient_strategies/monster_recipient_strategy.py:150-187` |
| 直接の配送: 全員 | WR | `get_player_ids()` | 天候、腐敗、結果の知らせ、会議での異常解決 | `WR:3511`, `WR:3529-3530`, `WR:5891-5892`, `WR:2601-2614` |
| 直接の配送: シナリオの宣言 | WR | `recipients == "players_at_spot"` ならグラフの presence、それ以外は全員 | シナリオの出来事 | `WR:3077-3083` |

- 【確認】腐敗の知らせは、腐った品がどこにあっても (誰かの持ち物でも、遠くの地面でも) 全員に「今日は◯◯が N 個腐った。」と届く (`WR:3465-3513`)

### 2-2. 声の大きさと通路の音の通しやすさ

| 要素 | どこで | どう決めているか | 効く出来事 | 根拠 |
|---|---|---|---|---|
| 声の大きさ → 届く hop 数 | domain | ささやき 0、ふつう 1、叫び 2 | 発言、行動に添えた一言 (ふつう固定) | `domain/world_graph/enum/sound_volume.py:11-16`, `application/world_graph/speech_channel_mapping.py:7-12` |
| 発言の明瞭さ | SPR | hop 0 は CLEAR。hop 1 は経路の透過率の積が 0.35 以上で MUFFLED、未満は FAINT。hop 2 以上は FAINT。積が 0.02 未満で打ち切り。複数経路は最も明瞭なもの | 発言 | `SPR:13-14`, `SPR:33-42`, `SPR:44-113` |
| 通路の透過率の既定 | domain | 開口 1.0、無傷の壁 0.1、ひびの壁 0.4、鍵の扉 0.5、閉じた扉 0.6、開いた扉 1.0、結界 1.0。シナリオが上書きできる | すべての音 | `domain/world_graph/value_object/passage.py:44-54` |
| ささやき | SRS / PF | 宛先が同じ場所にいるときだけ宛先 1 人。受け手の戦略と formatter の両方で確かめる | 発言 | `SRS:93-100`, `PF:404-413` |
| 明瞭さで文を変える | PF | CLEAR は全文、MUFFLED は「〈道〉の向こうから、X の遠くの声が聞こえる」+ 先頭 20 字、FAINT は内容なし。structured の `content` も同じだけ削る | 発言 | `PF:37`, `PF:60-73`, `PF:434-461` |
| 接続の状態変化の音 | GRS / OH | 透過率 0.1 以上の接続 1 本ぶんの隣に「遠くで〈道〉が動く音がした。」。声の大きさの概念は無い | 接続の状態変化 | `GRS:383-407`, `OH:924-933` |
| 耳を澄ます・環境音 | domain | 透過率を hop 数 1〜4 に量子化 (0.7 / 0.4 / 0.1 で区切る) し、場所の音の強さ (`atmosphere.sound_intensity`) を減衰させる。気配は hop 1 で人数、hop 2 で有無、hop 3 以上は不明 | listen、移動先の環境音 | `domain/world_graph/value_object/passage.py:77-97`, `domain/world_graph/aggregate/spot_graph_aggregate.py:448-540` |
| 本人への「N 名に届いた」 | 別の resolver | `SpeechAudienceResolver` が届く範囲を 3 度目に計算。話し手が会っていない聞き手は数えない | 発言 | `application/speech/services/speech_audience_resolver.py:117-215`, `application/llm/services/world_llm_turn/speech_handler.py:171-198` |

### 2-3. 暗さ

| 要素 | どこで | どう決めているか | 効く出来事 / 表示 | 根拠 |
|---|---|---|---|---|
| 実効照明の計算 | SPS | 場所の基本照明 → 屋外で夜か悪天候 (STORM / FOG) なら 1 段暗く (重ねても 1 段) → 同じ場所に光源を持つ人が 1 人でもいれば DARK / PITCH_BLACK を DIM へ | 下の全部 | `SPS:21-73`, `LR:37-38`, `LR:61-114` |
| 材料を集める | LR | 光源 = 光源の品を持っている entity。グラフの presence から数える | 同上 | `LR:74-91`, `WR:5198-5205` |
| 見える明るさの集合 | 5 か所に同じ集合 `{BRIGHT, DIM}` を書いている | 「三つは別の問い」と各所のコメントが互いを参照 | 物体が見える / 宣言文の明所版 / 第三者が加害者を見分ける / 痕跡を読む / モンスターが標的を見る | `SPS:75-77`, `application/world_graph/declared_observation_message.py:9-19`, `PF:236-245`, `domain/world_graph/entity/spot_object.py:211-223`, `domain/monster/service/monster_visibility_service.py:43` |
| 場面から消す | SB | 見えなければ物体 (`is_visible_in_dark` を除く)・地面の品・モンスターを出さない。暗くて見えない物体の名前は別に持つ。**同じ場所の人と倒れた人は暗くても出す** | 毎ターンの場面 | `SB:1111-1112`, `SB:1147-1152`, `SB:1227`, `SB:1280-1298`, `SB:1300-1404` |
| 照明の説明文 | SPS | 「手元の光源で…」「{名前}の持つ光源で…」「完全な暗闇だ。何も見えない。」(コードの文) | 場面の雰囲気 | `SPS:79-100`, `SB:1259-1272` |
| 倒れた人の加害者名 | PF | 受け手と加害者が同じ場所で、見える明るさのときだけ名前を出す | 倒れた (第三者向け) | `PF:185-202` |
| 宣言文の明暗の切り替え | PIAS / SIAS | 作者が `*_in_dark` を書いたときだけ、実効照明で切り替える。照明が分からなければ暗所版 | 対人行為の目撃文、転移の出発・到着の文 | `PIAS:1079-1087`, `SIAS:303-318`, `SIAS:855-875`, `SIAS:1375-1400` |
| 前提条件 | domain | `SPOT_LIGHTING_IS` / `_IS_NOT` が同じ resolver の値を見る | 物体・対人の操作 | `domain/world_graph/service/spot_interaction_service.py:697-709`, `SIAS:1240-1269` |
| モンスターの攻撃 | `application/world_graph/spot_attack_orchestrator.py` | **場所の基本照明だけ** (光源・夜・天候を見ない)。被害者だけ「暗闇から何かに襲われた。」、第三者は常に名前つき | モンスターの攻撃 | `spot_attack_orchestrator.py:151-167`, `:506-515`, `application/observation/services/formatters/_spot_graph_monster_handler.py:85-109` |
| 遠景 | `application/world_graph/distant_view_service.py` | 屋外にいるときだけ見える (屋内は視程 0)。夜・天候・照明は見ない | 場面の遠景、遠景の手がかりの観測 | `distant_view_service.py:12`, `:354-358`, `:289-322` |
| 時刻帯の表示 | 現在状態の formatter | 「時刻帯: 夜 (暗い)」 | 場面 | `application/llm/services/spot_graph_current_state_formatter.py:73-77` |

- 【確認】暗さを見ないもの: 入退場 (`MH:44-132`)、発言 (`PF:335-482`)、物体の操作の目撃文 (`SIAS:1595-1614` は `witness_observation_message` をそのまま載せ、`witness_observation_message_in_dark` を読まない)、拾う・置く・渡す、品を使った、探索、モンスターの攻撃 (第三者向け)、倒れた人の発見 (`WR:4998-5023` のコメントに「暗さは見ない」)
- 【確認】`witness_observation_message_in_dark` は全 interaction の読み込みで受け付ける (`infrastructure/scenario/parse_interactions.py:126-131, 193`) が、使うのは対人の操作だけ。物体の操作に書いても黙って効かない

### 2-4. 名前を知っているか

| 要素 | どこで | どう決めているか | 効く出来事 | 根拠 |
|---|---|---|---|---|
| 会ったことがあるか (層 1) | formatter が 2 版を作り、appender が選ぶ | 観測が `subject_name` と `if_subject_unknown` (伏せた版 `SubjectUnknownView` か、届けない印 `WithheldFromStrangers`) を持つときだけ。受け手が `subject_name` と会った記録を持つか。引けなければ伏せる側 | 発言 (「誰かが言った」)、倒れた・復帰した (同じ場所は「誰かが」、遠くは届けない)、死体の初見 (「誰かが倒れている」)、結果の知らせ (追放以外は届けない) | `application/observation/contracts/dtos.py:10-76`, `PA:156-171`, `PF:176-184`, `PF:227-234`, `PF:269-290`, `PF:462-481`, `WR:5040-5065`, `WR:5862-5878` |
| 名前を知っているか (層 2) | PA | 見た目 (`appearance`) を宣言した人だけが対象。会っていて `knows_name` なら名前、それ以外は見た目。structured に値として出ている参加者の名前を、本文の「」『』の外だけ置き換える | appender を通る全観測 | `PA:199-215`, `PA:298-322`, `PA:346-416` |
| 最初に知っている相手 | `move_translation` / WR | `knows_at_start` を書かなければ全員を紹介。`mutually_known_roles` の役割どうしは「あなたと同じ側」を添える。初期配置で同じ場所の人とは会った記録を残す | 上の 2 層の初期値 | `application/observation/being_contract/move_translation.py:28-55`, `WR:3919-3931`, `WR:6737-6738` |
| 会った記録が増える | PA | 入ってきた人の観測を受けたとき双方に (伏せた観測では増えない) | 入場 | `PA:173-197` |
| 名前を知る | PA | 名乗り (話し手が分かる声に自分の名前) と呼びかけ (同じ場所の人の名前、ささやき以外)。会っていない相手の名前は聞いても知ったことにしない | 発言 | `PA:217-263` |
| 場面の名前 | SB / UI | 同じ場所の人を `viewer_name_resolver` (呼び名) で出し、初対面なら「(初めて会った)」 | 場面 | `SB:501-507`, `SB:1352-1357`, `application/llm/services/spot_graph_ui_context_builder.py:646-661` |
| 「N 名に届いた」 | speech_handler | 話し手が会っていない聞き手を数えない | 発言の結果文 | `application/llm/services/world_llm_turn/speech_handler.py:193-197` |

- 【確認】formatter は本当の名前で文を作る (`WR:5222-5224` で名前の解決を差し替え)。伏せる・置き換えるは appender で後からかかる
- 【確認】層 1 を持たない観測 (入退場、物体の操作、give、拾う、置く、対人行為、探索、モンスターへの攻撃、会議の招集・投票) は、会っていない相手でも名前か見た目で届く。【推測】同じ場所にいるなら会った記録がほぼ必ずある (初期配置か入場で記録) ので実害は小さいが、転移で現れた人や会議の集合で現れた人の扱いは確かめていない

### 2-5. こっそり行う、効果の見え方

| 要素 | どこで | どう決めているか | 効く出来事 | 根拠 |
|---|---|---|---|---|
| 第三者に届くか (`WitnessPolicy`) | GRS | SAME_SPOT なら同じ場所の他人、ACTOR_ONLY なら誰にも届けない。作者の宣言か、`stealth` 引数 | 物体の操作、拾う、置く、対人行為 | `domain/world_graph/enum/witness_policy.py:35-40`, `GRS:211-220`, `GRS:447-449` |
| 対象本人に届くか (`notify_target`) | GRS / OH | ACTOR_ONLY でも対象本人だけに届ける。対象専用の文 (`target_observation_message`) が無ければ目撃文に「(あなたが対象だった)」 | 対人行為 | `GRS:222-244`, `OH:767-783` |
| 効果が届くか (`EffectVisibility`) | domain の既定表 + 作者の上書き | ACTOR_DIRECT は本人の結果文、PUBLIC_OBSERVABLE は同じ場所の第三者へ、HIDDEN は誰にも (本人の現在状態だけ) | 効果を使う行為と出来事 | `domain/world_graph/enum/effect_visibility.py:22-32`, `domain/world_graph/service/effect_application/visibility.py:24-128`, `SIAS:1615-1625`, `SIAS:1935-1985` |
| 失敗が周りに見えるか | SIAS / OH | 前提条件の不成立で、作者の `on_failure_observation` か理由があるときだけ。秘匿の条件 (`ConditionVisibility`) は出さない。同じ (行為者, 物体, 操作, 理由) は 24 tick 抑える | 物体の操作だけ | `SIAS:235-273`, `SIAS:1276-1303`, `SIAS:2105-2175`, `OH:866-904` |
| 宣言文が行為者を伏せるか | formatter | 宣言文に `{actor}` が無ければ structured からも行為者名を外す | 入退場 (転移の宣言文)、対人行為 | `MH:77-78`, `MH:121-122`, `OH:784-785` |

### 2-6. 本人だけ、伏せた属性 (集まりの見え方)

| 要素 | どこで | どう決めているか | 効く出来事 / 表示 | 根拠 |
|---|---|---|---|---|
| `observation_category="self_only"` | 各 formatter | 本人の状態 (所持金、持ち物、倒れた本人、復帰の本人、失敗)。今は配送を変えない (1-3) | 翻訳の経路決め | `PF:300-333`, `PF:484-571` |
| 属性の見え方 (`AttributeVisibility`) | domain | PUBLIC は全員、SECRET は本人だけ (存在も伏せる)、HIDDEN は本人も知らない | 本人の場面の「自分の状態」、満たせない条件の注記 | `domain/player/value_object/player_attribute_spec.py:40-53`, `:136-162`, `application/llm/services/spot_graph_current_state_formatter.py:131-185`, `application/world_graph/unreachable_attribute_notes.py:80` |
| 本人の状態の公開 | SIAS / OH | `CHANGE_PLAYER_STATE` を作者が PUBLIC_OBSERVABLE にしたときだけ、同じ場所の他人に「{X}の{key}が{before}から{after}に変わった。」 | 状態の公開 | `SIAS:1963-1979`, `OH:1106-1133`, `application/observation/services/formatters/_spot_graph_formatter_helpers.py:120-132` |
| 同じ側の仲間 | move_translation / SB | `mutually_known_roles` の役割どうしだけ「あなたと同じ側」。場面の対人の操作の候補も、表示済みの関係だけで絞る | 紹介、場面 | `move_translation.py:43-55`, `SB:509-547` |

- 【確認】本人の状態の公開は属性の SECRET / HIDDEN を見ない。キーと値は宣言の呼び名ではなく生の `key` と値で文になる (`_spot_graph_formatter_helpers.py:125-131`)
- 設計 (`docs/environment_model/design/world_design.md:76-82`) の `GroupingDeclaration.visibility: EVERYONE / SELF_ONLY / NOBODY` は、今のコードの `AttributeVisibility` の PUBLIC / SECRET / HIDDEN に対応すると読める (【推測】)

### 2-7. 倒れている人、去った人 (幽霊)

| 要素 | どこで | どう決めているか | 効く出来事 | 根拠 |
|---|---|---|---|---|
| 倒れている人は周りを知覚しない | ORR の出口 | `can_receive_world_observation` (倒れていない、または去った主体) でない受け手を落とす。ただし主体が本人 (`aggregate_type == PlayerStatusAggregate` で `aggregate_id` 一致) なら残す | パイプライン経由の全観測 | `ORR:106-161`, `application/player/services/player_life_query.py:101-114` |
| 生者は去った主体を知覚しない | PPP | 受け手が生者で、行為者 (`aggregate_id` か `entity_id` / `actor_entity_id` / `attacker_entity_id` / `original_actor_entity_id`) が去った主体なら落とす。行為者の無い出来事は通す | パイプライン経由の全観測 | `PPP:36-82`, `ORR:139-145` |
| 去った主体の発言 | SRS | 去った主体の声は去った主体にだけ、生者の声は去った主体にも届く。位置は `DepartedPositionStore` | 発言 | `SRS:58-66`, `SRS:102-134` |
| 去った主体の場面 | SB | 位置は去った位置。生者を見られる。生者からは見えない。自分の体は「自分の亡骸」として出る。対人の操作の候補は出さない | 場面 | `SB:997-1019`, `SB:1300-1402` |
| 倒れた本人への文 | PF | 「倒れて動けなくなった。」。去った主体になるなら「死亡した後も移動できる…」。`victim_learns_killer` なら加害者名 | 倒れた | `PF:131-162`, `domain/player/value_object/death_semantics.py:37-51` |
| 周りへの「倒れた」 | PF | 同じ場所なら「{X}が倒れて動かなくなった。」(加害者が見えれば名前)。遠くなら `announce_globally` のときだけ「遠くで誰かが倒れた気配がした。」 | 倒れた | `PF:163-234` |
| 死の知らせ | WR | DEAD は `announce_globally` のときだけ全員へ (直接の配送) | 結果の知らせ | `WR:5879-5892` |
| 死体の初見 | WR / SB | 場面を組むとき、同じ場所の倒れた人・死んだ人を初めて見たら一度だけ観測 (遭遇の記録で一度きり)。加害者は「もう見た」と刻む | 場面 → 観測 | `SB:952-995`, `SB:1404`, `WR:4998-5065`, `WR:5906-5935` |

- 【確認】直接の配送は出口を通らないので、倒れている人にも天候・腐敗・結果の知らせ・シナリオの出来事・会議での異常解決が buffer に積まれる。復帰時に buffer を空にする処理は `src` に見つからなかった (`ORR:110` のコメントは「復帰時に buffer を clear する仕様」と書く)。【推測】起きた後の最初の手番に、倒れていた間の知らせがまとめて届く
- 【確認】去った主体の居場所を見る場所が分かれる。`DepartedPositionStore` を見る: 発言の受け手と文 (`SRS:58-66`, `PF:381-396`)、GRS の同席者 (`GRS:333-345`)、場面 (`SB:1006-1013`)、formatter の位置 (`application/observation/services/formatters/_formatter_context.py:140-159`)。グラフの居場所 (= 体の場所) を見る: 品を使った (`item_use_recipient_strategy.py:47-63`)、遠景の手がかり (`WR:3225-3230`)、シナリオの出来事 `players_at_spot` (`WR:3077-3082`)、実効照明の光源 (`LR:82-84`)、listen (F 調査)

### 2-8. 耳を澄ます、遠景、物音

| 要素 | どこで | どう決めているか | 効く出来事 | 根拠 |
|---|---|---|---|---|
| listen | domain → GRS → sound handler | 今の場所の環境音、隣の場所ごとの減衰した環境音と動ける人の気配 (モンスターは数えない)。本人だけ。気配の観測は `schedules_turn=False` | listen | `domain/world_graph/aggregate/spot_graph_aggregate.py:465-540`, `GRS:483-484`, `_spot_graph_sound_handler.py:32-66` |
| 移動先の環境音 | domain | 移動 (`move_entity`) のたびに移動先の音を本人に。SILENT なら出さない | 入場 | `spot_graph_aggregate.py:448-463` |
| 環境音の文 | sound handler | 強さの語 + 作者の `ambient_description`。隣の音は「隣の spot から…が漏れ聞こえる」(コードの文) | listen、入場 | `_spot_graph_sound_handler.py:67-116` |
| 常時の遠景 | SB / DistantViewService | 屋外にいて、別の area で、隣の area でなく、目立ち度 0.25 以上、目立ち度 × (視程 6 / 距離) が 0.20 以上。最大 2 行 | 場面 | `SB:739-797`, `distant_view_service.py:10-13`, `:289-322` |
| 遠景の手がかり | WR | 作者が宣言した物体の状態が偽→真に変わった tick に、上と同じ見え方の人だけへ作者の文 (`{direction}` などを置換)。初回の評価は基準を記録するだけ | 遠景の手がかり | `WR:3084-3156`, `WR:3197-3245`, `WR:3277-3291` |

### 2-9. 会議中の見え方

| 要素 | どこで | どう決めているか | 根拠 |
|---|---|---|---|
| 場面の節 | prompt_section_layout | 会議中は同席者 (行動なし)・所持金・所持品・身体の状態だけ。接続・物体・モンスター・地面・商人・取引・板は理由つきで落とす | `application/llm/services/prompt_section_layout.py:100-155` |
| 会議中であること | 現在状態 | 観測ではなく毎ターンの現在状態の行に置く | `spot_graph_current_state_formatter.py:79-85` |
| 会議の開始・終了 | GRS / OH | 全員へ。招集した人の名前つき。去った主体で投票できない人には別の締めの文 | `GRS:462-463`, `OH:109-130`, `OH:248-290` |
| 投票 | OH | 進みは投票者以外へ投票先を伏せて、集計は全員へ誰が誰に入れたかまで | `OH:168-246` |
| 集合 | MCS | 投票できる人を報告者の場所へ teleport (去った主体と倒れている人は動かさない)。【推測】集合先で入場の観測が出て、互いに会った記録が残る | F 調査の report_body |

- 【確認】会議中も発言・知覚の決まりは自由時間と同じ (会議専用の受け手の規則は無い)。全員が同じ場所に集まるので、結果として全員に届く

### 2-10. 倒れている間にされたこと

| 要素 | どこで | どう決めているか | 根拠 |
|---|---|---|---|
| 預かる | `TargetedWhileDownRecorder` | 対人行為の対象が行為の始まりに倒れていたら「{行為者}に「{ラベル}」をされた」を 1 行記録。上限 8 件、古い順に捨てる。snapshot に載らない | `application/player/handlers/targeted_while_down_recorder.py:49-77`, `application/player/services/downed_incident_log.py:31-60`, `WR:5967-5998` |
| 起き上がったとき | `PlayerRevivedPostHocObservationHandler` | 「N tick の間、意識を失っていた。{介抱者}に介抱されて…」+ 預かった行為。本人だけ | `player_revived_post_hoc_observation_handler.py:79-140` |
| 起き上がったとき (別経路) | PF | 本人に「復帰しました。」、同じ場所に「{X}が復帰しました。」、遠くに「遠くで誰かが動けるようになった気配がした。」。介抱者は出さない | `PF:247-290` |

- 【確認】預かる側は `witness_policy` / `notify_target` / `target_observation_message` を見ず、行為者の本当の名前 (`spawn.name`) を必ず書く (`targeted_while_down_recorder.py:69-77`, `WR:5962`, `WR:5997`)。起きているときの対人行為は「対象に伏せる」「誰にやられたか伏せる」を宣言で書けるのに、倒れている間に受けた同じ行為は起きたときに名前つきで伝わる。名前は structured に値として出ないので、見た目への置き換えもかからない
- 【推測】1-2 のとおり、この申し送り自体が時刻の札を持たず Being に写らない可能性が高い

### 2-11. 知らせのまとめ方と重複の抑制

| 要素 | どこで | どう決めているか | 根拠 |
|---|---|---|---|
| 腐敗の日まとめ | WR | その日 (昼夜があれば `ticks_per_day`、無ければ既定の分) の腐敗をためて、日が変わった `advance_tick` で 1 件にまとめて全員へ | `WR:3420-3513`, `WR:841-852` |
| 失敗の目撃の抑制 | SIAS | 同じ (行為者, 物体, 操作, 理由) を 24 tick 抑える。tick が分からなければ抑えない | `SIAS:235-273`, `SIAS:2105-2175` |
| 初見を一度きり | WR / 遭遇の記録 | モンスターと倒れた体は Encounter Memory で一度だけ。起動時の読み取り検査中は通知を止める | `WR:4970-4996`, `WR:4998-5065`, `SB:474-491` |
| 受け手の重複 | ORR / 各戦略 | 受け手の id を順序を保って重複除去 | `ORR:167-176`, `GRS:125-133` |
| 発言の重複 | `player_speech_service` | collector が `event_id` で重複を除く | `application/speech/services/player_speech_service.py:128-136` |
| 同じ一撃の文の重複 | PF / PIAS | 対人行為の宣言済みの目撃文が届くとき、倒れた観測の汎用文を空にする (空なので Being には写らない) | `PIAS:1088-1097`, `PF:206-215` |
| 待ち時間のタイマー | heartbeat | 最後の活動から N tick (既定 6) で「周囲に大きな変化はない」 | `heartbeat_observation_emitter.py:97-165` |

---

## 3. 毎ターンの場面 (【現在地と周囲】)

### 3-1. 作っている場所

| 段 | どこで | 何をするか |
|---|---|---|
| 状態を集める | `SB.build_snapshot` | 居場所、接続、物体、地面、雰囲気、モンスター、同席者、所持品、天候、身体、市場など。ここで死体・モンスターの初見の観測も出す | `SB:997-1530` |
| 文にする | `SpotGraphCurrentStateFormatter` | 雰囲気・天候・時刻・会議中・作業の進み・モンスター・自分の状態 | `application/llm/services/spot_graph_current_state_formatter.py:40-130` |
| 節を足す | `SpotGraphUiContextBuilder` | 接続・物体・同席者・モンスター・所持品などの節を、フェーズごとの並び (`sections_for`) で | `spot_graph_ui_context_builder.py:515-560` |
| 場面に包む | `prompt_builder` | 見出し「現在地と周囲」で `Scene` に入れ、作業記憶へ | `application/llm/services/prompt_builder.py:267-289`, `application/llm/services/world_scene.py:7` |

### 3-2. 場面の見え方の決まりは観測と同じか

| 決まり | 場面 | 観測 | 同じか |
|---|---|---|---|
| 実効照明 | `SB` の内部の `SpotEffectiveLightingResolver` (`SB:461-472`) | `WR:5198-5205` で別に作った resolver | 計算は同じクラス、インスタンスと光源の判定関数は別々に組み立てている |
| 暗いと消えるもの | 物体・地面・モンスター | 物体の操作・拾う・置く・モンスターの攻撃 (第三者) は暗くても文が届く | **違う**。場面で見えない物体を誰かが操作すると、目撃文は届く |
| 暗くても見えるもの | 同席者、倒れた人 | 入退場・発言は暗さを見ない | 揃っている (どちらも見ない) |
| 去った主体 | `can_perceive_player` で同席者から外す (`SB:1341-1348`) | 出口で `can_receive_event` | 同じ `PlayerPerceptionPolicy` を使う |
| 名前 | `viewer_name_resolver` (呼び名) | appender で見た目へ置き換え | どちらも `PlayerAcquaintances.call_name` に頼る (【推測】`viewer_name_resolver` の配線は読んでいない) |
| 倒れている人 | 「(倒れて動かない)」「(死亡している)」と持ち物を出す (`spot_graph_ui_context_builder.py:919-955`) | 倒れた・死体の初見の観測 | 場面が状態、観測が気づいた瞬間、と役割を分けている (`SB:952-969`) |
| 遠景 | 屋外だけの常時表示 (`SB:739-797`) | 手がかりの観測は同じ `DistantViewService` で見え方を判定 (`WR:3223-3245`) | 同じサービス。居場所の引き方だけ違う (場面は去った位置、観測はグラフ) |
| 会議中 | 節を落とす | 受け手の規則は変わらない | 場面だけが会議を知っている |
| 本人の伏せた属性 | HIDDEN を「自分の状態」から外す (`spot_graph_current_state_formatter.py:131-185`) | 公開された状態変化は属性の見え方を見ない | **違う** |

---

## 4. 「周りに届く文」の出どころ

### 4-1. 作者が書く文

| 作者の宣言 (シナリオの JSON のキー) | 使われる観測 | 根拠 |
|---|---|---|
| `witness_observation_message` (`{actor}` `{object}` `{target}` `{action}` を展開) | 物体の操作・対人行為の目撃 | `OH:818-864`, `OH:795-816`, `infrastructure/scenario/parse_interactions.py` |
| `witness_observation_message_in_dark` | 対人行為の目撃 (暗所)。物体の操作には効かない | `PIAS:1079-1087` |
| `target_observation_message` | 対人行為の対象本人 | `OH:767-783` |
| `on_failure_observation` | 物体の操作の失敗の目撃 | `OH:879-883` |
| `departure_observation_message` / `arrival_observation_message` (+ `_in_dark`) | 転移の出発・到着 | `SIAS:855-875`, `MH:93-107` |
| `scenario_events[].observation` (文、手番、移動を止めるか、カテゴリ、受け手) | シナリオの出来事 | `WR:3029-3047`, `infrastructure/scenario/parse_scenario_events.py` |
| 反応 (`narrative_on_true` / `narrative_on_false`) | 物体の状態変化 (無ければ出さない) | `OH:964-994`, `infrastructure/scenario/parse_reactive_bindings.py` |
| `on_prepare_observation_message` | 同期操作の準備 | E 調査 |
| `distant_cues[].appear_event.message`、`ambient_descriptions`、area の `distant_descriptions` | 遠景の手がかり、常時の遠景 | `WR:3121-3141`, `SB:761-772` |
| `player_outcome_messages` | 結果の知らせ | `WR:5840-5860` |
| `event_removal_message` (品ごと) | 出来事で持ち物から消えた本人へ | `PF:520-535` |
| `atmosphere` の音・匂い、`passage_conditions[].failure_message` | 場面、移動の取りやめ | `SB:1259-1272`, `SB:1052-1072`, `application/world_graph/travel_blocked_message.py:19-35` |
| `SHOW_MESSAGE` 効果 | 行為者の結果文 (ACTOR_DIRECT) | `domain/world_graph/service/effect_application/visibility.py:96` |
| 世界の時刻帯の `display_text` | 「{夕暮れ}になった。」 | `OH:292-314` |

### 4-2. コードが作る文 (主なもの)

| 文 | 出来事 | 根拠 |
|---|---|---|
| 「{X}が〈道〉を抜けて「B」へ去っていった。」「{X}が「A」から〈道〉を通って{B}にやってきた。」 | 入退場 | `MH:134-170` |
| 「{X}が言った/囁いた/叫んだ: 「…」」「〈道〉の向こうから、{X}の遠くの声が聞こえる: 「…」」「…かすかに聞こえるが、内容ははっきりしない。」 | 発言 | `PF:440-445`, `PF:474-481` |
| 「{X}が「{ラベル}」を行った。」「{X}が{物}を操作した。」 | 物体の操作 (作者の文が無いとき) | `OH:836-840` |
| 「{X}が{物}を地面に置いた。」「拾い上げた。」「{品}を{Y}に渡した。」「{品}を使用した。」 | 置く・拾う・渡す・使う | `OH:640-695`, `OH:316-351`, `application/observation/services/formatters/item_use_formatter.py:22-58` |
| 「{X}が倒れて動かなくなった。」「遠くで誰かが倒れた気配がした。」「復帰しました。」 | 倒れた・復帰 | `PF:124-290` |
| 「{X}が倒れているのを見つけた。動かない。」「{M}が同じ場所にいることに気づいた。」 | 初見 | `WR:4985-4996`, `WR:5025-5030` |
| 「外の天候が変わった: RAIN（強度 0.6）」 | 天候 | `WR:3517` |
| 「今日は{品}が{N}個腐った。」 | 腐敗 | `WR:3488-3491` |
| 「{X}が緊急招集をかけた。全員が集まる。」ほか会議の文の表 | 会議 | `OH:157-166`, `OH:109-124` |
| 「遠くで{道}が動く音がした。」「{道}が通行可能になった。」 | 接続の変化 | `OH:924-943` |
| 「隣の spot から{強さ}が漏れ聞こえる」「{場所}のほうから{N}人ぶんの足音が聞こえる。」 | listen・環境音 | `_spot_graph_sound_handler.py:32-116` |
| 「{X}の{key}が{before}から{after}に変わった。」 | 状態の公開 | `OH:1114-1121`, `_spot_graph_formatter_helpers.py:120-132` |
| 「暗闇から何かに襲われた。」「{M}が{Y}を攻撃した。」 | モンスターの攻撃 | `_spot_graph_monster_handler.py:101-109` |
| 「{X}に「{ラベル}」をされた」 | 倒れている間にされたこと | `targeted_while_down_recorder.py:69-77` |
| 「周囲に大きな変化はない」系 | 待ち時間 | `heartbeat_observation_emitter.py` の `_HEARTBEAT_PROSE` |

---

## 5. 重複・食い違い・べた書き

### 5-1. 同じ判断が複数の場所にある

| 判断 | 場所 | 根拠 |
|---|---|---|
| 発言が誰にどの明瞭さで届くか | 受け手の戦略、formatter、本人への「N 名に届いた」の 3 か所で計算する。倒れている人を落とすのは受け手の出口だけで、「N 名」の計算は落とさない (人数に倒れている人が入る) | `SRS:75-134`, `PF:366-433`, `speech_audience_resolver.py:117-215` |
| ささやきの宛先が同じ場所か | 受け手の戦略と formatter の両方。「宛先が去っていないか」は speech_handler だけ | `SRS:93-100`, `PF:404-413`, F 調査 |
| 同じ場所の他人 | GRS の共通関数と ItemUse の自前の実装 (去った主体の位置を見ない) | `GRS:333-352`, `item_use_recipient_strategy.py:44-63` |
| 見える明るさ `{BRIGHT, DIM}` | 5 か所 (2-3 の表) | 同上 |
| 実効照明 | 共通の resolver があるのに、モンスターの攻撃だけ自前で光源・夜・天候を見ずに計算。docstring は TODO として認めている | `spot_attack_orchestrator.py:506-515` |
| 死をどこまで知らせるか (`announce_globally`) | 倒れた観測 (`PF:172-175`) と死の結果の知らせ (`WR:5879-5890`) の 2 か所。コメント自身が #914 で片方だけ塞いだ経緯を書く | 同上 |
| 行為者本人を除く | 受け手の戦略と formatter の `_is_self` の二重の守り (各所に「二重ガード」のコメント) | `GRS:168-174`, `OH:1111-1113`, `OH:1002-1004` |
| 去った主体の居場所 | `DepartedPositionStore` を見る場所とグラフを見る場所が分かれる (2-7) | 同上 |
| 「会った」の記録 | `PlayerAcquaintances` (名前を伏せる、初対面の注記) と Encounter Memory (モンスター・体の初見) が別の記録 | `PA:73-87`, `WR:4970-5023` |

### 5-2. 種類によって扱いが食い違う

- 暗さ: 対人行為と転移は暗所の文を書けるが、物体の操作は書けない (読み込みは受け付ける)。モンスターの攻撃は被害者だけ暗さで文を変え、第三者には常に名前つき (`_spot_graph_monster_handler.py:91-109` に TODO)。場面では暗くて見えない物体の操作が、観測では届く
- 音: 発言は声の大きさ × 経路の透過率の積、接続の変化は透過率 0.1 以上の 1 hop だけ (声の大きさの概念なし)、listen と環境音は透過率を 1〜4 hop に量子化して強さを減衰。同じ壁を通る音が、出来事の種類で別の物理になっている (`SPR:33-42`, `GRS:383-407`, `passage.py:77-97`)
- 倒れている人: パイプライン経由は届かず、直接の配送は届く (2-7)
- 名前を伏せる: 層 1 (会ったか) を持つのは 5 種類だけ (2-4)。結果の知らせは追放だけ伏せない、と種類ごとに書いている (`WR:5862-5864`)
- 「対象に伏せる」: 起きている対象には `notify_target` / `target_observation_message` で伏せられるが、倒れている対象は起きたときに必ず行為者名を知る (2-10)
- 腐敗の知らせは、品がどこにあっても全員に届く。他の「物の変化」は同じ場所の人にしか届かない
- 本人の状態の公開は、属性の SECRET / HIDDEN を見ない。場面は HIDDEN を本人からも外す
- `schedules_turn`: 入退場は起こさず、置く・拾うは起こす。時刻帯の変化は起こさず、天候は起こす。表ではなく formatter ごとのべた書き (1-3)
- 移動を止める (`breaks_movement`): 値は付けているが、読む側が組み立てられていない (1-3)

### 5-3. コードに直接書かれた値と文

| 値・文 | 場所 |
|---|---|
| 発言の明瞭さの閾値 0.35、打ち切り 0.02 | `SPR:13-14`, `SPR:39` |
| 遠くの声を 20 字で切る | `PF:37` |
| 接続の変化が隣に漏れる閾値 0.1 | `GRS:398` |
| 透過率の量子化 0.7 / 0.4 / 0.1 と、気配の hop 1 / 2 の境 | `passage.py:88-97`, `spot_graph_aggregate.py:520-526` |
| 通路の種類と状態ごとの既定の透過率 | `passage.py:44-54` |
| 視界を落とす天候 STORM / FOG (RAIN は落とさない) | `LR:37-38` |
| 遠景の閾値 0.25 / 0.20、視程 6.0、最大 2 行 | `distant_view_service.py:10-13` |
| 失敗の目撃の抑制 24 tick | `SIAS:239` |
| 倒れている間の記録の上限 8 件 | `downed_incident_log.py:36` |
| 待ち時間 6 tick | B 調査 (`LLM_IDLE_TIMEOUT_TICKS`) |
| 知らない相手の代わりの語「誰か」 | `PF:40`, `WR:5031`, `WR:5047`, `OH:1005` |
| 天候の文に enum の生値 (`RAIN` など) を入れる。場面は `weather_display` で呼び名に変える | `WR:3517`, `spot_graph_current_state_formatter.py:53-63` |
| 環境音の文に「spot」の語 | `_spot_graph_sound_handler.py:92`, `:97` |
| 状態の公開の文に生のキーと値 | `_spot_graph_formatter_helpers.py:125-131` |
| 会議の文の表、会議中の締めの文 | `OH:117-124`, `OH:157-166` |
| 照明の説明文 | `SPS:91-100` |

---

## 6. またいで見えたこと

### 確かめた事実

- 知覚の判断は、受け手の戦略 (場所の範囲、`WitnessPolicy`、`notify_target`)、受け手の出口 (倒れている、去った主体)、formatter (音の明瞭さ、暗さによる身元、位置による文の切り替え、`schedules_turn`)、appender (会ったか、名前を知っているか)、場面の builder (暗さで消す、去った主体、初見の観測) の 5 層に分かれている。「同じ場所か」「見えるか」「聞こえるか」「誰だと分かるか」が層をまたいで別々に決まる
- 受け手の出口と appender は全観測に一律にかかる唯一の場所で、過去の漏れ (run 008 の死者が声を拾った件、`ORR:113-121`) を受けてここへ寄せた経緯がある。ただし直接の配送はこの出口を通らない
- 暗さは配送先ではなく文と場面にだけ効く。場面と観測で暗さの扱いが揃っていない (場面で消える物体の操作が観測で届く)
- 音のモデルが出来事の種類ごとに 3 つある
- 名前を伏せる仕組みは観測ごとに作者 (formatter) が 2 版を用意する方式で、用意していない観測は伏せられない。見た目への置き換えは structured に値として出た名前だけで、文の中に埋め込まれた名前 (倒れている間の記録など) は置き換わらない
- `breaks_movement` と `AttentionLevel` は観測に値を持つが、今の世界の経路では効いていない
- 作者が書ける文は 15 種類ほどあり、明暗の 2 版を書けるのは対人行為と転移だけ

### 推測

- 新しい設計で「知覚の決まり」を 1 つの部品にするなら、少なくとも「出来事の起きた場所と種類 (見える / 聞こえる / 本人だけ / 全員)」「受け手の状態 (倒れている、去った、居場所)」「照明」「音の経路」「受け手が主体を知っているか」の 5 つを入力に持つ必要がある。今のコードでは前の 4 つが出来事ごとに書き分けられ、最後の 1 つだけが appender に寄っている
- 直接の配送 (天候、腐敗、結果、シナリオの出来事、遠景の手がかり) が出口を通らないのは、「宛先が決まっている」からという理由で別経路にした結果で、倒れている人・去った主体の規則を意図して外したわけではないように読める (`WR:1811-1822` の docstring は trace と起床の漏れだけを気にしている)
- 復帰の申し送りは Being に写らず、倒れている間にされたことが本人に届いていない可能性が高い (1-2)
- 腐敗の知らせが全員に届くのは、日まとめにしたときに「誰の品か」を捨てたためで、知覚の決まりとして選んだものではないように読める

### 分からなかったこと

- `viewer_name_resolver` (場面の名前) の配線先が `PlayerAcquaintances.call_name` か
- 転移・会議の集合で現れた人について、会った記録がいつ残るか (グラフのイベントがいつ流れるか、F 調査の未解決と同じ)
- モンスター集約のイベント (`MonsterDamagedEvent` など) がいつ観測になるか (F 調査の未解決と同じ)
- 去った主体が開けた扉などの状態変化が、生者に届くか (`SpotObjectStateChangedEvent.actor_entity_id` が去った主体なら出口で落ちると読めるが、試験で確かめていない)
