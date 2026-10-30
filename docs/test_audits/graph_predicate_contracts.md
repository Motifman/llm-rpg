# 共通述語の値比較・診断結果・合成条件の試験監査

## 対象と結果

基準は `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。対象5ファイルの全73宣言とパラメータ行を読み、独立した第二読で R67（保持）・F6（契約を保持して検査を修理）・C0（統合）・D0（削除）とした。73宣言をすべて残し、6宣言の検査だけを補強した。

| 対象 | 宣言 | 基準ケース→修理後 | 基準行数→修理後 |
| --- | ---: | ---: | ---: |
| `service/test_scenario_predicate_evaluator.py` | 37→37 | 66→66 | 531→536 |
| `value_object/test_predicate_result.py` | 12→12 | 16→23 | 156→178 |
| `value_object/test_scenario_event_condition.py` | 10→10 | 10→10 | 91→97 |
| `value_object/test_scenario_predicate.py` | 9→9 | 28→28 | 97→97 |
| `value_object/test_scenario_predicate_usage.py` | 5→5 | 5→5 | 110→110 |
| 計（`tests/domain/world_graph/` 配下） | 73→73 | 125→132 | 985→1018 |

試験は追加52・削除19の33行増。廃止ファイル、製品変更、共有準備の変更、試験専用入口の追加・削除は0。削減数や高速化を目的にせず、元の入力と保証を残したまま見逃しを減らす。

## 修理した6宣言

1. 配置の防御コピーは件数1だけでなく、元のEntityIdとSpotIdの対応そのものを確認する。元mappingへの追加と不正な整数キーの拒否は残した。元の宣言が確認していなかった「不正な値型の拒否」まで保証したように読める説明は直した。この修理は局所的な主張の補強であり、配置値の破壊を既存の他宣言が検出できないとは主張しない
2. 複数stateの一致には、元の全一致・余分な現在値・単独不一致に加え、一方だけ一致する2例を追加した。先頭phaseが一致して後方の入れ子が違う例もあり、先頭だけを比べる誤実装を検出する
3. 要求stateと現在stateの入れ子コピーを、それぞれ独立した元の値と照合する。元入力へ2と3を追記する操作と評価成立の確認を残し、空の要求に縮めて偶然成立する抜けを防ぐ
4. 成功結果への失敗詳細混入は、元の複数詳細に加え、理由、失敗文、述語、非空経路、不足文脈名の単独5例を追加した。値自体の型検査を通る入力を使い、別ガードによる拒否で成功結果との矛盾を見逃さない。空経路だけを持つ成功結果の既存宣言も独立に残した
5. 失敗結果の述語と経路は、元の両方欠落に加え、片方ずつの欠落を拒否する。空経路 `()` は有効な根の位置であり、経路欠落 `None` と区別する
6. 合成条件の集合自己比較を、別々に構築した等値条件木の等値・同hash・辞書キー交換可能性へ直した。異なる条件のhash値が異なることや、全種類の条件がhash可能なことは要求していない

## 残す層と構造監査

共通評価核は解決済みの値の比較と、通常未成立・文脈不足・未対応の区別を所有する。以下の用途側は、対象選択・旧入力変換・合成・文面・評価不能時の出口を所有する。模擬した共通評価器の結果を使う用途側試験は、核自体の値比較や不正入力拒否の代わりにはならない。

- `ScenarioConditionEvaluator`: 世界全体と指定player、旧DTOへの戻し、失敗経路、三値のNOT/AND/OR、確率の短絡
- `SpotInteractionService`: 操作元と明示対象、object/item/player、数量補正、作者文、宣言順
- `GameEndConditionEvaluator`: 明示player集合のANY/ALL、非player除外、空集合、勝敗文
- `SpotGraphNavigationService`: 公開 `can_pass` の通行条件と用途文
- `SpotExplorationService`: 公開 `explore` の発見更新と既発見の保持
- `SpotGraphMonsterSpawnStageService`: 必須/禁止フラグ、天候候補のOR、未知値互換、評価不能を反転しない出口

これらの利用側試験を関連確認として実行したが、今回の73宣言の監査済み件数へは加えていない。型拒否、空値と未配線、既存の負閾値・bool現在値・None比較、初期値、合成条件の構築制約も、それぞれ独立した契約として残した。

[設計判断86](../design_decisions.md#86-共通述語基盤は決定的な葉と用途表を完成境界とする) は、述語型・文脈型・実行時一覧・評価分岐・用途表の双方向照合を明示している。`test_scenario_predicate_usage.py` の5宣言と監査用一覧・用途表を保持した。ASTから分岐を拾う試験には局所引数名への依存があるが、現在の9種類の意味試験だけでは新規型の未登録、廃止分岐の残存、用途誤分類をすべて代替できない。実行時の呼出がないという理由だけで、この設計上の監査契約を削除しない。

## 故意変更による旧新対照

同じ製品変更を元と修理後の作業場所に一時適用し、直列に実行した。毎回元のバイト列へ復元した。次の表は、特記した1行を除き、担当5ファイル全体（旧125件・新132件）の結果である。

| 故意変更 | 旧 | 新 | 直接の検出点 |
| --- | --- | --- | --- |
| 空要求の真を保ち、非空の一部一致を許す | 全成功 | 1失敗 | 複数stateの一部不一致 |
| 先頭の要求だけを比較する | 全成功 | 1失敗 | phase一致・後方入れ子不一致 |
| 要求snapshotから入れ子mappingを捨てる | 全成功 | 2失敗 | 部分一致の拒否と要求snapshotの元値 |
| 成功時の理由コード拒否を外す | 全成功 | 1失敗 | 理由だけの混入 |
| 成功時の失敗文拒否を外す | 全成功 | 1失敗 | 正常型の文だけの混入 |
| 成功時の失敗述語拒否を外す | 全成功 | 1失敗 | 述語だけの混入 |
| 成功時の不足文脈拒否を外す | 全成功 | 1失敗 | 入力名だけの混入 |
| 失敗時の述語必須検査を外す | 全成功 | 1失敗 | 有効な根経路があるが述語なし |
| 失敗時の経路必須検査を外す | 全成功 | 1失敗 | 述語があるが経路なし |
| 条件木のhashを物体の同一性由来へ変える | 全成功 | 1失敗 | 等値な別条件木の同hash |
| 配置コピーの全SpotIdを99へ置き換える（対象1宣言のみ） | 1成功 | 1失敗 | 件数だけでなく元の対応を照合 |
| 要求stateを浅いコピーへ変える | 1失敗 | 1失敗 | 既存の入れ子切り離しを保持 |
| 現在stateを浅いコピーへ変える | 1失敗 | 1失敗 | 既存の入れ子切り離しを保持 |
| 条件木のhashを定数1へ変える | 全成功 | 全成功 | hashの衝突自体は禁止しない |
| 整数state評価の局所変数名だけを変える | 全成功 | 全成功 | 識別子だけの変更で壊れない |

新しく全体で検出できたものは10種、局所宣言の検査を強くした対照は1種、元から検出していた退行の保持は2種、契約を変えない対照は2種。15種×旧新の30実行を行い、反復件数を網羅件数へ加算していない。失敗は狙ったassertionまたは期待例外の不発で、収集エラーや別ガードの失敗を代用していない。

単純な `all`→`any` は既存の空要求試験が検出する。上表は空要求を真のまま保つ誤変更であり、単純置換を新規検出として数えていない。配置の値置換は対象1宣言だけの対照であり、旧5ファイル全体が通ったという意味ではない。

## 検証結果と限界

Python 3.10.22 / pytest 8.4.1。資格情報を除去し通信を遮断する実行器で、各回の読み込み元が指定した作業場所の `src` であることを確認した。外部モデルの取得を停止し、通常のquality/live_api除外を維持した。有料LLM・外部API・ネットワーク試験は実施していない。

- 未編集基準: 担当125件、関連209件が成功
- 修理後の担当: 132件が成功
- 故意変更: 30実行すべて期待した旧新結果。各回の製品復元をバイト単位で確認
- 復元後の最終: 担当132＋関連209＝341件が成功、失敗・エラー・skipなし
- 製品1601ファイルは基準と一致。製品・試験の追跡3176ファイルのうち差分があるのは修理した3試験だけ
- Ruff 0.16.8の対象3ファイルと `git diff --check` が成功。書式全体の変更はしていない

関連209件の対象は次の7ファイル。

- `tests/application/world_graph/test_scenario_condition_predicate_result.py`
- `tests/domain/world_graph/test_game_end_condition_evaluator.py`
- `tests/domain/world_graph/test_spot_interaction_service.py`
- `tests/domain/world_graph/test_interaction_time_weather_conditions.py`
- `tests/domain/world_graph/test_spot_graph_navigation_service.py`
- `tests/domain/world_graph/test_spot_exploration_service.py`
- `tests/application/world_graph/test_spot_graph_monster_spawn_stage_service.py`

全リポジトリ試験、性能比較、SQLiteやsnapshot形式の変更は行っていない。基準で製品不具合は再現していない。製品修正・Issue作成はこの監査に含めない。

## 履歴と並行変更

- [結果の構造化](https://github.com/Motifman/llm-rpg/commit/0af42cefb47ae97bb48e38540e0ae4cd333080f8): 通常未成立・文脈不足・未対応を同じFalseへ潰さず運ぶ
- [合成条件のtuple検証とhash保証](https://github.com/Motifman/llm-rpg/commit/43547182958396553e4dafba130e15a69bab7032): 構築時の子制約を守り、空AND/ORの意味を評価側へ残す
- [場所条件の対象分離](https://github.com/Motifman/llm-rpg/commit/e6daaad8928ec07e465e61cff6d29c2458f30342): 通常entity、本人、明示player集合の対象範囲を混ぜない
- [状態一致の共通化](https://github.com/Motifman/llm-rpg/commit/e9c05edaed535c9489fb19af311caeefa91cbba4): 比較だけを共通化し、対象選択と失敗文を用途側へ残す
- [共通述語基盤の完成境界](https://github.com/Motifman/llm-rpg/commit/52b8c188b8a02989643f5fadfecbbf2b494ba303): 型・評価分岐・用途表の構造監査を維持する

2026-10-14 10:17 UTCにmainと未統合PR74件のhead・変更パスを確認し、担当5試験と6製品所有者への直接衝突は0だった。[備蓄再生 #1684](https://github.com/Motifman/llm-rpg/pull/1684) は再生・端数、[明示対象 #1688](https://github.com/Motifman/llm-rpg/pull/1688) はobject選択の責任を持つ。共通核は解決済み値を読むため、この2件の本体・保持試験を変更せず、未統合の修正を上書きしていない。[経路 #1737](https://github.com/Motifman/llm-rpg/pull/1737) と [表示 #1739](https://github.com/Motifman/llm-rpg/pull/1739) も別の契約を扱う。

## 全73宣言の判断

以下は基準時点の宣言名と行。Rはそのまま保持、Fは同じ宣言を補強した。保持先は各元宣言で、契約の別ファイルへの移管はない。

### `tests/domain/world_graph/service/test_scenario_predicate_evaluator.py`

| 基準宣言（行） | 判定 | 保護する契約 |
| --- | --- | --- |
| `TestScenarioPredicateEvaluatorFlagSet.test_matches_only_exactly_named_flag` (45) | R | 同名フラグが集合にあれば成立し、大文字小文字違いでは成立しない。 |
| `TestScenarioPredicateEvaluatorFlagSet.test_empty_set_is_normal_unsatisfied` (53) | R | 空集合は配線済みの正当な状態なので、文脈不足でなく通常未成立とする。 |
| `TestScenarioPredicateEvaluatorFlagSet.test_missing_flag_set_is_context_missing` (63) | R | 世界フラグ集合が未配線なら、通常未成立と区別して必要文脈名を返す。 |
| `TestScenarioPredicateEvaluatorFlagSet.test_context_rejects_mutable_or_invalid_flag_collections` (74) | R | 可変集合や不正な要素を受け入れず、評価中の意味変化を防ぐ。 |
| `TestScenarioPredicateEvaluatorTickAtLeast.test_matches_at_or_after_threshold` (89) | R | 現在tickが閾値と等しい時点から成立し、それより前は成立しない。 |
| `TestScenarioPredicateEvaluatorTickAtLeast.test_missing_current_tick_is_context_missing` (100) | R | 現在tick未配線は通常未成立でなく、必要な文脈名を返す。 |
| `TestScenarioPredicateEvaluatorTickAtLeast.test_wrong_context_kind_is_context_missing` (110) | R | 別用途の文脈を渡しても属性エラーにせず、current_tick不足を返す。 |
| `TestScenarioPredicateEvaluatorTickAtLeast.test_context_rejects_non_world_tick` (121) | R | WorldTick以外を現在値として受け入れず、型の取り違えを早期発見する。 |
| `TestScenarioPredicateEvaluatorLocation.test_entity_at_spot_distinguishes_match_other_and_unplaced` (130) | R | 本人は一致時だけ成立し、別spotと未配置は通常不成立とする。 |
| `TestScenarioPredicateEvaluatorLocation.test_entity_count_matches_at_threshold` (153) | R | 同じspotの通常entity数が閾値以上のときだけ成立する。 |
| `TestScenarioPredicateEvaluatorLocation.test_location_predicates_distinguish_empty_and_missing_context` (179) | R | 空配置は通常未成立、未配線と異種contextは文脈不足として返す。 |
| `TestScenarioPredicateEvaluatorLocation.test_context_copies_and_validates_entity_locations` (198) | F | 配置mappingの元の対応を防御コピーし、不正な整数キーを拒否する |
| `TestScenarioPredicateEvaluatorItemOwnership.test_matches_only_owned_item_spec` (212) | R | 指定品目が解決済み所持集合に含まれるときだけ成立する。 |
| `TestScenarioPredicateEvaluatorItemOwnership.test_empty_set_is_normal_unsatisfied` (224) | R | 空集合は所持情報が配線済みなので、通常未成立として返す。 |
| `TestScenarioPredicateEvaluatorItemOwnership.test_missing_or_wrong_context_reports_owned_item_specs` (234) | R | 所持集合の未配線と異種文脈は、必要な文脈名つきで返す。 |
| `TestScenarioPredicateEvaluatorItemOwnership.test_context_rejects_mutable_or_untyped_collections` (253) | R | 可変集合とItemSpecId以外の要素を拒否し、評価中の意味変化を防ぐ。 |
| `TestScenarioPredicateEvaluatorItemSpecCount.test_matches_at_or_above_required_count` (268) | R | 品目の個数が必要数と等しい時点から成立し、それ未満では成立しない。 |
| `TestScenarioPredicateEvaluatorItemSpecCount.test_empty_counts_are_unsatisfied_but_missing_counts_are_context_missing` (283) | R | 空mappingは既知の0個、Noneと異種文脈はitem_spec_counts不足とする。 |
| `TestScenarioPredicateEvaluatorItemSpecCount.test_predicate_rejects_invalid_required_count` (299) | R | 必要数はboolを除く正整数だけを受け入れ、不正定義を構築時に拒否する。 |
| `TestScenarioPredicateEvaluatorItemSpecCount.test_predicate_rejects_untyped_item_spec_id` (308) | R | ItemSpecIdでない品目参照を型付き述語の構築時に拒否する。 |
| `TestScenarioPredicateEvaluatorItemSpecCount.test_context_validates_and_copies_counts` (313) | R | 個数mappingを防御コピーし、不正なキー・個数・mapping型を拒否する。 |
| `TestScenarioPredicateEvaluatorStateValues.test_matches_required_entries_and_ignores_extra_state` (336) | F | 全要求値が一致すれば余分な現在値があっても成立し、1件違えば不成立になる。 |
| `TestScenarioPredicateEvaluatorStateValues.test_missing_key_matches_expected_none_like_legacy_dict_get` (354) | R | 要求値Noneは現在キーの欠落とも一致する既存のdict.get比較を維持する。 |
| `TestScenarioPredicateEvaluatorStateValues.test_empty_requirement_matches_known_empty_state` (363) | R | 空の要求mappingは、stateが配線済みなら空虚真として成立する。 |
| `TestScenarioPredicateEvaluatorStateValues.test_missing_or_wrong_context_reports_state_values` (372) | R | state未配線と異種文脈は通常不成立でなく必要文脈名を返す。 |
| `TestScenarioPredicateEvaluatorStateValues.test_predicate_and_context_deep_copy_nested_values` (385) | F | 構築後に元mappingの入れ子を変更しても述語と文脈の意味は変わらない。 |
| `TestScenarioPredicateEvaluatorStateValues.test_rejects_non_mapping_and_non_string_keys` (396) | R | mapping以外と文字列でないstateキーを型付き入口で拒否する。 |
| `TestScenarioPredicateEvaluatorStateIntAtLeast.test_matches_at_or_above_threshold` (411) | R | 現在値が閾値と等しい時点から成立し、それ未満では成立しない。 |
| `TestScenarioPredicateEvaluatorStateIntAtLeast.test_missing_or_non_int_state_is_zero` (423) | R | キー欠落と整数以外の現在値は、文脈不足でなく既知の0として比較する。 |
| `TestScenarioPredicateEvaluatorStateIntAtLeast.test_zero_negative_threshold_and_bool_state_keep_legacy_integer_semantics` (435) | R | 0・負閾値を許し、bool現在値も従来どおりPython整数として比較する。 |
| `TestScenarioPredicateEvaluatorStateIntAtLeast.test_missing_or_wrong_context_reports_state_values` (454) | R | state未配線と異種文脈は通常不成立でなく必要文脈名を返す。 |
| `TestScenarioPredicateEvaluatorStateIntAtLeast.test_predicate_rejects_invalid_state_key` (468) | R | state_keyは空でない文字列だけを受け入れる。 |
| `TestScenarioPredicateEvaluatorStateIntAtLeast.test_predicate_rejects_non_integer_threshold` (474) | R | 閾値はboolを除く整数だけを受け入れる。 |
| `TestScenarioPredicateEvaluatorWeatherType.test_matches_only_the_required_weather` (492) | R | 現在天候と要求天候が同じ列挙値のときだけ成立する。 |
| `TestScenarioPredicateEvaluatorWeatherType.test_missing_or_wrong_context_names_current_weather` (510) | R | 現在天候の未配線と異種文脈は通常不一致でなく文脈不足にする。 |
| `TestScenarioPredicateEvaluatorWeatherType.test_predicate_rejects_non_enum_weather` (523) | R | 要求天候へ文字列を直接渡すとドメイン検証例外で拒否する。 |
| `TestScenarioPredicateEvaluatorWeatherType.test_context_rejects_non_enum_weather` (528) | R | 現在天候へ文字列を直接渡すと文脈検証例外で拒否する。 |

### `tests/domain/world_graph/value_object/test_predicate_result.py`

| 基準宣言（行） | 判定 | 保護する契約 |
| --- | --- | --- |
| `TestPredicateResultFactories.test_satisfied_result_has_no_failure_information` (19) | R | 成立結果には理由・失敗述語・経路・不足文脈を持たせない。 |
| `TestPredicateResultFactories.test_not_satisfied_result_identifies_predicate_and_path` (30) | R | 通常の未成立は、落ちた述語と根からの子番号を保持する。 |
| `TestPredicateResultFactories.test_missing_context_result_names_required_inputs` (47) | R | 文脈不足は通常の未成立と別の理由コードと入力名を持つ。 |
| `TestPredicateResultFactories.test_unsupported_result_is_distinct_from_world_state_mismatch` (60) | R | 未対応の述語は、世界状態が合わない通常未成立と区別する。 |
| `TestPredicateResultInvariants.test_satisfied_result_rejects_failure_details` (75) | F | 成立なのに失敗理由を持つ矛盾した結果は生成できない。 |
| `TestPredicateResultInvariants.test_satisfied_result_rejects_even_an_empty_failure_path` (85) | R | 空tupleも根を指す経路なので、成立結果へ混入できない。 |
| `TestPredicateResultInvariants.test_failed_result_requires_predicate_and_path` (90) | F | 未成立結果は、どこで落ちたかを必ず機械的に特定できる。 |
| `TestPredicateResultInvariants.test_missing_context_requires_at_least_one_input_name` (98) | R | 文脈不足を名乗りながら不足項目が空の結果は拒否する。 |
| `TestPredicateResultInvariants.test_non_missing_reason_rejects_missing_context_names` (108) | R | 通常未成立へ不足文脈を混ぜ、理由を二重化する状態を拒否する。 |
| `TestPredicateResultInvariants.test_failed_path_rejects_non_tuple_bool_and_negative_index` (120) | R | 失敗経路は非負整数の tuple だけを受理する。 |
| `TestPredicateResultInvariants.test_context_missing_rejects_bare_string_before_conversion` (131) | R | 文脈名の文字列を一文字ずつの集合へ静かに変換しない。 |
| `TestPredicateResultInvariants.test_direct_construction_rejects_invalid_context_name_collection` (144) | R | 不足文脈は空でない文字列だけを持つ frozenset に限定する。 |

### `tests/domain/world_graph/value_object/test_scenario_event_condition.py`

| 基準宣言（行） | 判定 | 保護する契約 |
| --- | --- | --- |
| `TestNotCondition.test_not_with_single_child_is_valid` (16) | R | NOT に子条件 1 個を渡せば構築できる。 |
| `TestNotCondition.test_not_with_zero_children_rejected` (23) | R | NOT に子条件 0 個ならバリデーション例外。 |
| `TestNotCondition.test_not_with_multiple_children_rejected` (28) | R | NOT に子条件 2 個以上はバリデーション例外。 |
| `TestAndOrCondition.test_and_with_no_children_is_valid` (39) | R | AND は children 空でも構築可（vacuous truth は評価器側で扱う）。 |
| `TestAndOrCondition.test_or_with_no_children_is_valid` (45) | R | OR は children 空でも構築可（評価時は False）。 |
| `TestAndOrCondition.test_and_can_nest_arbitrary_depth` (50) | R | AND の中に NOT、その中に leaf という入れ子が許容される。 |
| `TestChildrenTupleInvariant.test_list_children_rejected` (62) | R | children に list を渡すと ValidationException を投げる。 |
| `TestChildrenTupleInvariant.test_tuple_children_is_hashable` (68) | F | 独立に構築した等値な条件木は同じhashで、辞書キーとして交換可能 |
| `TestLeafCondition.test_leaf_with_children_rejected` (79) | R | leaf 条件（FLAG_SET 等）に children を持たせるとバリデーション例外。 |
| `TestLeafCondition.test_leaf_without_children_is_valid` (87) | R | 普通の leaf は children 無しで構築できて is_composite=False。 |

### `tests/domain/world_graph/value_object/test_scenario_predicate.py`

| 基準宣言（行） | 判定 | 保護する契約 |
| --- | --- | --- |
| `TestFlagSetPredicate.test_rejects_missing_empty_or_non_string_name` (24) | R | 空・空白のみ・文字列以外のフラグ名は定義時に拒否する。 |
| `TestFlagSetPredicate.test_preserves_exact_name_without_normalization` (29) | R | 大文字小文字や前後空白を勝手に変えず、完全一致用の名前を保持する。 |
| `TestTickAtLeastPredicate.test_rejects_non_integer_threshold` (40) | R | boolを含む整数以外の閾値は、型付き述語の構築時に拒否する。 |
| `TestTickAtLeastPredicate.test_preserves_integer_threshold` (46) | R | 入力厳格化を別PRへ分けるため、既存が受理する負数を含む整数を保持する。 |
| `TestLocationPredicates.test_entity_at_spot_rejects_untyped_ids` (58) | R | 本人位置の述語はEntityIdとSpotId以外を構築時に拒否する。 |
| `TestLocationPredicates.test_entity_count_rejects_non_positive_or_non_integer_threshold` (66) | R | 在席数の閾値はboolを除く正整数だけを受理する。 |
| `TestLocationPredicates.test_location_predicates_preserve_typed_values` (75) | R | 正しいIDと人数を正規化せず、そのまま保持する。 |
| `TestItemSpecOwnedPredicate.test_rejects_untyped_item_spec_id` (88) | R | ItemSpecId以外を受け入れず、整数IDとの取り違えを構築時に拒否する。 |
| `TestItemSpecOwnedPredicate.test_preserves_typed_item_spec_id` (93) | R | 正しいItemSpecIdを正規化せず、そのまま保持する。 |

### `tests/domain/world_graph/value_object/test_scenario_predicate_usage.py`

| 基準宣言（行） | 判定 | 保護する契約 |
| --- | --- | --- |
| `TestScenarioPredicateStructuralCoverage.test_type_alias_and_runtime_types_match` (62) | R | 型aliasへ追加した述語は実行時型一覧にも過不足なく現れる。 |
| `TestScenarioPredicateStructuralCoverage.test_every_predicate_has_an_evaluator_branch` (66) | R | 全共通述語に評価分岐があり、廃止型の分岐も残っていない。 |
| `TestScenarioPredicateStructuralCoverage.test_context_alias_and_runtime_types_match` (72) | R | 評価文脈の型aliasと実行時型一覧を双方向に一致させる。 |
| `TestScenarioPredicateStructuralCoverage.test_every_predicate_is_classified_by_usage` (76) | R | 全共通述語を少なくとも一つの実利用用途へ分類する。 |
| `TestScenarioPredicateStructuralCoverage.test_usage_matrix_records_only_migrated_meanings` (86) | R | 名前が似るだけの用途へ共通述語を誤って許可しない。 |
