# 相互作用の前提条件と拒否情報を入口で守る

## なぜ

旗や欲求の選択、HP比率の試験には、入力を固定値へ取り違えても通るものがあった。場所条件は私有の判定を直接呼ぶだけで、公開入口から現在地や照明が渡らなくても検出できなかった。対象者の所持品を伏せる分類、入力不足の例外が運ぶ条件、拒否文にも未確認の値があった。

この変更は対象7ファイル94宣言を全文確認し、保持78・修理14・統合2とした。元の入力・断言を先に保持し、同一入力で重複する2宣言だけを後から除いた。製品の振る舞いは変更しない。

## 固定した基準と範囲

- 親は [備蓄対象修正 #1688](https://github.com/Motifman/llm-rpg/pull/1688) の `4f4f39b596eea0a2d0288d28deb7471e88e6c338`。親には別途承認された製品2行修正が含まれるが、この子の製品差分は0
- 親のtreeは `95ee0a37774699df0bc442640e8ed232efc0c23b`。親の回帰6ケースは変更せず関連試験へ含めた
- 調査時のmain `be96ed1a62fad4ecfcbfa86d6da61bc6d83bf609` まで対象試験・製品所有者22パスは親の変更前基準から不変。main単独には備蓄対象の旧不具合が残るため、修正済み親に依存する
- [Itemの保持契約 #1682](https://github.com/Motifman/llm-rpg/pull/1682) は `25075240c79bb81ff8765ed6a8d196582418f699` を参照した。数量の入口とスタック可否は異なる契約であり、Item側の試験を移動・削除していない
- 宣言数94→92、実行件数163→168。追加の独立入力があるため実行件数は増える。短い単体試験の速度改善は主張しない

## 所有者と保持方針

`SpotInteractionService` が条件の対象選択、共通述語への入力、最初の失敗情報、公開実行結果への受け渡しを所有する。`ScenarioPredicateEvaluator` の純粋な比較試験で、この接続を代用しない。条件の秘匿分類は `interaction_condition_visibility.py` が所有し、表示側の行為者条件の絞り込みとは区別する。

実呼出元は `SpotInteractionApplicationService` の物体・宣言済み操作と前提結果照会、`PlayerInteractionApplicationService` の実行可否、`world_runtime` の組立てである。シナリオ読込の形式検証と実行時の拒否も別々に残す。

- 最初の不成立、元の条件実体、作者文面、配列位置を保持する。入力不足・未対応を通常の否定へ落とさず、否定条件でも成立へ反転しない
- `can_interact` は2要素、`evaluate_preconditions` は3要素。3要素と構造化結果の射影試験は独立に残す
- 私有の場所判定と公開入口の確認は同じ入力で併存させる。共通核への委譲試験は実際の条件判定の代わりにしない
- 使う側と対象側、入力と返却結果を区別し、状態・数量・通知の別契約を準備が似ているだけで統合しない
- 所有規約の既存PRと競合させないため、この方針は本書に記録する。共有AGENTSへの統合は別の整理で行う

## 導入根拠

- [旗条件の共通化](https://github.com/Motifman/llm-rpg/commit/7f13d9e75b8d72c1923cdbaa85af4ae6faab723c): 旗名と旗集合を渡し、用途固有の失敗文を保持する
- [数量条件の共通化](https://github.com/Motifman/llm-rpg/commit/9c593e7894a5283d59c0aa01514699db46c06d5b): 宣言順と最初の不足、数量未提供時の早期拒否を保持する
- [秘匿分類の導入](https://github.com/Motifman/llm-rpg/commit/85c3551ebff84fa1c5ccfc0818e5d3cdbeb8361b): 自由状態だけでなく対象者の所持品も初めから秘匿と宣言している
- [場所条件の導入](https://github.com/Motifman/llm-rpg/commit/c3ff38680cfd9360a98ef014b5c0c623159f8863): 現在地・実効照明が未提供なら拒否し、宣言した条件を有効にする
- [欲求とHP条件の導入](https://github.com/Motifman/llm-rpg/commit/b1130730364d556f325f9252f908ca21dc5144a3): 宣言した欲求と比率を読む。空腹や0.5に固定する契約ではない
- [パズルの2入口](https://github.com/Motifman/llm-rpg/commit/b835e13a7da1690040c816bd2987746b48c87842) と設計判断D1607: 入力不足は子例外、誤答は親例外。条件を運んで区別する

## 元の入力・断言の保存

修理では空の旗集合、2品目、空腹70、HP30/100・閾値0.5、HP80/100・閾値0.5をそのまま残し、非空集合・3品目・疲労・別のHP閾値を追加した。全94宣言の既存assertと例外期待が、対応する保持先に残っていることを構文木で照合した。

統合したのは次の2宣言。保持先を追加した時点では旧宣言も残して170件成功を確認し、その後に除いて168件成功を確認した。

- `TestCanInteractStaysCompatible.test_it_still_returns_two_values` → `test_it_agrees_with_the_richer_method`。同じ不成立入力で実際に呼んだ `can_interact` の長さ2・先頭Falseを確認してから、別に呼んだ3要素APIの成否・理由と照合する
- `TestUnknownDefaultsToHiding.test_the_default_is_not_reachable_in_practice` → `TestEveryConditionTypeIsClassified.test_no_condition_type_is_left_undeclared`。全種類が表にある式と、全値が `ConditionVisibility` に属する式を両方移した。未知条件の秘匿既定は別に残す

## 検出力の確認

一時的な製品変更を1つずつ行い、各変更について旧版全163件が通る一方、候補全168件では下表の追加・補強した検証箇所だけが落ちることを確認した。各組の後で製品を復元し、最後に製品1618ファイルのSHA-256が基準と一致することを照合した。型エラー、収集失敗、スキップを検出力の証拠にしていない。

| 一時的な変更 | 候補の意図した失敗数 |
|---|---:|
| OBJECT_STATE_INT_AT_LEASTの欠落理由文を別の文へ置換 | 1 |
| HAS_ITEMSの共通評価を宣言順で先に全件実行 | 1 |
| HAS_ITEM/HAS_ITEMSの欠落理由文を別の文へ置換 | 2 |
| 個数欠落の例外前に共通評価を呼び出す | 2 |
| FLAG_SETの文脈の旗集合を空に置換 | 1 |
| 実行結果のメッセージを二重化 | 1 |
| 対象変更後に返却室内の使う側へ対象更新を混入 | 1 |
| 対象所持の秘匿分類をPUBLICへ置換 | 2 |
| evaluate_preconditions_resultから照明の転送を削除 | 1 |
| evaluate_preconditions_resultから現在地の転送を削除 | 1 |
| need_typeの選択をHUNGER固定へ置換 | 1 |
| BELOWの宣言閾値を0.5へ固定 | 1 |
| AT_LEASTの宣言閾値を0.5へ固定 | 1 |
| 入力不足の子例外だけfailed_conditionをNoneへ置換 | 8 |

統合2件の保持先にも、戻り値3要素化、拒否のTrue化、分類の欠落、不正な分類値の4対照を当てた。移動前の宣言と移動後の保持先が、いずれも狙ったassertで失敗した。

HAS_ITEMSの3件目にも正常な評価結果を用意し、余計な呼出は照会順の断言で検出した。個数未提供の早期拒否も正常な模擬評価結果を用意し、余計な評価は未呼出の断言で検出した。

## 実行結果

| 段階 | 結果 |
|---|---|
| 未編集・主対象 | 163成功 |
| 未編集・関連 | 102成功 |
| 保持先先行・旧宣言も存置 | 170成功 |
| 統合後・主対象 | 168成功 |
| 最終・主対象 | 168成功 |
| 最終・関連 | 102成功 |

Python 3.10.22。資格情報を除去し、試験収集前に通信を遮断する実行器を使用した。各実行で自作業木のsrcを読んだことを確認し、一時変更ごとに専用の出力名とバイトコード領域を使った。対象Ruffと `git diff --check` は成功。全リポジトリの成功は局所試験から推定せず、公開後の正確なheadのCIで別途確認する。

変異集計器がJUnitの任意type属性やAssertionError接頭辞を必須と誤認して停止した。実際の試験はいずれも狙ったassertで失敗しており、集計をmessage・traceの表記差に対応させた。初回だけ新しい出力名で再実行し、その後の有効な旧新対照は再利用した。FLAG_SETとFLAG_NOT_SETの同形文字列も一意性検査で検出し、FLAG_SET節だけへ限定して続行した。両停止時とも製品は復元した。

再実行例: `uv run --frozen pytest` に下表の7ファイルを指定する。関連は親の `test_object_stock_condition_target.py`、削除事前確認・数量・両実体状態、アプリケーションの拒否分類・状態理由・現在手番・引数転送、実行時の拒否配線・目撃方針の計11ファイルを確認した。

## 全94宣言の台帳

Rは保持、Fは既存入力を残す修理、Cは保持先を先行確認した統合。分類は元の宣言に対するもので、新たな表の行を元の監査件数へ上乗せしない。

### tests/domain/world_graph/test_spot_interaction_service.py

| 元の宣言 | 判断 | 保持する契約・判断 |
|---|---|---|
| `TestSpotInteractionService::test_object_state_int_at_least_delegates_and_keeps_failure_contract` | R | 整数state下限は共通核へ一度委譲し、元条件・経路・作者文面を維持する。 |
| `TestSpotInteractionService::test_object_state_int_evaluation_failure_stops_interaction` | R | 整数state共通核の入力不足・未対応を通常の数量不足へ縮退させない。 |
| `TestSpotInteractionService::test_object_state_int_direct_quantity_keeps_legacy_minimum_one` | R | loaderを迂回した0・負の必要数は従来どおり1へ補正して共通核へ渡す。 |
| `TestSpotInteractionService::test_invalid_object_state_int_input_skips_common_evaluator` | F | 欠落入力の拒否文を契約と説明しているが、現断言は成否と未呼出だけ。既存2入力の既定文・条件実体・位置を確認する。 |
| `TestSpotInteractionService::test_object_state_int_reads_explicit_target_object` | R | 明示target_object_idがあれば操作元でなく対象objectのstateを共通核へ渡す。 |
| `TestSpotInteractionService::test_quantity_conditions_delegate_to_shared_predicate_evaluator` | R | 行為者の数量条件は品目別個数と必要数を共通評価核へ渡す。 |
| `TestSpotInteractionService::test_has_items_evaluates_specs_in_declared_order` | F | 最初の不足で止める説明だが不足が最後の2番目で、後続照会を見逃す。旧2品目の行を残し、3番目を持つ行を追加して照会順を同じ2品目に限定する。 |
| `TestSpotInteractionService::test_has_items_keeps_duplicate_specs_as_independent_checks` | R | 重複品目は個数を合算せず、従来どおり同じ必要数を二度判定する。 |
| `TestSpotInteractionService::test_quantity_evaluation_failure_stops_interaction` | R | 数量共通核の入力不足・未対応を通常の所持不足へ縮退させない。 |
| `TestSpotInteractionService::test_invalid_quantity_definition_does_not_call_shared_evaluator` | F | 旧DTOの既定文保持を説明しているが文を確認していない。2種類の元入力と未呼出を残し、対応する理由文・条件実体・位置を確認する。 |
| `TestSpotInteractionService::test_quantity_one_without_counts_uses_owned_spec_fallback` | R | 数量1の両条件は個数mapping省略時も所持品目集合から各1個へ戻す。 |
| `TestSpotInteractionService::test_quantity_above_one_without_counts_fails_before_evaluation` | F | 評価前の停止を説明しているが呼出先を観測していない。既存2条件と例外文を残し、注入した共通評価器が呼ばれないことを確認する。 |
| `TestSpotInteractionService::test_object_state_delegates_and_keeps_failure_contract` | R | OBJECT_STATEは共通核へ委譲し、元条件・経路・作者文面を維持する。 |
| `TestSpotInteractionService::test_object_state_evaluation_failure_stops_interaction` | R | state共通核の入力不足・未対応を通常の操作不可へ縮退させない。 |
| `TestSpotInteractionService::test_scoped_state_evaluation_failure_stops_interaction` | R | item/playerの使う側・使われる側も評価不能を通常falseへ縮退させない。 |
| `TestSpotInteractionService::test_flag_set_delegates_to_shared_predicate_evaluator` | F | 共通評価器は呼出回数しか確認せず、渡す旗名と旗集合の欠落を見逃す。旧空集合を残して非空集合を追加し、FlagSetPredicateと文脈値を明示照合する。 |
| `TestSpotInteractionService::test_flag_set_evaluation_failure_stops_interaction` | R | 共通評価核の入力不足・未対応は、操作不可という通常結果へ縮退させない。 |
| `TestSpotInteractionService::test_execute_open_success` | F | 成功時のメッセージは包含だけで重複を見逃す。元の全断言と入力を残し、メッセージ列全体と入力物体の状態不変を確認する。 |
| `TestSpotInteractionService::test_blank_display_label_falls_back_to_action_name` | R | loaderを迂回した空ラベルでも、結果表示は落ちずaction_nameへ戻る。 |
| `TestSpotInteractionService::test_execute_without_key_raises` | R | 鍵を持たない操作はInteractionNotAllowedExceptionで拒否される。 |
| `TestSpotInteractionService::test_unknown_object_raises` | R | 存在しない物体への実行はUnknownSpotObjectExceptionで拒否される。 |
| `TestSpotInteractionService::test_unknown_action_raises` | R | 既存物体に無い行為はInteractionNotFoundExceptionで拒否される。 |
| `TestSpotInteractionService::test_set_flag_and_connection` | R | スイッチの実行でpower_onと指定通路のOPEN更新指示を返す。 |
| `TestSpotInteractionService::test_change_object_state_can_target_other_object` | F | 対象の状態変更だけを見て、使う側や入力室内まで書き換える誤動作を見逃す。元の対象断言を残し、返却された操作元と入力両物体の不変を確認する。 |
| `TestSpotInteractionService::test_object_state_precondition_reads_the_explicit_target_object` | R | OBJECT_STATE は操作元でなく target_object に宣言した物体の状態を読む。 |

### tests/domain/world_graph/test_failed_precondition_is_carried_out.py

| 元の宣言 | 判断 | 保持する契約・判断 |
|---|---|---|
| `TestEvaluatePreconditionsReportsWhichOneFailed::test_the_failing_condition_is_returned` | R | 落ちた条件が 3 つ目の戻り値として返る。 |
| `TestEvaluatePreconditionsReportsWhichOneFailed::test_the_first_failing_condition_is_returned` | R | 複数の条件があるとき、最初に落ちたものが返る。 |
| `TestEvaluatePreconditionsReportsWhichOneFailed::test_nothing_is_returned_when_all_conditions_pass` | R | すべて通ったときは条件を返さない。 |
| `TestEvaluatePreconditionsResult::test_second_failure_keeps_condition_message_and_path` | R | 2番目で落ちると、条件の実体・文・子番号1を同じ結果へ保持する。 |
| `TestEvaluatePreconditionsResult::test_legacy_tuple_is_an_exact_projection_of_predicate_result` | R | 既存3要素APIは共通結果と成否・文・失敗条件が一致する。 |
| `TestCanInteractStaysCompatible::test_it_still_returns_two_values` | C | 同じ条件・同じ不成立入力による2要素APIの試験。len==2と先頭Falseを相互照合先へ先に移し、理由の一致と共に保持してから重複宣言を除く。 |
| `TestCanInteractStaysCompatible::test_it_agrees_with_the_richer_method` | R | 委譲先と成否・理由が一致する。 |
| `TestTheExceptionCarriesTheCondition::test_the_exception_exposes_the_failed_condition` | R | `InteractionNotAllowedException.failed_condition` に条件が載る。 |
| `TestTheExceptionCarriesTheCondition::test_declared_interaction_exception_exposes_failed_condition` | R | 物体を暗黙対象にしない実行経路でも、落ちた条件を例外へ運ぶ。 |
| `TestTheExceptionCarriesTheCondition::test_a_bare_raise_still_works` | R | 条件を渡さない従来の raise もそのまま動く。 |

### tests/domain/world_graph/test_interaction_condition_visibility.py

| 元の宣言 | 判断 | 保持する契約・判断 |
|---|---|---|
| `TestEveryConditionTypeIsClassified::test_no_condition_type_is_left_undeclared` | R | 宣言漏れの条件が無い。 |
| `TestEveryConditionTypeIsClassified::test_the_map_does_not_name_conditions_that_vanished` | R | 消えた条件が表に残らない。 |
| `TestRoleConditionsAreHidden::test_free_state_conditions_are_hidden` | F | 秘匿表の存在と値型は確認するが対象所持2条件のPUBLIC化を見逃す。元の自由状態2行を残し、TARGET_HAS_ITEM/TARGET_HAS_NO_ITEMの秘匿2行を追加する。 |
| `TestPhysicalConditionsStayVisible::test_they_are_not_hidden` | R | 隠さない。 |
| `TestUnknownDefaultsToHiding::test_an_unmapped_condition_is_treated_as_hidden` | R | 表に無い条件は隠す。 |
| `TestUnknownDefaultsToHiding::test_the_default_is_not_reachable_in_practice` | C | 全種類の登録確認は同ファイルの宣言漏れ試験と同じ。値がConditionVisibilityである確認を先に保持先へ移し、元のall式も残した状態で成功を確認してから重複宣言を除く。 |

### tests/domain/world_graph/test_interaction_place_conditions.py

| 元の宣言 | 判断 | 保持する契約・判断 |
|---|---|---|
| `TestSpotLightingIs::test_matching_lighting_passes` | F | 私有判定を直接呼ぶため、公開前提評価から照明が渡らない誤動作を見逃す。元の直接呼出と断言を残し、同条件をcan_interactへ渡した肯定を確認する。 |
| `TestSpotLightingIs::test_brighter_spot_is_rejected_with_the_authored_message` | R | 明るい場所では拒否し、シナリオが書いた失敗文をそのまま返す。 |
| `TestSpotLightingIs::test_missing_current_lighting_is_rejected` | R | 実効照明が渡っていなければ拒否する。 |
| `TestSpotLightingIs::test_missing_required_lighting_is_rejected` | R | required_lighting を書き忘れた宣言は成立させない。 |
| `TestSpotLightingIsNot::test_different_lighting_passes` | R | required_lighting=PITCH_BLACK で現在 DARK なら成立する。 |
| `TestSpotLightingIsNot::test_same_lighting_is_rejected` | R | 完全な暗闇では拒否する (「暗すぎて手元が見えない」の表現)。 |
| `TestAtSpotIs::test_matching_spot_passes` | F | 私有判定を直接呼ぶため、公開前提評価から現在地が渡らない誤動作を見逃す。元の直接呼出と断言を残し、同条件をcan_interactへ渡した肯定を確認する。 |
| `TestAtSpotIs::test_other_spot_is_rejected` | R | 別のスポットに居れば拒否する。 |
| `TestAtSpotIs::test_missing_current_spot_is_rejected` | R | 現在地が渡っていなければ拒否する (配線漏れを表に出す)。 |
| `TestAtSpotIs::test_missing_required_spot_is_rejected` | R | required_spot を書き忘れた宣言は成立させない。 |
| `TestAtSpotIsNot::test_other_spot_passes` | R | 禁止された場所以外なら成立する (「聖域では争えない」の表現)。 |
| `TestAtSpotIsNot::test_forbidden_spot_is_rejected` | R | 禁止された場所では拒否する。 |
| `TestTargetPlayerStateIs::test_matching_target_state_passes` | R | 対象の state が required_state と全キー一致すれば成立する。 |
| `TestTargetPlayerStateIs::test_different_target_state_is_rejected` | R | 対象の state が違えば拒否する。 |
| `TestTargetPlayerStateIs::test_acting_player_state_is_not_consulted` | R | 行為者の state が一致していても、対象が違えば拒否する。 |
| `TestTargetPlayerStateIs::test_missing_target_status_is_rejected` | R | 対象が渡っていなければ拒否する (物体 interaction に書いた場合)。 |
| `TestEveryConditionTypeHasABranch::test_condition_type_is_not_unhandled` | R | どの条件も「未対応」で落ちない (必要値が欠けた拒否は許容)。 |

### tests/domain/world_graph/test_interaction_time_weather_conditions.py

| 元の宣言 | 判断 | 保持する契約・判断 |
|---|---|---|
| `TestTimeOfDayIsNot::test_morning` | R | 夜以外なら 成立 morning。 |
| `TestTimeOfDayIsNot::test_documented_behavior_2` | R | 夜なら 拒否。 |
| `TestTimeOfDayIsNot::test_provider_2` | R | day_night 宣言が無いシナリオでこの condition を使うと fail する |
| `TestTimeOfDayIsNot::test_required_phase_missing` | R | required phase 欠落で 拒否。 |
| `TestTimeOfDayIs::test_matches_4` | R | 一致なら 成立。 |
| `TestTimeOfDayIs::test_matches_3` | R | 不一致なら 拒否。 |
| `TestWeatherIsNot::test_clear` | R | 嵐以外なら 成立 CLEAR。 |
| `TestWeatherIsNot::test_documented_behavior` | R | 嵐なら 拒否。 |
| `TestWeatherIsNot::test_provider` | R | provider 不在で 拒否。 |
| `TestWeatherIs::test_matches_2` | R | 一致なら 成立。 |
| `TestWeatherIs::test_matches` | R | 不一致なら 拒否。 |
| `TestWeatherCommonPredicateAdapter::test_is_and_is_not_use_one_positive_common_evaluation` | R | 正条件を一度評価し、IS_NOTだけ正常な真偽を反転する。 |
| `TestWeatherCommonPredicateAdapter::test_indeterminate_common_result_never_becomes_allowed` | R | 入力不足・未対応はIS_NOTでも成立へ反転せず即時停止する。 |
| `TestWeatherCommonPredicateAdapter::test_invalid_direct_strings_keep_legacy_comparison` | R | loaderを迂回した未知文字列は従来の完全一致比較を維持する。 |
| `TestWeatherCommonPredicateAdapter::test_precondition_result_keeps_original_condition_path_and_message` | R | 天候不一致は元条件・配列位置・作者文面を失わず構造化結果へ戻す。 |

### tests/domain/world_graph/test_missing_puzzle_input_is_a_distinct_refusal.py

| 元の宣言 | 判断 | 保持する契約・判断 |
|---|---|---|
| `TestMissingPuzzleInput::test_missing_or_blank_code_raises_parameter_missing` | F | 入力不足の子例外は型と文だけを確認し、失敗条件が失われても通る。元の4入力×2入口を残し、例外のfailed_conditionが元条件そのものであることを確認する。 |
| `TestMissingPuzzleInput::test_wrong_code_raises_the_plain_refusal` | R | "code" に違う番号を入れたときは、親の InteractionNotAllowedException をシナリオの文で投げる。 |

### tests/domain/world_graph/test_player_state_preconditions.py

| 元の宣言 | 判断 | 保持する契約・判断 |
|---|---|---|
| `TestPlayerNeedAtLeast::test_passes_when_need_at_or_above_threshold` | F | 肯定がHUNGERだけで、宣言されたneed_typeを無視してHUNGER固定にしても通る。元の空腹70と閾値60を残し、空腹0/疲労70でFATIGUEを選ぶ独立行を追加する。 |
| `TestPlayerNeedAtLeast::test_fails_when_need_below_threshold` | R | HUNGER=30 / threshold=60 → 拒否。 |
| `TestPlayerNeedAtLeast::test_passes_at_exact_threshold` | R | 境界条件: HUNGER==threshold で成立 (>=)。 |
| `TestPlayerNeedAtLeast::test_fails_when_player_status_not_provided` | R | acting_player_status を渡さない場合、silent pass を避けるため拒否。 |
| `TestPlayerNeedAtLeast::test_invalid_need_type_string_rejected` | R | need_type が NeedType に存在しない名前なら拒否。 |
| `TestPlayerNeedAtLeast::test_missing_need_type_or_threshold_rejected` | R | need_type または need_threshold が欠けていれば拒否。 |
| `TestPlayerHpRatioBelow::test_passes_when_hp_low` | F | 非退化入力の閾値が全て0.5で、hp_ratioを無視して半分固定にしても通る。元の30/100・0.5を残し、60/100・0.75の肯定を追加する。 |
| `TestPlayerHpRatioBelow::test_fails_when_hp_high` | R | HP 80/100 (=0.8), hp_ratio=0.5 → 拒否。 |
| `TestPlayerHpRatioBelow::test_fails_at_exact_ratio_below` | R | 境界条件: 充足率 == hp_ratio は BELOW では拒否 (strict <)。 |
| `TestPlayerHpRatioBelow::test_fails_when_status_missing` | R | acting_player_status を渡さなければ拒否。 |
| `TestPlayerHpRatioAtLeast::test_passes_when_hp_high` | F | AT_LEASTの非退化入力も閾値0.5だけ。元の80/100・0.5を残し、30/100・0.25の肯定を追加する。 |
| `TestPlayerHpRatioAtLeast::test_passes_at_exact_ratio_at_least` | R | 境界条件: 充足率 == hp_ratio は AT_LEAST では成立 (>=)。 |
| `TestPlayerHpRatioAtLeast::test_fails_when_hp_low` | R | HP 20/100, hp_ratio=0.5 → 拒否。 |
| `TestZeroMaxHpEdge::test_below_rejects_when_max_hp_zero` | R | max_hp=0 の player では PLAYER_HP_RATIO_BELOW が常に拒否される。 |
| `TestZeroMaxHpEdge::test_at_least_rejects_when_max_hp_zero` | R | max_hp=0 では PLAYER_HP_RATIO_AT_LEAST も拒否される (silent True 防止)。 |
| `TestScenarioLoaderValidation::test_invalid_need_type_rejected_at_load` | R | 未知の need_type 文字列は ScenarioLoadError で拒否 (silent runtime 失敗を回避)。 |
| `TestScenarioLoaderValidation::test_hp_ratio_out_of_range_rejected_at_load` | R | hp_ratio が 0.0..1.0 の範囲外なら ScenarioLoadError で拒否。 |
| `TestScenarioLoaderValidation::test_hp_ratio_non_numeric_rejected` | R | hp_ratio が数値でなければ拒否。 |
| `TestScenarioLoaderParsesPlayerFields::test_loader_propagates_player_need_fields` | R | JSON の need_type/need_threshold が InteractionCondition に反映される。 |

