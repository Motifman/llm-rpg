# 発電機の温まり通知と再始動の試験監査

## なぜ

`tests/demos/test_mine_village_noise_and_lift.py` には、説明が約束する時刻より後でしか結果を見ない検査と、別の前提条件による拒否で目的の条件を検査できない箇所があった。保証の穴を本番の操作・時刻進行・観測を使って修復し、同じ条件を再実行する弱い試験を一つ統合した。

速度や行数だけを理由に試験を捨てない。二巡目の獣の覚醒・睡眠、燃料不足、物語文の答えの非露出、届かない場所、再始動後の再通知、trace の受信時刻・受信者は維持した。

## 何を

- 温まり通知の五地点すべてで、始動後 5 tick は未着、6 tick で一件、その後三 tick でも一件と検査する。従来は 5 tick と 9 tick の結果だけだったため、7～9 tick に遅れても通った。
- 燃料切れで止めた発電機について、給油だけでは動かないという元の検査を残したうえで、実際に再始動する。再始動後 5 tick では荒い唸りの文で昇降機を拒否し、6 tick では動くことを確認する。従来は再始動しておらず、停止状態の拒否で温まりの消去漏れを隠した。
- 温まり前の拒否を検査する二つの試験のうち、拒否と「温」を含まないことだけを見る一宣言を、同じ準備で正確な返答まで確認する既存試験へ統合した。

変更は対象ファイルの三宣言に限定した。本番コード・シナリオ・共通補助関数は変更していない。

## 独立した仕様と導入履歴

