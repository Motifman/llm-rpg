# station_drillの燃料凍結試験を整理する

## 目的と基準

燃料凍結の試験を、再利用・時間境界・実操作の保証を残して整理した。重い世界構築の重複と、実際の結果を見ていない検査を減らす。速度だけを理由に反復周期や長い実経過を短絡しない。

基準はupstream main `0b51eb28d4692635a932dcf4063ab9b231768bf0`。読み取り監査では主ファイル全23宣言/25ケース、既存の統合先2ファイル全29宣言/41ケースを確認した。以下の行番号は基準版。R=保持、F=契約を保持して検査を修復、C=先に残す試験へ移して統合、D=独立契約なしで削除。今回Dはない。

変更は試験3ファイルとこの記録だけ。本番コード・scenario・共通支援の恒久変更はない。

## 履歴に基づく保持理由

- [#1101](https://github.com/Motifman/llm-rpg/pull/1101): 全員が無視しても進む締切、全員向け警報/復旧、別人の二役、3/4手番の境界、通常点検に加算しないこと
- [#1111](https://github.com/Motifman/llm-rpg/pull/1111): 25 tick後の再利用、発火1/3/5/7・締切9、二周期とも各一回、二度目放置の敗北。初段40分を聞いてから8 tick応答できる設計
- [#1352](https://github.com/Motifman/llm-rpg/pull/1352): 弁のinteractが準備を登録せず敗北した実障害。準備の本番入口をinteractへ統合し、同期対象interactionのeffectsを禁止した
- [#1031](https://github.com/Motifman/llm-rpg/pull/1031)、[#1129](https://github.com/Motifman/llm-rpg/pull/1129): 遠隔端末と明示対象、二人への配布、world共有待ち時間と保存
- [#1117](https://github.com/Motifman/llm-rpg/pull/1117)、[#1130](https://github.com/Motifman/llm-rpg/pull/1130): 当番表から得る事前知識、事実と戦術の区別、役職間の知識分離

## 主ファイルの全23宣言

対象: `tests/demos/test_station_drill_fuel_freeze_emergency.py`。台帳は最終実施結果。起床は宣言検査に限定し、復旧後と両役失敗後のtick数は維持した。

| # | 行・宣言 | 判定 | 実際に検出する契約・退行／残す先・修復 |
|---|---|---|---|
| 1 | 136 `test_remote_freeze_sounds_the_alarm_for_every_player` | R | 観測室からの遠隔発動でfuel_frozenと全員への最初の文を保証。局所対象限定・配達先漏れを検出。二周期試験は明示的な遠隔場所を固定していないため独立。1 tick必要 |
| 2 | 148 `test_all_three_countdown_alarms_reach_every_player` | C | 30/20/10の存在と順序を、#6の各周期の相対tick 1/3/5/7・全員配送の列比較へ移してから統合。7 tickと世界構築1件を削減した |
| 3 | 161 `test_each_alarm_stage_has_a_one_tick_reusable_window` | C | 4宣言、once=false、上限−下限=1という実装形式を固定。契約は二周期の各段一回性で#6が実行保証。#6へ各周期の期待順序と余分な警報が無いことを明示して残した。#4が時間と文の整合を保持。窓を別表現へ変えても同じ通知なら許せる |
| 4 | 186 `test_alarm_minutes_match_the_declared_deadline_for_every_stage` | R | 独立した40/30/20/10分と9 tick締切・圧計の整合。実装ヘルパで期待値を作っておらず、文面数値を独立に抽出。#1111の9→8退行の根拠。runtime不要、現在も未使用 |
| 5 | 221 `test_freeze_is_blocked_until_its_longest_sabotage_cooldown_expires` | F | 復旧後の再発動拒否と25で許可は価値あり。現状tick1の拒否では24で早期許可を検出しない。23回進めてtick24で拒否、1回進めてtick25で成功を確認する形へ変更済み。残す実操作・時間量は25 tickのまま |
| 6 | 239 `test_second_freeze_repeats_all_alarms_and_global_restoration_once` | R | 二度目の時刻再記録、restored/announced解除、once設定、4段×2回、全員告知×2回。再利用を偽の時刻注入で代用しない。#2/#3の吸収先。34 tickの実経過を維持 |
| 7 | 258 `test_ignoring_the_second_freeze_still_causes_the_declared_loss` | R | 初回復旧の残留が二度目の締切を抑止しない。二周期目でもfuel_lost/LOSE。初回放置(#15)では検出しない。34 tick維持 |
| 8 | 276 `test_resolved_or_lost_fuel_suppresses_future_countdown_alarms` | R（両行） | `fuel_restored` と `fuel_lost` の二行は独立の否定条件。凍結後に直接フラグを立てるのは条件ごとの対照として妥当。実復旧だけではlost側を試せず、lost到達後では全警報が終わっており陰性が空虚になる。7 tickで全後続段を通す必要あり |
| 9 | 298 `test_only_the_terminal_owner_can_see_the_freeze_action` | C | クゼ表示、モリ/セナ非表示。現在はジンも端末所有者で、単数の説明は古い。`test_station_drill_control_terminal.py::test_both_keepers_see_and_can_use_the_control_terminal` が所有者2人/クルー6人を既に検査。クルーのfreeze_fuel/表示ラベル非露出をそちらへ移した |
| 10 | 316 `test_valves_are_hidden_until_the_fuel_freezes` | R（両行） | モリ/fuel_bay/open_thaw_valve、セナ/machine_room/open_oil_feed_valve。両弁の凍結前後を別々に観測する。片側だけhide設定を落とす退行。陽性あり、単なる文字列非存在ではない |
| 11 | 330 `test_wrong_name_guidance_does_not_reveal_an_inactive_valve` | R | 救済一覧の平常時秘匿と活性時公開。普通の観測と別経路。helperを本番が使うことを確認。弱い私有述語検査として削除しない |
| 12 | 343 `test_two_people_restore_fuel_within_the_three_tick_window` | F | 復旧が締切を無効化し、両弁を隠す契約。元の_prepare_action直呼びを実interact二回へ変更。左右それぞれの返値success=Trueを必須にし、check_game_end().is_ended=Falseへ直した。3 tick境界は#17が担う。#22の通常点検不変を吸収。元の10 tickを維持 |
| 13 | 368 `test_restoration_is_announced_once_to_people_who_did_not_open_a_valve` | R | 非参加者6人に全員文だけ、参加者2人には現場文も届く。#6の全員回数では参加者限定の漏洩を拾えない。3 tick目は重複再通知を検出するため必要。既存の参加者文検査をそのまま保持した |
| 14 | 396 `test_partial_prepare_times_out_but_does_not_cancel_the_deadline` | R | 部分準備が3で解除・本人へ失敗文、9で独立締切。誰も準備しないケースとは別。私有の準備関数自体は本番で使用されており、今回は変更しない。9 tick維持 |
| 15 | 418 `test_ignored_freeze_reaches_the_deadline_and_loses` | R | 未準備でも初回9 tickで敗北。同期on_timeoutに締切を誤配置する退行を検出。reason実値と宣言descriptionは異なる契約として読む。この試験は変更せず、#23は別の宣言契約のまま保持した |
| 16 | 440 `test_distance_equals_the_window_so_one_runner_cannot_cover_both_valves` | R | 最短移動距離3と窓3、2役のシナリオ設計。名前は一人二役禁止の原因を誤解させる。#1101本文どおり移動距離と宣言窓を表す名前へ変更。runtimeはgroup宣言を取るためだけだったのでraw JSONへ置換し、全世界構築を除いた。独立した地理契約は保持 |
| 17 | 473 `test_distinct_people_complete_on_the_third_counted_tick` | R | 実scenario窓=3でprepare_tick0/2が成立。汎用resolverの窓2だけではscenarioの3→2退行を拾えない。専用stageの本番入口と実配線を使うため保持。世界tickを走らせず判定できており、効率理由の削除不要 |
| 18 | 490 `test_distinct_people_miss_the_window_on_the_fourth_counted_tick` | R | 実scenarioの0/3は不成立、両準備解除、両者に失敗文。#1101で3→4変異の保持根拠。後半9tickも保持。両役失敗後の締切継続を弱めない（stage.run(3)はruntimeの時刻を進めない） |
| 19 | 514 `test_one_player_is_rejected_when_trying_to_prepare_both_valves` | C | 別室へ移動した同一人の二役拒否。`test_interact_absorbs_synchronized_preparation.py::TestInteractRegistersTheListenerSide::test_one_listener_cannot_take_both_sides_through_interact` が同じ実scenario/移動/本番入口でより強い。first.success、理由「別の参加者」、非復旧を移してから、元の私有メソッド直呼びの重複を削減した |
| 20 | 534 `test_pressure_gauge_shows_world_minutes_only_during_the_emergency` | R | 平常時非表示、1tick後40分、生の内部キー非露出、復旧後非表示。pressure状態のhidden_state_keys検査も自動導出の設定経路の根拠。直接restoredを加えるのは表示条件の対照、実復旧は#12が所有 |
| 21 | 565 `test_duty_board_teaches_the_emergency_procedure_before_freezing` | R | 平常時に当番表を読む実操作で、二室/二人/片側不可を学べる。#1117の事前知識境界。文の独立仕様検査であり、inventory羅列として消さない |
| 22 | 577 `test_emergency_valves_do_not_count_as_routine_tasks` | F | 2操作の存在は検出するが、effects空に対するallは実際の復旧効果を見ない。#1352以降、検査位置が古い。#12で通常作業required_flags集合と実復旧前後の交差集合が同じことを検査し、成功したfuel_restoredの陽性と併置。同期on_completeへ点検フラグを追加する変異で、原版の見逃しと新試験の赤を確認。元の宣言走査を退役した |
| 23 | 596 `test_alarm_and_deadline_wake_every_player` | F | 6イベントの全員配送・手番対象という独立した設定契約を保持。実予約を保証するかのような名前を `test_alarm_restoration_and_deadline_declare_all_player_turn_notifications` へ改め、未使用runtime引数だけ除去。実scheduler配線の新証明は今回対象外 |

集計: R15宣言（パラメータ展開17ケース）、F4、C4、D0。Fの通常作業非加算は既存復旧試験へ吸収したため、主ファイルは18宣言/20ケースになる。

## 統合先1: 制御端末の全23宣言

対象: `tests/demos/test_station_drill_control_terminal.py`。2値の非扉操作、クルー6人の事前知識、所有者2人、クルー6人の非露出を展開して35ケース。このファイルでの変更は最初の試験の全クルーループに非露出2条件を移したことだけ。ほかは独立契約として保持し、別目的の整理へ広げない。

| 行・宣言 | 判定 | 独立契約・検出する退行／今回の扱い |
|---|---|---|
| 110 `test_both_keepers_see_and_can_use_the_control_terminal` | R | クゼ/ジンに3操作と説明が見え、クルー6人は端末非表示・所持拒否。ジンの配布漏れ、知識漏洩、非所持者実行を検出。凍結元のクルーへのfreeze_fuel/日本語ラベル非露出を吸収した |
| 131 `test_world_scoped_terminal_cooldown_blocks_the_partner` | R | 別所有者が同じcut_powerを直後に使えない。world→actor縮退を検出。操作間共有とは別 |
| 140 `test_world_scoped_terminal_cooldown_allows_the_partner_after_twenty_five_ticks` | R | cut_power後25 tickで相方のfreeze_fuelを許す。共有待ち時間が永久禁止になる退行を検出。24陰性はこの宣言には無いが、今回凍結元#5で補う。ここを別目的で改変しない |
| 152 `test_world_scoped_terminal_cooldown_survives_a_snapshot` | R | codec capture→新runtime restore後も別所有者のfreezeを拒否。共有記録の保存漏れを検出。2世界は異なる状態の往復に必要、共有fixture化不可 |
| 170 `test_blackout_blocks_the_partners_fuel_freeze` | R | 停電→凍結の操作間共有。cooldown_groupの片側漏れを検出 |
| 179 `test_fuel_freeze_blocks_the_partners_blackout` | R | 凍結→停電の逆方向。保存キーが操作依存で分裂する退行を逆側でも検出 |
| 188 `test_blackout_and_bulkhead_cooldowns_are_independent` | R | cut_power直後に同じ人のseal_bulkhead成功、隔壁結果文あり。隔壁まで共有groupへ含める退行を検出 |
| 199 `test_bulkhead_does_not_block_non_door_sabotage` | R（2行） | 非扉操作cut_power/freeze_fuel各行。先にseal_bulkhead、次に相方の操作成功。前行と逆向き・別actorで独立性を保証 |
| 209 `test_bulkhead_cooldown_expires_after_ten_ticks` | R | 相方が9で拒否、10で成功という両側境界。凍結の25と別の宣言値。10 tick維持 |
| 223 `test_blackout_hides_tasks_in_every_room` | R | 16作業の存在、全9室BRIGHT→DARK、作業物体行が消える。担当欄由来の文で誤検出しない `_has_object_row`を使う。効果先漏れ・暗所表示漏れを検出 |
| 238 `test_main_distribution_panel_restores_all_rooms_without_a_role_gate` | R | 暗所で配電盤と操作が見え、クルーの実操作で全9室復旧。暗さで復旧操作まで消す行き詰まりを検出 |
| 254 `test_blackout_observation_reaches_affected_rooms` | R | 明示6人/6室（モリ観測室、セナ医務室、アオイ温室、ハギ通信室、ユラ燃料庫、ジン倉庫）へ新規spot_public_effect_observed。行為者位置だけに配送する退行を検出。全9室への配送を実測しているとは主張しない |
| 283 `test_sabotage_keeps_the_world_design_asymmetric` | R | 9室効果、25/10/25待ち時間、共有単位、灯り2個、現地復旧と全員hall開始という設計契約。宣言独立検査。今回の凍結#5では演算の境界を別に守るのでこの25固定に任せきりにしない |
| 341 `test_remote_bulkhead_closes_both_observatory_passages` | R | 明示対象の記録、盤に操作なし、2通路のbindingと4tick。宣言の配線を検査。実通行/時間の試験はtest_the_bulkhead_falls_and_lifts_by_itself.pyにも存在。今回は隔壁の契約比較へ範囲を広げず、保持した |
| 382 `test_remote_item_effect_rejects_an_object_missing_from_the_world` | R | 実操作を不明object999999へ向け、所定例外を確認。暗黙の行為者側対象へ縮退する退行。合成するのは入力で、結果をmockしていない |
| 409 `test_remote_item_effect_rejects_objects_owned_by_different_rooms` | R | 隔壁盤と配電盤という別室2対象を指定した実操作が拒否。片側だけ適用する静かな欠損を検出。上の不明対象と別条件 |
| 445 `test_inert_bulkhead_panel_does_not_advertise_a_local_control` | R | 操作が無く状態だけの盤の説明から旧操作の宣伝を除く。interaction空だけでなく説明の嘘を防ぐ。一般のAPI在庫試験ではない |
| 465 `test_each_crew_member_knows_power_can_be_cut_without_learning_the_role` | R（6行） | モリ/セナ/アオイ/ハギ/ユラ/サキ。各systemに遠隔停電の事実、追記箇所にkeeper/管理人なし。1人だけ共通知識が欠落する退行を検出 |
| 479 `test_each_terminal_holder_knows_the_shared_sabotage_hand` | R（2行） | クゼ/ジン。能力、共有待ち時間、操作者秘匿、敗北、二室二人復旧、点検を中断する事実が各systemにある。片方だけ古い役職文になる退行 |
| 497 `test_persona_text_avoids_known_tactical_phrases` | R | 全players+roleの本文に「待つ/待ち伏せ/狙え/走る/決められる」を含めない独立した執筆方針。未知の言い換えは対象外という限界もdocstringが明示。単純grepというだけで削除しない |
| 513 `test_crew_systems_do_not_receive_the_impostor_hand_description` | R（6行） | モリ/セナ/アオイ/ハギ/ユラ/サキに5つの手札説明なし。system知識の境界で、110行のuser所持品表示とは別。吸収先の編集でこれを置換しない |
| 527 `test_sabotage_hand_description_hides_role_names_and_declared_ticks` | R | keeperの手札段落に役割名/10/20/25の数値二重宣言が無い。物語知識と内部待ち時間の分離。旧文のコピーへ戻る退行 |
| 543 `test_old_sabotage_locations_have_no_operable_remnants` | R | 旧4室の盤/通気口/旧接続bindingを残さない移行済みscenario契約。表示や通路が旧場所に復活する退行。今回の凍結整理と独立なので保持 |

## 統合先2: interact同期入口の全6宣言

対象: `tests/application/llm/services/executors/test_interact_absorbs_synchronized_preparation.py`。6ケース。実runtime・本番executor・dispatchのsay_inline wrapperを使い、準備や配信結果を偽造するmockはない。

| 行・宣言 | 判定 | 独立契約・検出する退行／今回の扱い |
|---|---|---|
| 120 `TestInteractRegistersTheListenerSide.test_interacting_with_a_valve_registers_a_preparation` | R | 実interactの成功/未完了文/二種準備フラグ。#1352の「手をかけたが登録なし」退行。二種フラグは現在の登録と互換条件の両方が本番で利用される |
| 130 `TestInteractRegistersTheListenerSide.test_two_listeners_interacting_in_the_same_tick_restore_the_fuel` | R | 別室の実interact二人→1tickでfrozen消失/restored成立/参加者観測。本番分岐断線を検出。凍結元#12は締切後安全・弁非露出を担うため別契約 |
| 145 `TestInteractRegistersTheListenerSide.test_one_listener_cannot_take_both_sides_through_interact` | F | モリが燃料庫で受持ち→機関室へ移動→二役拒否、前提失敗コード、frozen継続。凍結元#19より本番に近い。元#19のfirst.success=True、理由「別の参加者」、fuel_restored非成立を吸収して陰性の原因を特定した。このファイルでの変更はこの宣言のみ |
| 159 `TestInteractRegistersTheListenerSide.test_say_inline_still_reaches_the_room_when_a_valve_is_taken` | R | 同室クゼに添えた発言が届く。同期処理早期returnで発言配送が抜ける退行。wrapperが本番と同じため観測をmockで生成していない |
| 171 `TestInteractRegistersTheListenerSide.test_an_ordinary_interaction_still_runs_its_effects` | R | hallの当番表で成功・点検文・sync_prep無し。全部のinteractを準備扱いにして通常効果を殺す退行を陽性で検出 |
| 186 `TestNoSeparateToolRemains.test_prepare_action_is_not_in_the_tool_list_of_a_world_with_sync_groups` | R | 実世界の公開ツール一覧からprepare_action無し、interact有り。#1352の二つの動詞が同じaction名を奪い合う問題に対する公開API契約。単なるexport羅列とは扱わない |

## 移管対応と境界の保存

- 主#2の順序と#3の各周期一回性 → 主#6。各周期の相対1/3/5/7を1 tickずつ進め、全員の警報イベント列を比較。元からあった全観測文での件数比較も保持する
- 主#9のクゼ陽性は制御端末の二所有者陽性へ包含。モリ/セナのfreeze_fuelと日本語ラベル陰性は全クルー6人の同じuser promptへ移した。system知識の試験とは混ぜない
- 主#19のfirst成功・second失敗・理由・未復旧 → interact145行の既存試験。燃料庫から機関室への移動、拒否コード、凍結継続も残す
- 主#22の通常点検非加算 → 主#12の実interact復旧前後のrequired_flags交差集合比較。左右の実操作successを必須とし、両操作の存在は実scenario読み込みの検査も維持する
- 主#5は復旧が1 tick進めることを踏まえ、1で拒否、24で拒否、25で成功。合計の時間進行は変えない
- 主#12は元の10 tick、主#18は失敗後の9 tickを維持。主#6/#7は実際の二周期・25までの待ち時間を維持し、時刻の直接書き換えで省略しない
- 主#13の参加者2人の現場文と非参加者6人の全員文の差を独立保持
- 主#16は地理のJSON契約へ縮小するが、ロード済みgroupへの接続は実runtimeを組む主#17/#18が引き続き保証する
- 主#23は全員への手番対象を宣言する設定契約だけを検査する。実schedulerへ予約されたことの新しい証明は対象外。元の保証範囲を削らず、誇大な命名と未使用fixtureだけを修正した

`_prepare_action`、resolver、registry、救済一覧helperには本番の呼び出しがあるため、私有名だけを理由に削除していない。新たなテスト専用の本番注入口も追加していない。

## 保存性点検で見つけて直した欠落

最初の候補では、元の全観測文に対する警報回数検査を、`event_id`が`fuel_freeze_alarm_`で始まる配送結果の列比較に置き換えた。これは発火時刻と順序を強くする一方、**別のidを持つ出来事が同じ警報文を重複配送する**場合を見落とした。

点検で指摘を受け、元の `prose.count(_ALARM) == 2` と各段階文の件数2を、新しい時刻・順序検査に加えて戻した。別idの出来事を追加して同じ40分警報を両周期で配送する変異は、修正前候補で緑、修正後では件数4と期待2の不一致で赤になった。この保存性修復前の候補計時は最終比較から除外する。

## 変異と原版対照

所有者を1つずつ変更し、該当試験を直列で実行して、意図した理由で落ちることを確認した。各変異終了後、対象ファイルを元のバイト列へ復元した。本番に変異は残していない。

| 変異名の末尾 | 操作と意図した失敗 | 結果 |
|---|---|---|
| cooldown-early | remaining_ticksを1少なくする | 24tickの拒否でDID NOT RAISE。原版の同じ試験は緑 |
| alarm-order | 30分と20分の発火窓を交換 | 二周期試験のtick3で警報列不一致 |
| alarm-window | 40分警報の上限を2→3 | tick2で余計な40分警報を検出 |
| alarm-once | 30分警報をonce=true | 二周期目の30分が欠落して不一致 |
| routine-count | 同期on_completeにtask_wind_instrumentsを追加 | 復旧前後の通常作業集合不変で赤。原版の復旧試験・元のeffects走査は両方緑 |
| ended-after-restore | fuel_restoredを追加敗北条件にする | is_ended=Falseで赤。fuel_lostは無いまま、原版の理由比較は緑 |
| crew-leak-action | モリの実promptへfreeze_fuelが出る入力 | 移した操作名非露出で赤 |
| crew-leak-label | モリの実promptへ燃料を凍結させるが出る入力 | 移した日本語表示非露出で赤 |
| one-player-both | executorの既存役割拒否を外す | 二つ目のsuccess=Falseで赤 |
| window-2 | 実scenarioの同期窓を3→2 | 3手番目の実stage復旧成立が赤 |
| window-4 | 実scenarioの同期窓を3→4 | 4手番目にfuel_restoredが立ち陰性が赤 |
| missing-open_thaw_valve | 左弁の操作宣言を削る | loaderがrequired_action_names未宣言を拒否してsetup error |
| missing-open_oil_feed_valve | 右弁の操作宣言を削る | 同じく右側名を特定したsetup error |
| alarm-other-id-after-preservation | 異なるidで同じ40分警報を追加 | 保存性修復前は緑、修復後は全proseの件数4!=2で赤 |

合計14変異を検出。12件は狙った試験本文のassertで赤、弁宣言削除2件はloaderの未宣言操作拒否によるsetup error。この2件を「新しいsuccess assert自体が落ちた」とは数えない。実scenario構築が元の両操作存在契約を引き続き守ることの証拠である。

原版との対照は待ち時間・通常点検加算・誤敗北の3種類/4ケースが緑で、修復後だけが赤になった。さらに保存性修復前候補との別id重複対照が1ケース緑。既存本番の不具合を修正したという意味ではなく、試験が見逃していた退行を検出するようにした。

## 検証と費用

基準と候補はいずれもPython3.10.22で、外部ネットワーク遮断、認証環境変数除去、対象checkoutのsrcを読むことの確認付きで直列実行した。テスト内の有料API利用はない。

- 基準: 主25 passedを2反復、統合先35+6=41 passed、関連13+12+8+16=49 passed
- 初期候補: 主20+統合先41=61 passed
- 保存性修復前候補の主20×2および統合先/関連90も成功したが、その計時は最終比較に採用しない
- 保存性修復後: 主20 passedを2反復、統合先41+関連49=90 passed。失敗・skipなし
- 対象3ファイルのruff、`git diff --check`は成功
- CI全件・quality・型検査はこの局所監査では未実行。通常CIでは既存の `uv run --frozen pytest -n auto` に含まれるため、登録先の変更はない

局所検証の標準入口:

```sh
uv run --frozen pytest tests/demos/test_station_drill_fuel_freeze_emergency.py --durations=20
uv run --frozen pytest tests/demos/test_station_drill_control_terminal.py tests/application/llm/services/executors/test_interact_absorbs_synchronized_preparation.py tests/demos/test_sync_levers_demo_scenario.py tests/application/world_graph/test_synchronized_action_resolver_stage.py tests/demos/test_station_drill_critical_sabotage_meeting.py tests/demos/test_station_drill_ongoing_conditions.py
```

試験の行数は1365→1312、差引53行減（主611→553、制御端末563→565、interact191→194）。本番0、共有支援0。文書の追加はこの試験削減数と分けて数える。二周期と時間境界を残すため、速度改善のために保証範囲を狭めていない。

### 保存性修復後の最終比較

比較に採用する候補は `station-preserved-final1` と `station-preserved-final2` だけ。`station-final1/2` および初期候補は全観測文の件数を戻す前なので、最終性能値には使わない。

| 実行 | 結果 | 実経過秒 | pytest計測秒 | setup合計秒 | call合計秒 |
|---|---|---:|---:|---:|---:|
| 基準1 | 25 passed | 23.178 | 20.356 | 5.840 | 13.116 |
| 基準2 | 25 passed | 22.288 | 19.303 | 5.223 | 13.325 |
| 保存性修復後1 | 20 passed | 19.628 | 17.125 | 4.884 | 11.496 |
| 保存性修復後2 | 20 passed | 19.417 | 16.713 | 4.691 | 11.283 |
| 修復後の統合先・関連 | 90 passed | 16.484 | 13.798 | 6.739 | 6.166 |

主ファイルの実経過平均は22.733→19.522秒、この局所2反復では約14.1%短縮。初回importやキャッシュ・実行時の揺れを含む小標本であり、CI全体の速度改善率ではない。統合先と関連は基準で別プロセス、最終で同一プロセスにまとめたため、それらの合計時間は直接比較しない。

計測ごとに実行引数、参照src、終了コード、実経過/CPU時間、XML、ケース別setup/call/teardownを記録した。全変異を復元した最終試験3ファイルについて、ruff・diff checkを再確認済み。

独立した保存性レビューでも、指摘された全観測文の件数の修復後に保証欠落の追加指摘がないことを確認した。公開・取り込みの判断はこの局所試験結果と分けて扱う。
