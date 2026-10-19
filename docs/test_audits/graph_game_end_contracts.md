# 終了条件と個人・陣営結果の試験責任

## 結果

- 基準main: `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。9試験、元81宣言を全読し、R69/F7/C5/D0と判断した
- 最終76宣言。担当試験1622→1596行、追加65・削除91行。製品・共通準備の変更0、廃止ファイル0
- 未編集基準は担当106件＋関連71件成功。保持先を先に補い、統合元を残した状態で109件成功。統合後・全復元後は担当102件＋関連71件＝173件成功
- 故意変更14種類・旧新30実行。担当全体で旧成功→新失敗6種類、正の宣言1件に限定した補強1種類、統合の保存6種類、意味維持の改名1種類
- 旧新それぞれの製品1601ファイルは基準と一致。各故意変更を元のバイト列へ復元し、最終実行のソース位置も確認した
- Ruff 0.16.8で変更5試験と`git diff --check`が成功。全リポジトリ試験、有料LLM、ネットワーク試験、性能比較は行っていない

## 責任を分ける理由

条件が成立するかは`GameEndConditionEvaluator`、成立がWIN/LOSE/中立のどれかは呼び手が決める。型で勝敗を固定すると、インポスターを追放したクルーが敗北になる不具合が戻る。`WorldRuntime`は外的停止、チームwin、通常win、lose、中立endの順に評価する。

`GameEndCondition`は必須値と成立不能な宣言を拒否し、シナリオ読み込みはJSONの型・置き場所・診断を担当する。構築試験と読み込み試験を同一視しない。`ScenarioTeam`は勝者0/1/複数をLOSE/WIN/DRAWへ写し、`PlayerOutcomeRule`は発火機会と対象者条件を別の値として保持する。

設計判断26・43・58・71・72・73・D1516・D1618を確認した。共通比較核、用途側の対象集合と集約、個人結果規則の発火・確定、世界時計の接続は異なる責任である。単純な構築、既定値、未知型の構造検査、模擬評価器という形だけで削除しない。

### 保持する別の入口

- 共通述語の真理値は`tests/domain/world_graph/service/test_scenario_predicate_evaluator.py`。用途側の空集合拒否、明示player全員の評価、ANY/ALL、理由文、異常時の例外は本監査の評価器試験へ残す
- JSONの必須値表・未知型の網羅は`tests/infrastructure/scenario/test_scenario_loader.py::TestGameEndConditionScenarioData`。過去の検証漏れを防ぐ構造契約として残す
- 実際のdownは`tests/demos/test_faction_elimination_e2e.py::TestDownedCrewDoesNotEndTheRun::test_all_crew_down_but_alive_keeps_going`。HP0と`is_down`を確認しており、純粋評価器へUNRESOLVEDを渡すだけの試験とは異なる
- チームの同時成立は値オブジェクト試験の2DRAW/1LOSE、実runtime接続は`tests/integration/test_team_outcomes.py`。チームwinと`lift_departed`のendが同時に成立しても勝利を保ち、両チーム脱出ならDRAWになる
- 外的停止は`tests/integration/test_world_runtime_end_on_all_down.py`。通常設定、全員down、確定者、行動可能者、永続世界、空対象を区別する
- 失敗tickの時計同期は`tests/application/world_runtime/test_failed_world_tick_accounting.py::test_failed_tick_updates_runtime_clock_and_tick_limit`。後段失敗でも消費したtick50を終了判定へ反映する
- 移動後・猶予前と手番後の個人結果判定は`tests/integration/test_player_outcome_judged_in_the_tick_of_the_turn.py`と`tests/application/world_graph/test_player_outcome_rule_after_turns_and_death_grace.py`
- 規則無しの世界は`tests/integration/test_persistent_world.py`。`PlayerOutcomeRule`の発火・適格・一度限り進捗は`tests/application/world_graph/test_player_outcome_rule_stage.py`

## 修理と統合

7宣言の元入力を残し、閾値1で2人を1人へ丸める誤計数、空旗の別ガードによる見逃し、読み込み後の条件型、読み込み時の例外型と理由、ANY/ALLの混合集約、非整数tick比較の成立側を検査した。

5宣言は保持先を先に補ってから統合した。全滅結果のLOSEは全員DEADの試験へ、全員UNRESOLVEDの重複は全員生存の試験へ、DEAD/EJECTEDの同一入力は比較人数の主試験へ移した。場所2行とtick欠落1行は`TestConditionRequiredFields.test_missing_required_field_is_rejected`へ集約した。元の場所固有の理由文も残す。

R69のうち67宣言は説明文を除く実行構文木が不変。残り2宣言は統合保持先としてLOSEのassertまたはtick欠落行を受け入れた。場所構築の正常系はクラス名だけ変更し、本体は維持した。

## 全81宣言の台帳

Rは保持、Fは契約を残した検査修理、Cは保持先へ統合、Dは削除。宣言はパラメーター行数と別に数える。関連試験を81宣言へ足していない。

### `tests/domain/world_graph/test_all_members_have_outcome.py`

| 判定 | 元の宣言 | 契約・保存先 |
|---|---|---|
| R | `test_missing_outcome_is_rejected` | required_outcome を書かないと GameEndConditionValidationException を投げる。 |
| R | `test_unresolved_outcome_is_rejected` | required_outcome に UNRESOLVED を書くと GameEndConditionValidationException を投げる。開始した瞬間に成立してしまうため。 |
| R | `test_satisfied_when_every_member_has_the_outcome` | 北の 2 人が RESCUED なら、南が UNRESOLVED のままでも成立する。 |
| R | `test_not_satisfied_when_one_member_is_left_behind` | 北の 1 人だけが RESCUED で、もう 1 人が UNRESOLVED なら成立しない。 |
| R | `test_other_teams_outcomes_do_not_count` | 南の 2 人が RESCUED でも、北の誰も RESCUED でなければ北の条件は成立しない。 |
| R | `test_missing_team_member_ids_raises` | team_member_ids を渡さずに評価すると GameEndConditionValidationException を投げる。黙って未成立にすると勝敗が永久に決まらないため。 |
| R | `test_empty_team_is_never_satisfied` | team_member_ids が空なら成立しない。空集合の全員を成立とみなさない。 |
| R | `test_missing_player_outcomes_raises` | player_outcomes を渡さずに評価すると GameEndConditionValidationException を投げる。 |
| R | `test_member_missing_from_outcomes_counts_as_not_reached` | outcome の表に北の 1 人の行が無ければ、その人は RESCUED ではないとして成立しない。 |

### `tests/domain/world_graph/test_faction_elimination_end_condition.py`

| 判定 | 元の宣言 | 契約・保存先 |
|---|---|---|
| R | `test_not_ended_while_the_faction_survives` | crew が 2 人生きている間は成立しない。 |
| R | `test_not_ended_with_one_left` | crew が 1 人でも残っていれば成立しない (max_surviving=0)。 |
| R | `test_ended_when_the_whole_faction_is_dead` | crew が全員 DEAD になったら成立する。 |
| C | `test_result_is_lose` | keeperにresult==LOSEを先に加える。型に固定したLOSEという古い説明は、呼び手が渡したLOSEという現行契約へ直す |
| R | `test_other_factions_do_not_count` | 条件に指定していない役割の生死は影響しない。 |
| F | `test_threshold_above_zero` | 元の残り1人/閾値1を保ち、2人/閾値1の不成立を同じ宣言に足す |
| C | `test_downed_but_not_dead_keeps_the_game_going` | 同じ全員UNRESOLVED入力をkeeperに保存。実downはtests/demos/test_faction_elimination_e2e.py::TestDownedCrewDoesNotEndTheRun::test_all_crew_down_but_alive_keeps_goingがHP0とis_downを明示して保証 |
| R | `test_rescued_players_are_not_counted_as_dead` | RESCUED は退場扱いせず生存として数える。 |
| R | `test_missing_states_raises` | player_states が渡っていなければ例外にする。 |
| R | `test_missing_outcomes_raises` | player_outcomes が渡っていなければ例外にする。 |
| R | `test_missing_required_state_is_rejected` | required_state が無いと、誰を数えるか決まらない。 |
| R | `test_missing_max_surviving_is_rejected` | max_surviving が無いと閾値が決まらない。 |
| R | `test_negative_threshold_is_rejected` | 負の閾値は成立しえないので弾く。 |
| R | `test_declaring_both_fails_to_load` | 廃止形式は game_end_conditions の有無にかかわらず拒否する。 |

### `tests/domain/world_graph/test_flags_set_at_least_condition.py`

| 判定 | 元の宣言 | 契約・保存先 |
|---|---|---|
| R | `test_not_met_below_the_threshold` | 2 個では成立しない (閾値は 3)。 |
| R | `test_met_at_the_threshold` | ちょうど 3 個で成立する。 |
| R | `test_met_above_the_threshold` | 4 個でも成立する。 |
| R | `test_unrelated_flags_do_not_count` | 関係の無いフラグは進捗にならない。 |
| R | `test_a_mix_counts_only_the_declared_ones` | 混ざっていても、宣言したぶんだけ数える。 |
| F | `test_empty_flag_list_is_rejected` | 元の空tuple・閾値3を保存し、例外文を「required_flags が必要です」へ限定する。単にrequired_flagsでは後段の個数超過理由にも一致してしまう |
| R | `test_threshold_above_the_list_is_rejected` | 宣言した数より大きい閾値は拒否する。 |
| R | `test_zero_threshold_is_rejected` | 閾値 0 は拒否する。開始した瞬間に成立してしまう。 |
| R | `test_missing_threshold_is_rejected` | 閾値の書き忘れを既定値で埋めない。 |
| R | `test_duplicate_flags_are_rejected` | 同じ作業を二度書いたら拒否する。 |
| F | `test_a_valid_declaration_loads` | 元のJSONと値検査を維持しcondition_typeがFLAGS_SET_AT_LEASTであることを確認 |
| F | `test_an_impossible_threshold_is_rejected_at_load` | 数の整合を持つGameEndConditionValidationExceptionとmin_set_count超過の理由を要求 |
| F | `test_a_missing_threshold_is_rejected_at_load` | 入口のScenarioLoadErrorと整数min_set_count必須の理由を要求 |

### `tests/domain/world_graph/test_game_end_condition_evaluator.py`

| 判定 | 元の宣言 | 契約・保存先 |
|---|---|---|
| R | `test_flag_set_win` | 世界の対象旗が立つと呼び手のWINで終了する |
| R | `test_flag_set_delegates_to_typed_common_evaluator` | 終了条件固有の勝敗・理由文を保ち、FLAG_SETの真偽だけを共通核へ委譲する。 |
| R | `test_flag_set_evaluation_failure_stops_game_end` | 共通評価核の入力不足・未対応は、通常の終了条件不成立へ縮退させない。 |
| R | `test_all_at_spot_win` | 指定された2人全員が対象地に居ると呼び手のWINで終了する |
| R | `test_at_spot_conditions_reject_empty_player_scope` | ANY/ALLとも対象playerが0人なら、空集合を成立扱いせず未達とする。 |
| R | `test_at_spot_conditions_ignore_non_player_entities` | 対象地に非player entityだけが居ても、player集合のANY/ALLは成立しない。 |
| R | `test_all_at_spot_fails_when_one_declared_player_is_unplaced` | 明示playerの一人が未配置なら、残りが集合済みでもALLは未達とする。 |
| R | `test_at_spot_evaluation_failure_stops_game_end` | 場所共通核の入力不足・未対応は、通常の集合条件未達へ縮退させない。 |
| F | `test_at_spot_evaluates_each_declared_player_with_typed_predicate` | 元の2人と真偽列を保存し、ANY=True/ALL=False、結果ラベル、配置文脈を検査。識別子の表と全員評価契約は残す |
| R | `test_any_at_spot_does_not_filter_placed_dead_player_by_outcome` | DEAD outcomeでもgraphに配置された明示playerは、従来どおりANYの対象に含む。 |
| R | `test_tick_limit_lose` | 世界tick10が閾値10へ到達したら呼び手のLOSEで終了する |
| R | `test_tick_limit_delegates_to_typed_common_evaluator` | TICK_LIMITは真偽だけを共通核へ委譲し、既存の勝敗・理由文を保つ。 |
| R | `test_tick_limit_evaluation_failure_stops_game_end` | 共通核の入力不足・未対応は、ティック制限内という通常結果へ縮退させない。 |
| F | `test_tick_limit_keeps_legacy_float_comparison_outside_common_core` | 元のtick10を保存しtick11の成立・呼び手のLOSEを加える。共通核へ渡さないことは保持 |
| R | `test_invalid_flag_set_condition_raises_domain_exception_on_construction` | FLAG_SET に target_flag が無い条件は、評価前の構築時点で拒否される。 |
| C | `test_required_game_end_condition_fields_are_rejected_on_construction` | keeperを必須値拒否の表へ拡張し、場所2行とtick_limit欠落1行の同じ型・例外・フィールド名を先に保持。既存の場所固有メッセージも保存 |
| R | `test_mixed_resolved_outcomes_end_without_collective_result` | RESCUED と STRANDED が混在しても、集団 WIN/LOSE ではなく中立終了にする。 |
| R | `test_one_unresolved_player_keeps_world_running` | 一人でも UNRESOLVED なら個人結果の確定待ちとして終了しない。 |
| R | `test_empty_player_set_does_not_end_persistent_world` | 対象0人を「全員確定」とみなさず、終了条件なしの世界を誤終了させない。 |
| R | `test_missing_outcome_mapping_is_rejected` | 結果表の配線漏れは永久未成立へ縮退させず、評価時に例外にする。 |

### `tests/domain/world_graph/test_game_end_result_player_outcomes.py`

| 判定 | 元の宣言 | 契約・保存先 |
|---|---|---|
| R | `test_existing_three_argument_constructor_player_outcomes_none` | 既存 3 引数 constructor で player outcomes は None。 |
| R | `test_per_player_game_end_result` | per player モードの GameEndResult。 |

### `tests/domain/world_graph/test_surviving_player_group_comparison_end_condition.py`

| 判定 | 元の宣言 | 契約・保存先 |
|---|---|---|
| R | `test_three_crew_against_two_keepers_does_not_end` | crew 3 人、keeper 2 人なら人数差が残っているので成立しない。 |
| R | `test_two_crew_against_two_keepers_ends` | crew 2 人、keeper 2 人なら同数になったため成立する。 |
| R | `test_two_crew_against_one_keeper_does_not_end` | keeper が 1 人退場済みなら crew 2 人で敗北にはならない。 |
| C | `test_dead_players_who_continue_as_ghosts_are_not_survivors` | 既存keeperが同じDEAD入力とis_ended/resultを保持。幽霊もDEADであり生存数に戻さないという説明を吸収 |
| C | `test_ejected_players_are_not_survivors` | 同一入力とFalseを持つkeeperに追放者は比較母数から除外という説明を吸収 |
| R | `test_missing_comparison_state_is_rejected` | 比較先が無い宣言は、右辺の人数が決まらないため拒否する。 |
| R | `test_identical_state_selectors_are_rejected` | 同じ集合との比較は常に成立するため、開始即終了を構築時に拒否する。 |

### `tests/domain/world_graph/value_object/test_game_end_condition.py`

| 判定 | 元の宣言 | 契約・保存先 |
|---|---|---|
| R | `test_condition_type_without_a_validation_branch_raises` | __post_init__ に分岐が無い条件型を渡すと拒否される。 |
| R | `test_every_declared_condition_type_has_a_validation_branch` | 宣言済みの全条件型は「未知」で落ちない (必須値欠落での拒否は許容)。 |
| R | `test_it_is_constructible_without_any_field` | 条件型だけで構築できる。 |
| R | `test_missing_target_spot_is_rejected` | target_spot_id を省くと拒否される。 |
| R | `test_target_spot_is_accepted` | target_spot_id があれば構築できる。 |

### `tests/domain/world_graph/value_object/test_player_outcome_rule.py`

| 判定 | 元の宣言 | 契約・保存先 |
|---|---|---|
| R | `test_accepts_resolved_outcome_with_empty_player_conditions` | 未確定者全員を対象にするための空条件列は有効な宣言である。 |
| R | `test_rejects_malformed_fields` | 識別子・trigger・条件 tuple・once の型違反は値オブジェクトが拒否する。 |
| R | `test_rejects_outcomes_that_require_other_world_state` | 規則だけでは世界状態を完結できない未確定・死亡・追放を拒否する。 |

### `tests/domain/world_graph/value_object/test_scenario_team.py`

| 判定 | 元の宣言 | 契約・保存先 |
|---|---|---|
| R | `test_team_without_members_is_rejected` | 所属する人が 0 人のチームを作ると ScenarioTeamValidationException を投げる。全員が条件を満たす、が空集合で成立してしまうため。 |
| R | `test_team_without_win_conditions_is_rejected` | 勝利条件が 1 つも無いチームを作ると ScenarioTeamValidationException を投げる。 |
| R | `test_duplicated_member_is_rejected` | 同じ player を 2 度含むチームを作ると ScenarioTeamValidationException を投げる。 |
| R | `test_blank_team_id_is_rejected` | 空文字か空白だけの team_id を渡すと ScenarioTeamValidationException を投げる。 |
| R | `test_single_satisfied_team_wins_and_others_lose` | 成立したのが北だけなら、北が WIN、南が LOSE になる。 |
| R | `test_no_satisfied_team_means_every_team_loses` | どのチームも成立していなければ、全チームが LOSE になる。 |
| R | `test_simultaneous_satisfaction_is_a_draw_not_two_wins` | 北と南が同時に成立したら両方 DRAW になり、成立しなかった東は LOSE。WIN は 1 つも出ない。 |
| R | `test_unknown_satisfied_team_id_is_rejected` | 宣言に無い team_id を成立したと渡すと ScenarioTeamValidationException を投げる。 |

## 故意変更の対照

| 故意変更 | 旧 | 新 | 判定 |
|---|---|---|---|
| 固定閾値の人数を1へ丸める | 対象全体成功 | 閾値1・2人生存で失敗 | 修理 |
| 空旗固有の拒否を外す | 別の超過例外で成功 | required_flags必須の理由違いで失敗 | 修理 |
| 旗条件を中立終了型で構築 | 正の宣言1件は成功 | 正の宣言の型assertで失敗 | 焦点の補強 |
| 閾値超過をRuntimeErrorで拒否 | 対象全体成功 | 期待するdomain例外と違い失敗 | 修理 |
| 閾値欠落をKeyErrorで拒否 | 対象全体成功 | ScenarioLoadErrorと違い失敗 | 修理 |
| ANYを非空ALLとして集約 | 対象全体成功 | 混在する2人で失敗 | 修理 |
| 非整数tickを常に不成立 | 対象全体成功 | tick11で失敗 | 修理 |
| 全滅結果のラベルを落とす | 統合元が失敗 | 全員DEADの保持先が失敗 | 保存 |
| 固定陣営の生存数を0へ固定 | 元の全員UNRESOLVED宣言が失敗 | 全員生存の保持先が失敗 | 保存 |
| DEADを生存に数える | 元の幽霊宣言が失敗 | 2対2の保持先が失敗 | 保存 |
| EJECTEDを生存に数える | 元の追放宣言が失敗 | 2対1の保持先が失敗 | 保存 |
| 場所必須値を要求しない | 元の表と既存保持先が失敗 | 統合後の場所2行が失敗 | 保存 |
| tick必須値を要求しない | 元の表が失敗 | 移したtick行が失敗 | 保存 |
| 評価器の局所変数を一貫して改名 | 成功 | 成功 | 意味維持 |

条件型の誤変換は、旧の閾値超過試験も別理由で失敗する。旧担当全体が通ったとは主張せず、正の読み込み宣言1件に限定した追加対照を残した。他の6修理は担当全体で旧成功を確認した。配置文脈の追加assertは用途側接続を明示するが、独立した新規検出件数には加えていない。

## 導入・修正履歴

- [陣営の全滅条件を導入](https://github.com/Motifman/llm-rpg/commit/c869989b72b332a542acb46e6d4814424b6d7b94)
- [型ではなくシナリオの置き場所で勝敗を決める](https://github.com/Motifman/llm-rpg/commit/cc7b4687a0450e3e6c0743f8625b9f9ff71f08c8)
- [複数作業の旗を数える条件とJSON接続](https://github.com/Motifman/llm-rpg/commit/5283b5fbc2771a83a88f4d1d216032890bcf8c52)
- [両陣営の現在生存数の比較](https://github.com/Motifman/llm-rpg/commit/5a234ddf20f19bd51889c1a1e6f0484890b220c8)
- [必須値を構築時に拒否](https://github.com/Motifman/llm-rpg/commit/1823107547a5a31668bf421da775f8eaad7d2ed1)
- [未知条件型の検証漏れと空振り検査を修理](https://github.com/Motifman/llm-rpg/commit/2d9e8ea4375fe581238466f4e8d0e01ee07d0046)
- [個人結果規則の宣言から実行まで接続](https://github.com/Motifman/llm-rpg/commit/a30bc3db0094376280ce2d403e8e1700206cd60b)
- [チーム結果と同時成立DRAW](https://github.com/Motifman/llm-rpg/commit/423287db10421f740bb40e24d7070b5add59d4c7)

## 範囲外と残る確認

- #1731の欲求、#1741の共通述語、#1742の効果は別の担当として再編集しない。記憶・SNSの進行中変更も除外した
- 通常win/loseが同時成立した場合は実装上winが先。今回読んだ終了関連試験で、この両立を直接作る保持試験は確認できていない。今回削除した保証ではなく、既存の確認不足として残す
- 基準失敗0。確認した製品不具合は無く、未検査の組合せを製品不具合と呼ばない。製品修理やIssue作成は行わない
- 全open PRの正確な先端と変更パスを照合した。対象の9試験と5製品ファイルへの直接重複0。関連runtimeに触れる#1693/#1694はprompt/記憶配線で、終了判定と時計とは異なる位置・意味だった
