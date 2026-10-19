# 品目実体の状態・時刻・独立した拒否を守る

## 目的と固定基準

元の2ファイル24宣言を監査し、保持3、検査修理11、統合10、単独削除0とした。使う側と使われる側で繰り返していた準備と検査を1つの表へ集約し、別々の処理が片方だけ壊れる場合も各行で検出する。警告の未検証、部分更新の不十分な入力、保存用変更通知の欠落、片側だけの拒否を見逃す穴を試験で埋めた。製品の変更はない。

固定親は [#1770](https://github.com/Motifman/llm-rpg/pull/1770) の `484f0a085be686e1e587159a0341557844f68153`。対応するローカル基準は `a0712a1a2e4ff7b02e1ab910941b474c16cf9ef9`、treeは `7d75787f8a58930c5f0f01b01ce05e0fc20fb2e2`。親に含まれる [#1688](https://github.com/Motifman/llm-rpg/pull/1688) の備蓄対象修正と、相互作用・品目授受の保持先を変えない。

相互作用94宣言と品目授受51宣言は別監査済みであり、今回の24宣言へ再計上しない。Itemの値型・スタック拒否、効果可視性、アプリ保存接続も別の試験が所有する。

## 所有境界と履歴

- `WorldGraphEffectService.apply_effects` が実体を選んで状態・現在時刻を適用し、実際の状態差から両変更通知を別々に返す
- `effect_application/handlers/item_instance.py` が変更・時刻効果をそれぞれの実体へ適用し、必要入力の欠落を警告する
- `SpotInteractionService.can_interact` は公開条件入口。実評価器へ選択側の状態と要求全体を渡し、欠落・不一致は拒否し、作者の失敗文を返す
- `execute_interaction` と `execute_declared_interaction` は両実体と現在時刻を効果サービスへ渡す。`SpotInteractionApplicationService` は両変更通知を使い、必要な実体を別々に保存する
- 同じ仕様IDを持つ別実体は正当な入力。同じ集約参照を両側に渡すことは、条件入口と効果入口の両方で拒否する。アプリ層の同じ実体IDの拒否とは入口が異なる

使う側の11宣言は [8940df7](https://github.com/Motifman/llm-rpg/commit/8940df7fac51abe414d1cc193339c4dd1319c4ec)、使われる側の基盤は [b89162f](https://github.com/Motifman/llm-rpg/commit/b89162ff0853568f2bb221d45829c7b783d73364) に由来する。[8954570](https://github.com/Motifman/llm-rpg/commit/8954570df428c84cb7b45baea250d016cb2859a2) は#113のレビューを受け、同じ実体の二重変更・二重保存を防ぐため両入口の拒否と2試験を追加した。この2宣言は残す。[1d4e8d8](https://github.com/Motifman/llm-rpg/commit/1d4e8d8f4d8fd179c42d909cf8f396786b5783e1) による種別別処理への分割でも公開の意味は変わっていない。

## 統合する層と残す契約

`tests/domain/world_graph/test_item_instance_state_effects.py` を主担当にし、`test_target_item_instance_state_effects.py` を退役させる。実サービスと実ItemAggregateを使い、効果・条件を模擬実装で置き換えない。試験専用の製品入口や共有支援の追加・削除はない。

- 部分更新は指定キーだけ変更し、未指定キーと反対側の全状態を残す
- 時刻だけの変更でも選択側の変更通知を返す。使う側42・使われる側99の行は反対側を省略する。各側の時刻0の行は両実体を渡し、対象の取り違えを検出する
- 更新値不正、時刻・キー・実体の欠落は状態不変、両変更通知false、原因を指す警告を確認する。警告のレベル・効果名・原因語は同じ1レコード内で照合する
- 条件は反対側なしの部分一致を許可する。両実体がある行は反対側に逆の値を置き、複数キーの全一致・先頭だけ不一致・末尾だけ不一致を確かめる
- 両側の条件は成否4通りで確認し、使う側だけ、使われる側だけの不一致を個別に拒否する
- 同一実体拒否2入口と、1度の適用で両実体を変更・通知する合成試験を独立に保持する

### 第二読で守り直した片側省略

初期の保持案は正常系すべてに両実体を渡していた。独立した第二読で、時刻と条件の「反対側を省略しても動く」という既存入力が失われると指摘された。特に剣修理デモは両実体を渡すため、この単独入力の代替にはならない。

時刻42/99の行を片側だけ、時刻0の行を両側ありに分け、条件の部分一致行も片側だけとした。11宣言33例のまま、単独適用と両実体の分離を両立する。元の宣言名・状態キー・値を機械的に複製するのではなく、元の成功/拒否の条件と観測結果が保持先に残っていることを確認した。

## 統合10宣言の対応

保持先はすべて上記主担当ファイル内。行名は表の入力区分を示す。

| 元の宣言 | 保持先 | 残す入力・観測 |
|---|---|---|
| `TestChangeItemInstanceStateEffect::test_merges_state_updates_into_acting_item` | `test_merges_only_selected_item_state[acting]` | 使う側の行へ移す。反対側も渡し状態不変と両通知を確認する |
| `TestChangeItemInstanceStateEffect::test_no_op_and_warn_when_acting_item_is_none` | `test_missing_item_warns_without_changing_other_item[change-acting]` | 欠落する側と効果を明記した行へ移し、反対側への誤適用も拒否する |
| `TestRecordItemInstanceStateTickEffect::test_writes_current_tick_into_state_key` | `test_records_tick_only_on_selected_item[acting]` | 42の行では旧入力どおり反対側を省略する。0の行は両実体を渡し、存在する実体の状態と両通知を確認する |
| `TestItemInstanceStatePrecondition::test_passes_when_state_matches` | `test_required_state_matches_only_selected_instance[acting-subset-match]` | 部分一致の行では旧入力どおり反対側を省略する。別の複数キー一致行では反対側の不一致状態との対照を保つ |
| `TestItemInstanceStatePrecondition::test_fails_when_state_differs` | `test_required_state_matches_only_selected_instance[acting-mismatch]` | 使う側の不一致行で成否と作者文の完全一致を保つ |
| `TestItemInstanceStatePrecondition::test_fails_when_acting_item_is_none` | `test_missing_item_condition_refuses_with_reason[acting]` | 使う側欠落の行へ移し、既定理由断片を保持する |
| `TestChangeTargetItemInstanceStateEffect::test_no_op_and_warn_when_target_is_none` | `test_missing_item_warns_without_changing_other_item[change-target]` | 使われる側欠落の行へ移し、反対側の不変も明示する |
| `TestTargetItemInstanceStatePrecondition::test_passes_when_target_state_matches` | `test_required_state_matches_only_selected_instance[target-subset-match]` | 部分一致の行では旧入力どおり反対側を省略する。別の複数キー一致行では反対側に不一致値を置く |
| `TestTargetItemInstanceStatePrecondition::test_fails_when_target_state_differs` | `test_required_state_matches_only_selected_instance[target-mismatch]` | 使われる側の不一致行へ成否と作者文の完全一致を移す |
| `TestTargetItemInstanceStatePrecondition::test_fails_when_target_is_none` | `test_missing_item_condition_refuses_with_reason[target]` | 使われる側欠落の行へ移す。反対側が条件一致でも拒否する |

## 全24宣言の台帳

Rは契約保持、Fは検査の修理、Cは指定保持先への統合。F11は元宣言の分類であり、変異12種や実行例33件とは別の数である。位置は編集前の固定親を基準とする。

### test_item_instance_state_effects.py

| 元の宣言と行 | 判定 | 検出契約・扱い・保持先 |
|---|---|---|
| `TestChangeItemInstanceStateEffect::test_merges_state_updates_into_acting_item` (75) | C | 使う側のlitを更新しfuelを残し、使う側変更通知を返す。使う側の行へ移す。反対側も渡し状態不変と両通知を確認する。保持先: `test_merges_only_selected_item_state[acting]` |
| `TestChangeItemInstanceStateEffect::test_no_op_and_warn_when_acting_item_is_none` (94) | C | 使う側欠落時に変更通知falseとacting_item_aggregate診断を返す。欠落する側と効果を明記した行へ移し、反対側への誤適用も拒否する。保持先: `test_missing_item_warns_without_changing_other_item[change-acting]` |
| `TestChangeItemInstanceStateEffect::test_no_op_when_state_updates_is_not_dict` (112) | F | 辞書でない更新を適用せず状態と通知を変えない。警告自体は未検証。既存の状態/通知に加え、当該効果とstate_updatesを指す警告を確認する。保持先: `test_invalid_state_updates_warns_without_mutation[acting]` |
| `TestRecordItemInstanceStateTickEffect::test_writes_current_tick_into_state_key` (135) | C | 42を指定キーへ書き、元のlitを残して使う側変更通知を返す。42の行では旧入力どおり反対側を省略する。0の行は両実体を渡し、存在する実体の状態と両通知を確認する。保持先: `test_records_tick_only_on_selected_item[acting]` |
| `TestRecordItemInstanceStateTickEffect::test_no_op_when_current_tick_missing` (154) | F | 時刻欠落時に指定キーを作らない。警告と通知falseは未検証。非空の元状態全体・両通知false・current_tickを指す警告を確認する。保持先: `test_invalid_tick_context_warns_without_mutation[acting-missing-tick]` |
| `TestRecordItemInstanceStateTickEffect::test_no_op_when_state_key_missing` (173) | F | キー欠落時に空状態を保つ。警告と通知falseは未検証。非空の元状態全体・両通知false・state_keyを指す警告を確認する。保持先: `test_invalid_tick_context_warns_without_mutation[acting-missing-key]` |
| `TestRecordItemInstanceStateTickEffect::test_no_op_when_acting_item_missing` (192) | F | 時刻効果で使う側が欠落すると変更通知false。警告自体は未検証。有効な時刻/キーを供給し、実体欠落の警告と反対側の不変を確認する。保持先: `test_missing_item_warns_without_changing_other_item[tick-acting]` |
| `TestItemInstanceStatePrecondition::test_passes_when_state_matches` (232) | C | 使う側litが一致すればfuelという余分な状態があっても許可する。部分一致の行では旧入力どおり反対側を省略する。別の複数キー一致行では反対側の不一致状態との対照を保つ。保持先: `test_required_state_matches_only_selected_instance[acting-subset-match]` |
| `TestItemInstanceStatePrecondition::test_fails_when_state_differs` (248) | C | 使う側lit不一致を拒否し作者の失敗文を返す。使う側の不一致行で成否と作者文の完全一致を保つ。保持先: `test_required_state_matches_only_selected_instance[acting-mismatch]` |
| `TestItemInstanceStatePrecondition::test_fails_when_acting_item_is_none` (266) | C | 使う側欠落を拒否し必要なacting item/use_itemの理由を返す。使う側欠落の行へ移し、既定理由断片を保持する。保持先: `test_missing_item_condition_refuses_with_reason[acting]` |
| `TestItemInstanceStatePrecondition::test_required_state_with_multiple_keys_all_match` (282) | F | 複数キーの一致を許可し末尾fuelだけの不一致を拒否する。先頭lit脱落は検出しない。全一致、先頭だけ不一致、末尾だけ不一致を独立した行にする。共通評価器の全キー算法を再実装しない。保持先: `test_required_state_matches_only_selected_instance[acting-multi-key]` |

### test_target_item_instance_state_effects.py

| 元の宣言と行 | 判定 | 検出契約・扱い・保持先 |
|---|---|---|
| `TestChangeTargetItemInstanceStateEffect::test_merges_into_target_not_acting` (83) | F | 使われる側rustを変え、使う側と使う側通知を変えない。部分更新の未指定キー維持は入力にない。使われる側に未指定の残すキーを追加し、更新先と両通知の既存確認を保持する。保持先: `test_merges_only_selected_item_state[target]` |
| `TestChangeTargetItemInstanceStateEffect::test_no_op_and_warn_when_target_is_none` (104) | C | 使われる側欠落時に通知falseとtarget_item_aggregate診断を返す。使われる側欠落の行へ移し、反対側の不変も明示する。保持先: `test_missing_item_warns_without_changing_other_item[change-target]` |
| `TestChangeTargetItemInstanceStateEffect::test_no_op_when_state_updates_not_dict` (120) | F | 辞書でない更新を適用せず使われる側状態を保つ。警告/通知は未検証。当該効果とstate_updatesの警告、両通知false、両実体不変を確認する。保持先: `test_invalid_state_updates_warns_without_mutation[target]` |
| `TestRecordTargetItemInstanceStateTickEffect::test_writes_current_tick_into_target_state` (140) | F | 99を書き元のrustを残す。時刻だけの変更通知は未検証。99の行では旧入力どおり反対側を省略する。0の行は両実体を渡す。時刻単独更新で使われる側通知true、使う側falseを確認する。保持先: `test_records_tick_only_on_selected_item[target]` |
| `TestRecordTargetItemInstanceStateTickEffect::test_no_op_when_target_missing` (156) | F | 時刻効果で使われる側が欠落すると通知false。警告は未検証。時刻/キーを有効にして欠落警告・両通知false・反対側不変を確認する。保持先: `test_missing_item_warns_without_changing_other_item[tick-target]` |
| `TestRecordTargetItemInstanceStateTickEffect::test_no_op_when_current_tick_missing` (171) | F | 時刻欠落時に空状態を保つ。警告/通知は未検証。非空状態全体・両通知false・current_tick警告を確認する。対称表に使われる側のキー欠落も加える。保持先: `test_invalid_tick_context_warns_without_mutation[target-missing-tick]` |
| `TestTargetItemInstanceStatePrecondition::test_passes_when_target_state_matches` (207) | C | 使われる側rust一致なら許可する。部分一致の行では旧入力どおり反対側を省略する。別の複数キー一致行では反対側に不一致値を置く。保持先: `test_required_state_matches_only_selected_instance[target-subset-match]` |
| `TestTargetItemInstanceStatePrecondition::test_fails_when_target_state_differs` (223) | C | 使われる側rust不一致なら作者の失敗文で拒否する。使われる側の不一致行へ成否と作者文の完全一致を移す。保持先: `test_required_state_matches_only_selected_instance[target-mismatch]` |
| `TestTargetItemInstanceStatePrecondition::test_fails_when_target_is_none` (241) | C | 使われる側欠落時に条件を拒否する。使われる側欠落の行へ移す。反対側が条件一致でも拒否する。保持先: `test_missing_item_condition_refuses_with_reason[target]` |
| `TestTargetItemInstanceStatePrecondition::test_acting_and_target_evaluated_independently` (256) | F | 両側一致は許可し、使われる側だけ不一致なら拒否する。使う側だけ不一致は入力にない。両側の成否4通りを表で確認し、どちらの独立拒否も成立させる。保持先: `test_each_item_condition_can_refuse_independently` |
| `TestSameInstanceGuard::test_apply_effects_rejects_same_instance_for_acting_and_target` (301) | R | 同じ参照を両側へ渡すと効果が空でもValueErrorを返す。同名で残す。相互作用入口のガードではこの公開効果入口の直接呼出を代替しない。保持先: `test_apply_effects_rejects_same_instance_for_acting_and_target` |
| `TestSameInstanceGuard::test_can_interact_rejects_same_instance_for_acting_and_target` (316) | R | 同じ参照を両側へ渡すと前提条件が空でもValueErrorを返す。同名で残す。アプリ層のID等価拒否と参照同一拒否は別の入口として保持する。保持先: `test_can_interact_rejects_same_instance_for_acting_and_target` |
| `TestCombinedActingAndTargetEffects::test_both_aggregates_can_be_modified_in_one_apply` (343) | R | 一度に使う側used、使われる側rust/時刻を更新し両変更通知を返す。同名で残す。複数効果の合成と両通知は単一効果表では代替しない。保持先: `test_both_aggregates_can_be_modified_in_one_apply` |

## 修理11宣言の変異対照

製品を一時的に壊した隔離コピーで、元24件と保持先33件を同じ変更に対して別々に実行した。以下の11種は、元24件が成功する一方、保持先の対応検査が失敗した。元宣言が実際に見逃していたことを対照で示す。

| 元宣言 | 一時的な製品変更 | 保持先で検出するもの |
|---|---|---|
| `TestChangeItemInstanceStateEffect::test_no_op_when_state_updates_is_not_dict` | 使う側の更新値不正の警告を抑止 | 既存の状態/通知に加え、当該効果とstate_updatesを指す警告を確認する |
| `TestRecordItemInstanceStateTickEffect::test_no_op_when_current_tick_missing` | 使う側の時刻欠落の警告を抑止 | 非空の元状態全体・両通知false・current_tickを指す警告を確認する |
| `TestRecordItemInstanceStateTickEffect::test_no_op_when_state_key_missing` | 使う側のキー欠落の警告を抑止 | 非空の元状態全体・両通知false・state_keyを指す警告を確認する |
| `TestRecordItemInstanceStateTickEffect::test_no_op_when_acting_item_missing` | 時刻効果の使う側欠落の警告を抑止 | 有効な時刻/キーを供給し、実体欠落の警告と反対側の不変を確認する |
| `TestItemInstanceStatePrecondition::test_required_state_with_multiple_keys_all_match` | 使う側条件へ末尾の要求キーだけを渡す | 全一致、先頭だけ不一致、末尾だけ不一致を独立した行にする。共通評価器の全キー算法を再実装しない |
| `TestChangeTargetItemInstanceStateEffect::test_merges_into_target_not_acting` | 使われる側の部分更新を全置換へ変更 | 使われる側に未指定の残すキーを追加し、更新先と両通知の既存確認を保持する |
| `TestChangeTargetItemInstanceStateEffect::test_no_op_when_state_updates_not_dict` | 使われる側の更新値不正の警告を抑止 | 当該効果とstate_updatesの警告、両通知false、両実体不変を確認する |
| `TestRecordTargetItemInstanceStateTickEffect::test_writes_current_tick_into_target_state` | 使われる側変更通知を表示用要約の存在に依存させる | 99の行では旧入力どおり反対側を省略する。0の行は両実体を渡す。時刻単独更新で使われる側通知true、使う側falseを確認する |
| `TestRecordTargetItemInstanceStateTickEffect::test_no_op_when_target_missing` | 時刻効果の使われる側欠落の警告を抑止 | 時刻/キーを有効にして欠落警告・両通知false・反対側不変を確認する |
| `TestRecordTargetItemInstanceStateTickEffect::test_no_op_when_current_tick_missing` | 使われる側の時刻欠落の警告を抑止 | 非空状態全体・両通知false・current_tick警告を確認する。対称表に使われる側のキー欠落も加える |
| `TestTargetItemInstanceStatePrecondition::test_acting_and_target_evaluated_independently` | 使われる側が実在すると使う側の条件を読み飛ばす | 両側の成否4通りを表で確認し、どちらの独立拒否も成立させる |

これに加え、対称表へ補った使われる側のキー欠落行も、該当警告だけを抑止すると元24件成功・保持先失敗になる。したがって改善対照は12種。既存警告の修理7枝と、新しい対称行の1枝を混同しない。

保存対照は10種。状態変更と時刻記録の使う側/使われる側をそれぞれ逆へ適用する4種、各側の時刻を1ずらす2種、同一実体の条件/効果ガードをそれぞれ取り除く2種、各側の変更通知をfalseにする2種を実行した。すべて元24件と保持先33件の双方が検出した。

計22種44実行は全て予定した成否になり、各回の収集数は元24件・保持先33件で一定だった。収集・準備エラーを検出成功へ数えていない。変更した製品3ファイルは毎回元のバイト列へ戻し、最後に隔離コピーの差分0を確認した。最終候補の製品差分も0。

## 別に残す主担当

- `tests/domain/item/test_item_instance_state.py` は値型、非文字列キー、防御的コピー、部分更新、失敗時不変、状態付き実体のスタック拒否を所有する。Graphでの実体選択・効果振分け・変更通知を代替しない
- `tests/domain/world_graph/test_effect_visibility.py` は観測対象と状態差分の要約を所有する。表示用の要約と保存用の変更通知は別の出力
- `tests/domain/world_graph/test_spot_interaction_service.py` は共通評価不能の即時停止や旧API互換など、親監査の保持先を所有する
- `tests/domain/world_graph/test_object_stock_condition_target.py` の固定親由来6対照は無変更
- ランタン/剣修理のデモはJSON読込、実体解決、アプリ保存を所有する。メモリ内リポジトリは複製して読み書きするため、同じ参照の再読出だけで永続化を主張していない。ただしデータベース全体のトランザクションの証拠ではない
- 剣修理デモの使用済み道具の再使用ケースは剣も修理済みなので、使う側だけ不一致の検査の代替にはしない

これらの保持先は編集しない。重複に見えるという理由だけで責務の異なる入口を削除しない。

## 検証と行数

| 段階 | 結果 |
|---|---|
| 固定親の対象 | 24成功 |
| 固定親の関連 | 101成功 |
| 元24件と新33件の併存 | 57成功 |
| 変異対照 | 22種44実行、改善12種・保存10種を全て検出 |
| 完全復元後の最終対象 | 33成功 |
| 完全復元後の最終関連 | 101成功 |
| 静的検査 | 対象Ruff、整形確認、git diff --check成功 |

試験は2ファイル677行から1ファイル356行、追加318行・削除639行、差引321行減。宣言は24から11、実行例は24から33。製品・共有支援ファイルの変更は0。監査文書の行数は試験削減へ含めない。

試験は自身のソースを解決していることを確認し、ネットワークを遮断した実行環境で行った。変異対照の保持先と最終配置の差はimport間の空行1行のみで、構文木一致と最終配置での再実行を確認した。

再実行する最小範囲は以下。

```bash
uv run --frozen pytest tests/domain/world_graph/test_item_instance_state_effects.py
uv run --frozen pytest \
  tests/domain/item/test_item_instance_state.py \
  tests/domain/world_graph/test_effect_visibility.py \
  tests/domain/world_graph/test_spot_interaction_service.py \
  tests/domain/world_graph/test_object_stock_condition_target.py \
  tests/demos/test_lantern_lifecycle_demo_scenario.py \
  tests/demos/test_sword_repair_demo_scenario.py
```

## 最新mainとの関係と限界

2026-10-14 16:03 UTCに `e5b2b2a24646309b365772fafce431b42041ad89` から `fe8cab46646d39bf718a13cf936aecadc68e62b0` への64変更パスを確認した。対象2試験、直接の製品所有者・呼出元、関連101例の6試験、uv.lockとは直接交差しない。#1767の記憶機能撤去、観測変換、WorldRuntime組立ての変更は固定親へ取り込んでいない。

2026-10-14 16:28 UTCには、最新main `7f2443d7f3567d77c7163270ad562759eab6943f`（#1768統合）も再確認した。直前のfe8cab46からはシナリオ固定データ移設など9パスの変更で、対象・直接呼出元・関連101例・uv.lockとの直接交差はない。新規#1772の23変更では、SpotGraphSimulationApplicationServiceの差分はコメントのみであり、今回の関連試験は同クラスや退役するrelayシナリオを実行しない。新規#1773の56変更は記憶領域と実行時組立てなどで、今回の対象・直接呼出元・関連試験には交差しない。両PRはその後main `7c7dc63c5f4be701832a3f1443e27682fe9869d1` へ統合されたため、16:29 UTCに7f2443d7からの78変更も再照合した。対象2試験・直接呼出元・関連101例・uv.lockとの直接交差はなく、シミュレーションサービスとdomain内SubjectiveEpisodeの差分はコメントだけだった。これらを固定親へは取り込んでいない。

関連のランタン/剣修理デモはWorldRuntime組立てを呼ばず、ScenarioLoaderとSpotInteractionApplicationServiceを使う。上記成功は固定親での検証に限り、最新mainへ統合した全体成功とは主張しない。ローカル全体試験は未実行。公開時には親headと最新main、新規PRとの交差を再確認し、公開した正確なheadのCIを別途確認する。

## 継続時の所有規約

新しい状態効果や拒否を増やす際は、まずこの保持表の対応側へ入力と観測を足す。片側を欠落させる試験では他の必須入力を有効にし、別のガードで止まらないようにする。警告と状態不変、表示要約と変更通知、同じ仕様と同じ実体をそれぞれ区別する。関連するアプリ・Item・可視性の保持先を、同じ実装を通るというだけで廃止しない。