- [Issue #1600](https://github.com/Motifman/llm-rpg/issues/1600) は始動から 6 tick の知らせを要求し、6 tick や燃料量の変更を対象外とした。起動後 5 tick に断られた直後、温まったことに気づかず脱出を逃した実 run が動機である。
- [決定コメント](https://github.com/Motifman/llm-rpg/issues/1600#issuecomment-6108377037) は、機械室・隣の三地点・乗り場へその tick に通知することを選んだ。全員への通知は、遠くで唸りの質を聞き分けられるのが不自然なため退けた。
- [PR #1604](https://github.com/Motifman/llm-rpg/pull/1604)、[設計判断 D1600](../design_decisions.md#d1600-試して学ぶ決まりは外れ方を足りないものごとに分け満ちた瞬間を音で知らせる答えは書かない)、[シナリオ設計](../mine_village_scenario_design.md) が、温まった同じ tick・一回・停止後の再通知を定める。期待時刻を本番 JSON の offset から計算して追従させてはいない。
- [PR #1537](https://github.com/Motifman/llm-rpg/pull/1537) は、6 tick の温まりと燃料切れでの温まり消去を記録している。停止後の試験の元の説明も「温め直すまで動かない」と約束していた。
- [PR #1614](https://github.com/Motifman/llm-rpg/pull/1614) は、籠の外にいる人へ操作盤の位置を先に伝える拒否順位と、説明文の位置を修復した。この四状態の表と静的な説明文検査は削らない。

## 所有境界

主所有者は `data/scenarios/mine_village_v1.json` の発電機・昇降機・場所別通知。`create_world_runtime` で実際の宣言を読み、`do_interact` と `advance_tick` で進め、本人の観測バッファと trace を見る。

本番の入口は `runtime_manager.create_session` と `SpotGraphToolExecutor`。始動時刻は通常の `RECORD_OBJECT_STATE_TICK` で記録され、`SpotGraphSimulationApplicationService` が実際の各処理段を進める。`SpotGraphScenarioEventStageService` が宣言順にイベントを確定し、`ScenarioConditionEvaluator` が時刻を判定する。`WorldRuntime` が場所の在席者を選び、`ObservationAppender` が観測と trace を残す。

この組合せでは、共通の時刻判定が正しくてもシナリオの通知順や場所を間違えれば壊れる。したがって、共通評価器だけの単体試験へ置き換えない。時計だけの書換えや新しい試験専用の本番入口も加えない。

温まり前拒否の統合先は `TestLiftRefusalTellsWhatIsMissing.test_lift_refuses_before_warm_with_the_rough_hum`。削除側の `_ready` を展開すると、両者とも `_open_safe` → `_fuel_and_start_generator` → `_board` → 5 tick である。統合先の本番の返答との完全一致は、元の「温」を含まない検査も満たす。

## 全宣言の台帳

基準は main `0b51eb28` の対象ファイル、Git blob `8cc90b9a3d4fe63ccd11394eeeeef3c21fe50b20`。行番号は変更前。R は保持、F は契約を保持して検査を修理、C は強い既存試験へ統合。40 宣言すべてを読み、パラメータ各行も確認した。

R=35、F=4、C=1。F のうち今回修復したのは通知時刻と停止後の温まりの二件。残り二件は下記の次の修理として保持した。

| 判定 | 宣言 | 契約・実際に捕捉できる回帰・残す理由 |
|---|---|---|
| R | `TestNoiseWakesTheBeastOfThatSector.test_beast_attacks_someone_where_it_appears` (L143) | 出現地点のミオだけ HP が減り、南のサヨは減らない。怪物配置だけの試験では攻撃配線の欠落を捕まえられない。標的抽選への対策は既存のハル退避を維持する。 |
| R | `TestNoiseWakesTheBeastOfThatSector.test_beast_wakes_again_after_sleeping` (L157) | 二巡目の再出現と再出現後 19/20 tick を保護。awake_at 更新漏れ、二巡目が永久に起動しない/直ちに眠る回帰は初回睡眠試験では見えない。 |
| R | `TestNoiseWakesTheBeastOfThatSector.test_beast_description_does_not_tell_what_wakes_it` (L172) | 本番 JSON の獣の説明に R5 の答えを漏らさない。#1537 で実際に「物音に目を覚まし」を削除した歴史があり、安い独立した物語文の契約。 |
| R | `TestNoiseWakesTheBeastOfThatSector.test_more_noise_while_awake_brings_no_second_beast` (L178) | 起きている間の追加の音が同じ北の獣を二重生成しない。初回の閾値試験とは生存状態の遷移が異なる。 |
| R | `TestNoiseWakesTheBeastOfThatSector.test_no_beast_at_start` (L186) | 初期配置が条件無視で獣を作る回帰。最初の tick 後に空を確認。 |
| R | `TestNoiseWakesTheBeastOfThatSector.test_beast_appears_where_the_noise_reached_the_threshold` (L193) | deep/north/south の全 3 行で 2 回では空、3 回目同 tick に指定場所の一頭。閾値変更、区画誤配線を捕捉。 |
| R | `TestNoiseWakesTheBeastOfThatSector.test_noise_does_not_add_up_across_sectors` (L203) | 北 2 + 南 2 を総和してしまう回帰。区画ごとの単独試験では代替できない。 |
| R | `TestNoiseWakesTheBeastOfThatSector.test_machines_and_the_timber_are_loud_in_the_deep` (L211) | 発電機・ポンプ・支柱という異なる操作の音が深層に加算される。水門だけの閾値試験の代用不可。 |
| R | `TestNoiseWakesTheBeastOfThatSector.test_the_beast_goes_back_to_sleep` (L222) | 初回 19/20 tick の消滅境界。二巡目だけに統合せず、初回の開始時刻と状態遷移を残す。 |
| R | `TestNoiseWakesTheBeastOfThatSector.test_noise_counts_again_from_zero_after_the_beast_sleeps` (L233) | 眠ったあとの 2 回では起きない。二巡目 3 回で起きる試験だけでは過少閾値/古い累積値を捕まえられない。 |
| F | `TestDistantCuesTellSomeoneIsAhead.test_generator_hum_reaches_someone_deep_in_the_other_tunnel` (L250) | 遠方への一件・名前非露出は有効。ただし説明は「次の tick」、観測は 3 tick 後のみで遅延を許す。温まり通知とは別の起動通知。今回は保持し、独立契約確認後に 1 tick 時点の検査を追加する候補。 |
| R | `TestDistantCuesTellSomeoneIsAhead.test_hum_is_heard_again_after_a_restart` (L261) | 燃料枯渇→給油→再始動で遠方への起動音が二件になる。停止時 generator_hum_heard 消去漏れを保護。温まり通知とは別フラグ。 |
| R | `TestDistantCuesTellSomeoneIsAhead.test_safe_bell_reaches_someone_far_away` (L281) | 金庫を開けた次 tick に北の竪坑口へ一件の鐘、開けた人名は出ない。鍵の付与だけでは守れない。 |
| R | `TestSafeAndKey.test_wrong_code_is_refused` (L296) | 0000 を前提条件で拒否し、意図した文を返し、鍵を付与しない。absent を拒否とみなさない。 |
| R | `TestSafeAndKey.test_desk_holds_the_code` (L304) | 机を実際に調べた返答に 1907 がある。南の初期知識とは独立した北の発見経路。 |
| R | `TestSafeAndKey.test_right_code_gives_the_key_once` (L310) | ゲンの正答で鍵が付与され、サヨの再開錠が拒否。誤答のみでは付与/一回性を守れない。 |
| R | `TestSafeAndKey.test_south_knows_the_code_north_does_not` (L319) | 本番 persona の 1907 所有者集合が gen/sayo のみ。初期情報の非対称性は静的でも独立契約。 |
| C | `TestLift.test_lift_refuses_before_the_generator_warms_up` (L334) | 鍵・乗船・缶一個・始動後 5 tick の拒否を L480 の test_lift_refuses_before_warm_with_the_rough_hum が同じ実境界で完全な返答一致まで保護。禁止語「温」は一致する期待文にも含まれない。後者を残し、この一宣言を削減した。 |
| R | `TestLift.test_lift_starts_once_the_generator_is_warm` (L344) | 始動後ちょうど 6 tick の成功。燃料容量の兄弟試験は +6 tick をポンプ後に進めており、この正確な温まり境界を代替しない。 |
| R | `TestLift.test_lift_refuses_without_the_key` (L353) | 温まり・燃料・乗船を満たして鍵だけ欠くと鍵の文で拒否。別の前提条件による偽陽性を避けている。 |
| R | `TestLift.test_anyone_holding_the_key_can_start_the_lift` (L364) | ハル以外のゲンでも開錠・鍵保持・乗船・始動が成功。人物固定の誤りを捕捉。開けた人と異なる人への鍵の受け渡しは実行しておらず、その保証と報告してはいけない。 |
| F | `TestLift.test_lift_refuses_once_the_generator_has_stopped` (L375) | 停止→給油後の拒否は守るが、再始動していないため generator_running が先に拒否する。generator_warm 消去漏れの証明にはならない。今回、再始動後 5 tick の正確な拒否文と 6 tick の成功を追加し、穴を修復した。 |
| R | `TestLift.test_lift_refuses_with_too_little_fuel` (L391) | 燃料 1 かつ温まった状態で short_of_fuel の正確な文。兄弟容量試験の数値観測/ポンプ一回で燃料 2 の成功と役割が違うため保持。 |
| R | `TestLift.test_people_on_the_landing_escape_and_the_rest_are_left` (L406) | 乗船した二人 RESCUED、別地点の二人 STRANDED、全体終了。兄弟の乗り場にいるだけの人は取り残す契約とは異なる。ゲーム終了までの保護を落とさない。 |
| R | `TestLift.test_lift_runs_only_once` (L426) | 二度目を明示した文で拒否。別の条件で拒否して偶然通るのを防ぎ、一回性を保護。 |
| R | `TestLiftRefusalTellsWhatIsMissing.test_lift_refuses_with_the_generator_off` (L470) | 鍵・乗船は満たすが電源停止なら停止用の正確な文。D1600 の三種類の区別の主所有者。 |
| R | `TestLiftRefusalTellsWhatIsMissing.test_lift_refuses_before_warm_with_the_rough_hum` (L480) | 鍵・乗船・燃料を満たし、5 tick で荒い唸りの文による拒否。上記 C の受入先。完全一致で文と対象理由の対応を保護。 |
| R | `TestLiftRefusalTellsWhatIsMissing.test_refusals_are_all_different` (L492) | 本番の三つのフラグと三つの失敗文の対応を読んで確認。#1604 のレビューで単なる値集合から対応比較へ直した履歴がある。実動作の三試験と重なるが安価で、今回これを削る理由に静的であることを使わない。 |
| F | `TestLiftRefusalTellsWhatIsMissing.test_refusal_does_not_name_the_answer` (L506) | 3 行すべて本番の返答ではなく _LIFT_REFUSAL 内の期待値だけを検査。別試験の本番一致に依存する。禁止語の独立契約は保持し、将来本番の対象前提条件の failure_message に直接適用するか実返答検査へ吸収。 |
| R | `TestLiftControlsAreInsideTheCage.test_someone_outside_the_cage_is_told_the_controls_are_inside_first` (L549) | 4 行 no_key_generator_off/key_generator_off/key_not_warm/key_short_of_fuel を維持。操作盤の位置が先に伝わる可観測な拒否順位は D1613 の実回帰。兄弟の全部準備済みだが外にいる試験とは異なる。 |
| R | `TestLiftControlsAreInsideTheCage.test_lift_description_puts_the_controls_inside_the_cage` (L558) | 「籠の中」であり「脇」でない本番説明。#1613 の実 run の誤解を防ぐ物の配置の契約。実操作の拒否だけでは説明の誤りを捕まえない。 |
| R | `TestLiftControlsAreInsideTheCage.test_every_refusal_of_start_lift_is_a_different_sentence` (L566) | start_lift の全前提条件の文が一意。trace から理由を特定できる D1613 の契約で、発電機三理由の検査より広い。 |
| F | `TestGeneratorWarmthIsHeard.test_notice_arrives_exactly_when_warm` (L579) | 5 行 machine_room/mid_junction/lower_shortcut/miners_rest/lift_landing。5 tick 無通知と 9 tick 一件のみ。6 tick 時点の通知を見ず、7～9 tick 遅延を許す。今回、6 tick 直後一件を確認し、その後 3 tick の一件維持も残した。 |
| R | `TestGeneratorWarmthIsHeard.test_notice_does_not_reach_far_places` (L593) | north_tunnel/gas_chamber/village_square/timber_passage の全 4 行。全員配信/遠方誤配線を検出。正の 5 地点だけでは代用不可。 |
| R | `TestGeneratorWarmthIsHeard.test_notice_comes_again_after_a_restart` (L602) | 燃料枯渇で停止したのち再給油・再始動・6 tick で温まり通知が二件。global heard フラグが消えず二回目が抑止される回帰を保持。 |
| R | `TestGeneratorWarmthIsHeard.test_notices_name_neither_the_answer_nor_anyone` (L620) | 本番五通知の SHOW_MESSAGE が一つずつあり、温/準備/燃料/人名差し込みがない。実装ソースの grep ではなくシナリオ文の独立契約。 |
| R | `TestGeneratorWarmthIsHeard.test_rough_hum_before_and_settled_hum_after_pair_up` (L633) | 始動時の荒い唸りと機械室の落ち着く知らせ、および不成立文が対になる D1600 の学習可能性。件数だけでは語の対を守れない。 |
| R | `TestNoiseAndLiftLeaveATrace.test_beast_waking_and_sleeping_are_recorded` (L672) | 獣の出現/消滅フラグが scenario_event・actor None で記録される。配置や攻撃だけでは観測性の欠落を捕まえない。 |
| R | `TestNoiseAndLiftLeaveATrace.test_lift_departure_names_who_started_it` (L685) | lift_departed が spot_interaction・ハルで一件。結果状態だけでは行為者の出所を守れない。 |
| R | `TestNoiseAndLiftLeaveATrace.test_warm_notice_records_the_tick_and_who_heard_it` (L698) | 起動時刻+6、受信者ハル/ゲン、場所別 event_id を trace で完全一致。通常通知試験との二層は trace 脱落/誤時刻という別リスクがある。隣の三地点の遅延までは保護しない。 |

## 故意の変異と復元

既存の本番シナリオの宣言だけを一時的に変更し、同じ試験環境で対照を取った。構築失敗や通信失敗ではなく、次の検証が失敗することまで確認した。

| 変異 | 変更前の試験 | 変更後の試験 |
|---|---|---|
| 温まりイベントから分岐の通知だけを `next_event_id` と `delay_ticks=1` で予約し、一 tick 遅らせる | 五地点の通知＋二地点の trace、6 件すべて通過 | 分岐の行だけ、6 tick 時点の件数が 0 で失敗。他の五件は通過 |
| 停止イベントから `CLEAR_FLAG generator_warm` だけを外す | 停止後の試験は通過 | 再始動後 5 tick の操作が refused でなく done になり失敗 |
| 温まり前の拒否文を燃料不足の文へ差し替える | 統合先は変更していない | 残した統合先が完全一致で失敗 |
| 昇降機の `generator_warm` 前提条件を外す | 統合先は変更していない | 残した統合先が早期成功を検出して失敗 |

変異ごとの試験を終えてからファイルを差し替え、すべての変異終了時に本番シナリオと候補試験を元のバイト列へ復元した。復元後のシナリオ SHA-256 は `ab1fdd6d6e7dfb5a0fa661ad089f60ca5ce7088873afa8679801df3d596329bf`、候補試験は `72a4678b5f125ef47b006ed1da466c65bb314274a2446fda6ab9607afad52858`。本番シナリオの Git 差分も空である。

## 試験と計測

- 変更前: 741 行・40 宣言・54 件
- 変更後: 748 行・39 宣言・53 件。テスト +19/-12 行、本番 0 行、試験補助 0 行。監査記録の行数は別集計
- 基準全件を二回、限定範囲を一回、変異の対照を順に実行。変異復元後に全件を二回と関連範囲を再実行
- ローカル検証は Python 3.10.22、pytest 8.4.1、ruff 0.16.8。
- すべて外部ネットワークを遮断し、既存ローカル依存を使った。実 LLM/API は呼んでいない。通常の tick を省略していない
- CI の正式条件は Python 3.10、`uv run --frozen pytest -n auto`。この監査は並列計測の競合を避け、対象範囲を直列で比較した。ローカル結果を CI 全体の成功とは呼ばない

| 範囲 | 結果 | 起動・収集を含む実時間 |
|---|---|---|
| `generator-baseline1` | 54 件、失敗 0 | 54.526 秒 |
| `generator-baseline2` | 54 件、失敗 0 | 54.188 秒 |
| `generator-focused` | 22 件、失敗 0 | 26.834 秒 |
| `generator-final1` | 53 件、失敗 0 | 52.954 秒 |
| `generator-final2` | 53 件、失敗 0 | 53.356 秒 |
| `generator-siblings-baseline` | 156 件、失敗 0 | 57.360 秒 |
| `generator-siblings-final` | 156 件、失敗 0 | 56.807 秒 |

全ファイルの実時間の二反復中央値は 54.357 秒から 53.155 秒（約 2.2% 減）だった。ばらつきと検査量の増加を含む二反復の比較なので、高速化が確立したとは扱わない。

単独の重複を削ったことによる節約だけで高速化を主張しない。再始動の本来の保証のため実 tick を六回増やしたので、今回の主結果は二つの検査の穴を閉じ、同じ境界の重複を減らしたことである。

`ruff check` 対象ファイルと `git diff --check` はどちらも成功。独立した保全レビューの結果は別途確認する。

再現する対象コマンド:

```bash
uv run --frozen pytest tests/demos/test_mine_village_noise_and_lift.py -q --durations=20
uv run --frozen pytest \
  tests/demos/test_mine_village_capacity_and_fuel.py \
  tests/demos/test_mine_village_water.py \
  tests/demos/test_mine_village_map_and_start.py \
  tests/demos/test_mine_village_clues_and_recovery.py \
  tests/demos/test_mine_village_attack_and_steal.py::TestBoardingTheLift \
  tests/application/world_graph/test_spot_graph_scenario_event_stage.py \
  tests/application/world_graph/test_object_state_tick_at_least_null.py -q
uv run --frozen ruff check tests/demos/test_mine_village_noise_and_lift.py
git diff --check
```

## 残る二つの修理

1. `TestDistantCuesTellSomeoneIsAhead.test_generator_hum_reaches_someone_deep_in_the_other_tunnel`: 起動音の説明は次 tick だが、三 tick 後しか見ていない。起動音は温まり音とは異なる契約なので今回は分離した。次は一 tick 直後の一件を確認し、さらに二 tick でも一件のままという検査へ直す。再始動時の遠方通知は別試験として保持する。
2. `TestLiftRefusalTellsWhatIsMissing.test_refusal_does_not_name_the_answer`: 三行とも本番の文ではなく期待値 `_LIFT_REFUSAL` を読む。別試験の本番との一致に依存する形なので、本番の三つの対象前提条件から `failure_message` を読んで禁止語を適用するか、三状態の実返答検査へ吸収する。静的検査の層は今回広げず、現契約と試験を保持した。

## 今後の保守

- 「ちょうど N tick」と約束するシナリオ試験では N-1、N、必要なら N 後の維持を別々に観測する。追加の待機を N の代わりにしない
- 複数の前提条件がある拒否試験では、狙った拒否文まで確認する。停止中の拒否を再始動後の温まり消去の証拠にしない
- 初回と再始動/再覚醒の時刻、燃料一不足/ちょうど足りる境界、別地点への不達は同じ契約ではない。重複統合の前にそれぞれの主所有試験を指定する
- 本人への配達と trace 記録は故障の仕方が異なるので、件数試験だけを理由に観測性の試験を捨てない
