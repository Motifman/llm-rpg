# 探索・パズル・罠の試験責任と保存確認

## 対象と結果

- 基準main: `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。ローカル再構成基準 `d2a11ae023ad55ff0dc5b0dcf9864cd88e43d2d0` のtreeは、公開mainと同じ `4807c4c1ce6ceddf5f812a0b0bef0278e528fe07`
- 対象は下記3ファイルの40宣言。判定はR31（保持）、F5（契約を保って検査を修理）、C3（保持先へ統合）、D1（重複検査の削除）
- 最終36宣言・39実行件。基準40宣言・42実行件との差には、反復罠の初回／発動済みを同一宣言の2行へ残した変更を含む
- 対象試験は623行→595行、追加39行／削除67行。製品・試験用支援コードの変更は0行。削除数を目標にせず、既存の公開契約と意味がある模擬評価器試験を保持した
- 最新照合時の公開74PRに、対象3試験・3評価サービスの直接変更はない。今回の規約は本書へ残す

対象ファイル:
- E: `tests/domain/world_graph/test_spot_exploration_service.py`（9宣言→8）
- P: `tests/domain/world_graph/test_puzzle_evaluation_service.py`（14宣言を保持）
- T: `tests/domain/world_graph/test_trap_evaluation_service.py`（17宣言→14）

## 所有者・呼出元・導入理由

探索は`SpotExplorationService.explore`が、発見条件・発見済み状態・未発見候補の残りを決める。`SpotExplorationApplicationService._explore_with_repositories`は累積探索数と所持品目を解決し、発見状態保存・品物付与・通知を行う。`WorldRuntime.do_explore`と道具の入口がこれを呼ぶ。application側の確定・巻き戻し・通知試験は別の故障を検出するため、その層へ変更を広げない。

共通述語の型と入力不足／通常不成立の区別は`ScenarioPredicateEvaluator`の試験が主担当。探索側には、異常結果を静かな未発見へ縮退させない検査を残す。FLAG_SETの模擬評価器試験は、空の世界フラグでも共通核の成立結果を採用するため、単なる呼出引数検査ではない。用途側で正常結果を再計算する回帰を単独で捕える。

`PuzzleEvaluationService`と`TrapEvaluationService`は現行`src`・`scripts`内に製品呼出元を確認できない。ただし[パズル導入](https://github.com/Motifman/llm-rpg/commit/bb8e3859a94d94c67c11e0394042fc9b1df32cf3)、[罠導入](https://github.com/Motifman/llm-rpg/commit/2caaeecc5262547ff323d10471399e31c19a0a94)は公開された状態遷移・評価APIを定義し、[罠の旗返却修正](https://github.com/Motifman/llm-rpg/commit/7a4208fd0715acd9c7cd80ba9d18b9f45a2c7b8d)には一度きり罠の再発動防止という理由がある。`PuzzleState`は`SpotObject`と世界保存復元、`TrapDef`は`SpotNode`・`SpotObject`とSQLite符号化で製品利用される。呼出数0だけを理由にAPIと唯一の試験を廃止しない。

参照した判断・履歴:
- `docs/design_decisions.md`判断#71/#75: 同じ意味の葉だけを共通核へ移し、通常不成立と評価不能を分ける
- `docs/design_decisions.md`判断#78: 罠定義をSQLiteで保持する。発火stageと解除数量判定は別変更
- `docs/spot_graph/todo.md`: PR #53/#54の公開機能として罠・パズルを記録
- [探索余地の区別](https://github.com/Motifman/llm-rpg/commit/1d5ab8c7338042ff84460fa303d0903abd29eecd)、[世界フラグ共通化](https://github.com/Motifman/llm-rpg/commit/7f13d9e75b8d72c1923cdbaa85af4ae6faab723c)、[品目所持共通化](https://github.com/Motifman/llm-rpg/commit/22d422ff0b3927e0953502db412563e71983e1df)

## 層の整理と保持先

- 罠の進入成功に一度きりの旗返却を、操作成功に操作罠の旗返却を移した。同じ入口と同じ結果を繰り返す元2宣言をその後に削除
- 反復罠の旗なし検査を反復発動の主担当へ移した。空flagsの初回と発動済みflagsありの両入力を保ち、実発動・効果・新規旗なしを一緒に検査する。既存旗ありだけへ移すと、初回だけ余計な旗を返す誤りを失う
- 品目側の成功固定模擬評価器試験は、現行で検出する要求品目／所持集合の誤接続を実評価器の`test_has_item`が捕えると変異で確認してから削除。異常結果の用途側伝播試験は残した
- 空／全発見済みの探索余地試験へ再発見禁止を追加する案は見送った。application側の探索3回実行が再付与禁止を既に守っており、同じ契約を増やさない
- パズルの解決済み・試行上限の拒否は、結果文だけでなく入力時点の全状態を保持することを検査する。罠解除は不発時に効果と新規旗も空であること、異なる旗だけなら発動することを検査する。複数効果は件数だけでなく値と順序を検査する

## 全40宣言の台帳

行番号は基準main。保持先の詳細は以下の統合・削除対応表を参照。

| ID | 元の宣言 | 判定 | 契約と検出する誤り |
| --- | --- | --- | --- |
| E01 | E:18 `TestSpotExplorationService.test_always_discovers` | R | ALWAYSの未発見物を返し発見済みにする。報酬、説明、状態更新の欠落を検出 |
| E02 | E:32 `TestSpotExplorationService.test_search_count_requires_two` | R | 探索回数の境界1→2と条件未達時の探索余地を返す。閾値超過比較や早期枯渇を検出 |
| E03 | E:51 `TestSpotExplorationService.test_has_item` | R | 指定品目の未所持→所持で発見可否と探索余地を切り替える。所持入力の無視や早期枯渇を検出 |
| E04 | E:70 `TestSpotExplorationService.test_empty_or_all_discovered_interiors_have_no_remaining_discoverable_items` | R | 空・全発見済みは探索余地が無い。再付与禁止はapplication層のsearch_count/has_item三回実行が既に独立に守るため、同じ検査を追加しない |
| E05 | E:84 `TestSpotExplorationService.test_flag_set` | R | 要求フラグの無→有で新発見を切り替える。フラグ入力や要求名を誤って渡す回帰を検出 |
| E06 | E:100 `TestSpotExplorationService.test_flag_set_delegates_to_typed_common_evaluator` | R | 空の世界フラグでも共通核satisfiedの判断を採用する。正常結果を用途側でローカル再計算する回帰を独立に検出する。引数検査だけの試験ではない |
| E07 | E:127 `TestSpotExplorationService.test_has_item_delegates_resolved_ownership_to_common_evaluator` | D | 成功固定の品目評価器で検査していた要求品目・所持集合の誤接続は、実核test_has_itemが同じ変異を捕える。異常停止試験を残してこの重複検査を削除。正常結果のローカル再計算は旧新とも未検出の既存範囲 |
| E08 | E:154 `TestSpotExplorationService.test_has_item_evaluation_failure_stops_exploration` | R | 所持判定のmissing/unsupportedを正常な未発見へ潰さず停止する。用途側が例外を握り潰す回帰を検出する2行を保持 |
| E09 | E:184 `TestSpotExplorationService.test_flag_set_evaluation_failure_stops_exploration` | R | フラグ判定のmissing/unsupportedを正常な未発見へ潰さず停止する。用途側が例外を握り潰す回帰を検出する2行を保持 |
| E10 | P:34 `TestPuzzleStateValidation.test_empty_puzzle_type_raises` | R | パズル種別が空なら構築を拒否する。保存・復元入力で意味の無い種別を受理する回帰を検出 |
| E11 | P:39 `TestPuzzleStateValidation.test_empty_solution_raises` | R | 空の解を拒否する。空入力だけで解錠可能になる不正状態の受理を検出 |
| E12 | P:44 `TestPuzzleStateValidation.test_puzzle_state_is_frozen` | R | パズル状態の直接代入を拒否する。元状態が暗黙に書き換わる回帰を検出 |
| E13 | P:54 `TestCombinationLock.test_correct_code_solves` | R | 正しい組合せで今回解決・解決済状態・試行1回を返す。正解判定や状態遷移の欠落を検出 |
| E14 | P:63 `TestCombinationLock.test_wrong_code_does_not_solve` | R | 誤った組合せで未解決・試行1回を返す。誤解錠や試行不加算を検出 |
| E15 | P:72 `TestCombinationLock.test_already_solved_returns_immediately` | F | 解決済みへの再入力は新たな解決ではない。既存は文言と真偽だけなのでnew_puzzleが元の全状態と等しいことを追加し再入力による進行破壊を検出 |
| E16 | P:80 `TestCombinationLock.test_max_attempts_blocks` | F | 組合せの上限以降は正解入力でも拒否する。現在は文言だけで試行数や入力保持の破壊を見逃すので上限2回と拒否時の全状態保持を追加 |
| E17 | P:95 `TestCombinationLock.test_correct_on_last_attempt` | R | 最終許可回の正解を受理する。上限到達の先行判定による最後の一回の拒否を検出 |
| E18 | P:107 `TestSequencePuzzle.test_correct_sequence_solves` | R | a,b,cの段階入力だけが最終解決になる。途中での誤解決や進捗欠落を検出 |
| E19 | P:120 `TestSequencePuzzle.test_wrong_order_resets` | R | 途中の順序違反で入力を空へ戻す。中間列の残留を検出 |
| E20 | P:130 `TestSequencePuzzle.test_retry_after_reset` | R | 誤順序からリセット後に正順序で解決できる。失敗後に復帰できない回帰を検出 |
| E21 | P:139 `TestSequencePuzzle.test_correct_steps_do_not_consume_attempts` | R | 順序の正解ステップは最終解決まで試行数0を保持。with_input流用による正解ステップ消費の既知回帰を検出 |
| E22 | P:151 `TestSequencePuzzle.test_sequence_max_attempts_counts_failed_sequences` | F | 順序の失敗列だけを数えて2回後に入力拒否する。拒否後の状態保持も追加し入力進行や試行数増加を検出 |
| E23 | P:174 `TestUnknownPuzzleType.test_unknown_type_returns_message` | R | 未知種別は解決扱いせず用途説明を返す。未知を既知方式へ誤配分する回帰を検出 |
| E24 | T:69 `TestEntryTrapEvaluation.test_basic_entry_trap_triggers` | R | 進入罠の発動とAPPLY_DAMAGE効果を返す。test_one_shot_trap_sets_triggered_flagの旗を同じ保持先に先行移管 |
| E25 | T:78 `TestEntryTrapEvaluation.test_one_shot_trap_sets_triggered_flag` | C | 一度きり進入罠の旗を返す。test_basic_entry_trap_triggersが同じ入力経路を持つため旗の厳密値を移して統合 |
| E26 | T:86 `TestEntryTrapEvaluation.test_repeating_trap_does_not_set_triggered_flag` | C | 初回反復罠が新規発動旗を返さない。移管先test_repeating_trap_retriggersは空flagsと既存旗ありの2行へ拡張し、両方で発動・効果・旗なしを保持する |
| E27 | T:93 `TestEntryTrapEvaluation.test_one_shot_trap_does_not_retrigger` | R | 一度きり発動済み罠は罠・効果を返さない。再発動を検出 |
| E28 | T:102 `TestEntryTrapEvaluation.test_repeating_trap_retriggers` | R | 反復罠は発動済み旗があっても発動する。初回の空flagsを加えた2行で実発動と旗非追加を一緒に保持 |
| E29 | T:110 `TestEntryTrapEvaluation.test_disarmed_trap_does_not_trigger` | F | 解除フラグで不発。現在は罠一覧だけで効果漏れと旗照合無視を見逃すためフラグなし正対照と全戻り値を追加 |
| E30 | T:124 `TestEntryTrapEvaluation.test_disarm_by_item` | R | 解除品目のなし→ありで発動を切り替える。品目入力を無視する回帰を検出。数量条件とは別仕様を保つ |
| E31 | T:142 `TestEntryTrapEvaluation.test_multiple_traps_evaluate_independently` | R | aだけ発動済みならbだけ発動する。全罠を一括で止める回帰を検出 |
| E32 | T:154 `TestEntryTrapEvaluation.test_multiple_effects_per_trap` | F | 一罠から複数効果を全件返す。長さ2だけでは損傷効果二重や順序反転を見逃すので独立に作った効果列との完全一致へ修理 |
| E33 | T:161 `TestEntryTrapEvaluation.test_on_interact_trap_ignored_by_entry_evaluation` | R | 操作罠を進入評価で発動させない。トリガー選別の欠落を検出 |
| E34 | T:172 `TestInteractTrapEvaluation.test_interact_trap_triggers` | R | 操作罠の状態異常効果を返す。test_one_shot_interact_trap_sets_flagの旗を同じ保持先へ先行移管 |
| E35 | T:180 `TestInteractTrapEvaluation.test_entry_trap_ignored_by_interact_evaluation` | R | 進入罠を操作評価で発動させない。別入口のトリガー選別の欠落を検出 |
| E36 | T:187 `TestInteractTrapEvaluation.test_one_shot_interact_trap_does_not_retrigger` | R | 一度きり操作罠の発動済み旗があれば効果を返さない。操作入口の再発動を検出 |
| E37 | T:195 `TestInteractTrapEvaluation.test_one_shot_interact_trap_sets_flag` | C | 一度きり操作罠の旗を返す。test_interact_trap_triggersへ旗assertを移して重複実行を統合 |
| E38 | T:207 `TestTrapDefValidation.test_trap_def_is_frozen` | R | 罠定義の識別子を直接変更できない。共有定義が別利用者から壊れる回帰を検出 |
| E39 | T:213 `TestTrapDefValidation.test_empty_trap_id_raises` | R | 空の罠IDを拒否する。発動済み旗が衝突する不正定義の受理を検出 |
| E40 | T:222 `TestTrapDefValidation.test_no_effects_raises` | R | 効果なし罠を拒否する。無意味な罠定義の受理を検出 |

### 統合・削除の対応

| 元 | 保持先 | 先に残した判定 |
| --- | --- | --- |
| T `test_one_shot_trap_sets_triggered_flag` | T `test_basic_entry_trap_triggers` | 実発動・損傷効果と対象罠の発動済み旗の厳密値 |
| T `test_repeating_trap_does_not_set_triggered_flag` | T `test_repeating_trap_retriggers` | 初回／発動済みの両行で実発動・効果・新規旗空 |
| T `test_one_shot_interact_trap_sets_flag` | T `test_interact_trap_triggers` | 状態異常効果と対象罠の発動済み旗の厳密値 |
| E `test_has_item_delegates_resolved_ownership_to_common_evaluator` | E `test_has_item`、`test_has_item_evaluation_failure_stops_exploration` | 要求品目／所持集合の接続、共通核の異常結果で停止 |

## 検証と独立確認

- 未編集基準: 対象42件＋関連20件成功
- 旗の保持先を先に補い、元宣言を残した状態: 対象43件成功
- 統合・削除後: 対象39件成功
- 変異後に製品を戻した最終: 対象39件＋関連20件＝59件成功。失敗・収集エラー・skipなし
- 関連範囲: `test_spot_exploration_command_scope.py`の4宣言、`test_spot_graph_step4_integration.py`の探索3宣言、共通評価核の`TestScenarioPredicateEvaluatorFlagSet`と`TestScenarioPredicateEvaluatorItemOwnership`
- `ruff check`対象3ファイル、`git diff --check`成功。元から書式一括変更を採っていないリポジトリ方針に従い、無関係な整形は行わない
- 安全なオフライン実行器で外部通信を遮断、秘密・proxy・外部モデル接続を除外し、対象作業木の`src`を読んだことを確認。実LLM・ネットワーク試験・全リポジトリ試験は実行していない
- CIは既存`.github/workflows/ci.yml`の`uv run --frozen pytest -n auto`が対象を自動収集する。`quality`と`live_api`は通常選択から除外される。経路追加・CI設定変更は不要

### 旧新変異の対照

変異は製品所有者だけへ一時的に入れ、対応する削除元・保持先を旧版／候補版で実行した。狙ったassertの失敗であることを確認し、旧新の製品12ファイルは基準のSHA-256とbyte一致へ戻した。12種類24実行の内訳は次のとおり。

| 変異 | 旧版 | 候補版 | 意味 |
| --- | --- | --- | --- |
| 解決済みへの入力が試行数と履歴を増やす | 実行1・失敗0 | 実行1・失敗1 | 修理で新たに検出 |
| 上限拒否時に入力が試行数と履歴を増やす | 実行2・失敗0 | 実行2・失敗2 | 修理で新たに検出 |
| 解除された罠だけ効果が漏れる | 実行1・失敗0 | 実行1・失敗1 | 修理で新たに検出 |
| 解除フラグの名前照合を無視する | 実行1・失敗0 | 実行1・失敗1 | 修理で新たに検出 |
| 複数効果を先頭効果の複製にする | 実行1・失敗0 | 実行1・失敗1 | 修理で新たに検出 |
| 進入罠の発動旗を誤ったIDにする | 実行2・失敗1 | 実行1・失敗1 | 削除元から保持先へ検出力を移管 |
| 操作罠の発動旗を返さない | 実行2・失敗1 | 実行1・失敗1 | 削除元から保持先へ検出力を移管 |
| 初回反復罠だけ発動旗を追加する | 実行2・失敗1 | 実行2・失敗1 | 削除元から保持先へ検出力を移管 |
| 共通核へ要求品目IDを誤って渡す | 実行2・失敗2 | 実行1・失敗1 | 残存実評価器試験でも検出 |
| 共通核へ所持集合を空にして渡す | 実行2・失敗2 | 実行1・失敗1 | 残存実評価器試験でも検出 |
| フラグ共通核の正常結果を用途側で再計算する | 実行1・失敗1 | 実行1・失敗1 | 固有の契約として保持 |
| 品目共通核の正常結果だけ用途側で再計算する | 実行4・失敗0 | 実行3・失敗0 | 旧新に共通する既存の未検出点 |

## 今後の変更時の規約

- 模擬評価器で成功を返していても、その結果と本来の入力が食い違う場合は「どちらの判定を採用するか」という独立した契約がある。呼出形だけを見て一括削除しない
- 同じ保持先へ移す場合も入力集合を比べる。初回と再発動、空集合と既存旗ありを混同しない
- 拒否を返す入口は拒否文だけでなく、不変であるべき状態が保持されることを主担当で確認する
- 発動しないことは罠一覧だけで判断せず、効果や永続化用の旗が漏れていないことを確認する。複数効果は件数一致だけへ戻さない
- 休眠している評価サービスも公開API、保存利用、導入目的を確認する。呼出数だけで削除しない

## 限界と別所見

品目側で共通核の正常結果だけを用途側で再計算する変異は、旧削除元を含む旧4件も残存3件も成功した。これは今回失った検査ではなく、従来から検査していなかった範囲である。世界フラグ側は同じ再計算を固有の保持試験が捕える。本監査で品目側の新規契約追加や製品修正は行わない。

罠・パズル評価サービスの製品入口が現在接続されていない点、罠解除の数量無視は別判断として残す。前者には公開機能記録、後者には判断#75の既存留保があり、本監査だけで不具合や廃止対象とは断定しない。基準試験失敗は無く、製品修正やIssue作成は行っていない。
