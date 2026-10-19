# 被弾時の判断契約の監査

## 目的と範囲

`MonsterBehaviorStateMachine.compute_attacked_transition` の被弾判断を、HP閾値ちょうど、待ち伏せ範囲ちょうど、距離方式の取り違えまで区別して検査する。返却値を自前で構築して確認する3宣言は、実際の判断結果を確認する主試験へ移した。

- 元13宣言: R7（保持）、F3（検査補強）、C3（主試験へ移管）、D0
- 変更後の対象: 10宣言、パラメータ展開16件
- 試験ファイル全体: 32→29宣言、実行行は32→35件。対象外19宣言は本文・入力・AST不変
- 試験行数: 646→642、差分+57/-61。製品変更0、新しい共通支援ファイル0
- 基準main: `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`
- 対象ファイル: `tests/domain/monster/service/test_monster_behavior_state_machine.py`

集約反応29宣言（#1713）と追跡値12宣言（#1717）は別の範囲。今回13が完了しても、行動試験118宣言の残り64を完了扱いにしない。

## 所有者と実際の入口

製品所有者は `src/ai_rpg_world/domain/monster/service/monster_behavior_state_machine.py` の被弾計算と `AttackedTransitionResult`。

`CombatAggroHandler` は実ヒットイベントから攻撃者のID・座標を取り、`MonsterAggregate.record_attacked_by` を呼ぶ。集約は生存と出現状態を確認した後、生態、HP割合、成長に応じた逃走閾値と追跡許可、現在の行動状態、初期位置、待ち伏せ範囲を判断サービスへ渡す。

返却値は `MonsterBehaviorState.with_attacked` が行動状態・対象・位置へ適用し、集約が追跡の解除/同期に用いる。関連する集約の接続試験は残す。handlerの保存・配信や共有座標型の計算をこの試験へ移したわけではない。

抽出履歴 [3eca42d7](https://github.com/Motifman/llm-rpg/commit/3eca42d7dc8eec5d8879c28cea6d345277f45bef) を確認した。抽出前の集約もHP割合<=閾値とマンハッタン距離>待ち伏せ範囲を使用しており、今回新しい製品仕様を導入していない。

## 境界の検査

### HP割合

NORMAL、現在IDLE、追跡許可ありで、他の生態分岐が先に拒否しない入力を使う。閾値0.2に対し元のHP0.1を残し、等値0.2と直上0.21を追加した。

| HP割合 | 結果 | 追跡解除 | 追跡同期 |
|---:|---|---|---|
| 0.1 | FLEE | True | False |
| 0.2 | FLEE | True | False |
| 0.21 | CHASE | False | True |

各行で遷移あり、攻撃者ID200、座標(5,5,0)も確認する。期待値は表の定数で与え、製品の判断や返却値コンストラクタから作らない。

### 待ち伏せの距離

初期位置(0,0,0)、範囲5、HP十分、追跡許可ありの入力を使う。

- 元の範囲外(100,0,0)を残し、対角(3,3,0)を追加。マンハッタン距離6は範囲外だが、直線距離√18は範囲内なので、方式の取り違えを検出する
- 元の範囲内(2,0,0)を残し、(3,2,0)を追加。マンハッタン距離5ちょうどは追跡を許可する
- 初期位置None、範囲Noneの既存入力は独立して残す。範囲Noneの旧試験が確認するのは `no_transition=False` であり、stateまで確認済みとは主張しない

## 返却値の構築試験から移したもの

- 変更しない結果の6項目を、PATROL_ONLYの実計算へ集約。対象None、位置None、解除False、同期Falseも明示する
- FLEEの元対象99/座標(1,2,0)を、FLEE_ONLY主試験の追加行へ移す。既存の対象200/座標(5,5,0)を置換しない
- CHASEの元対象100/座標(5,5,0)を、高HP NORMAL主試験の追加行へ移す。こちらも既存200の行を残す
- C3の全assertを移した後に元宣言を除く。製品の返却値型は実集約が使うため削除しない

元の構築クラスの説明は不変性にも言及していたが、実際の3試験は属性代入拒否を検査していなかった。その保証を移管したとは扱わない。

## 元13宣言の台帳

すべて上記対象ファイル内。表中の `Compute` は `TestMonsterBehaviorStateMachineComputeAttackedTransition` の略。

| 元宣言 | 判定 | 保持先・理由 |
|---|---|---|
| TestAttackedTransitionResult.test_create_no_transition | C | Compute.TestNormalCases.test_patrol_only_returns_no_transitionへ6項目を移管 |
| TestAttackedTransitionResult.test_create_flee_transition | C | Compute.TestNormalCases.test_flee_only_returns_flee_clear_pursuitへ元99の入力と6項目を移管 |
| TestAttackedTransitionResult.test_create_chase_transition_with_sync | C | Compute.TestNormalCases.test_normal_hp_high_allow_chase_returns_chaseへ元100の入力と解除/同期の検査を移管 |
| Compute.TestNormalCases.test_patrol_only_returns_no_transition | R | 巡回専用の生態では被弾遷移しない |
| Compute.TestNormalCases.test_flee_only_returns_flee_clear_pursuit | R | HP十分でも逃走専用の生態はFLEEとなり追跡を解除 |
| Compute.TestNormalCases.test_normal_hp_low_returns_flee | F | test_normal_hp_boundary_selects_flee_or_chaseへ改名し、元低HPを含む3行で境界と対象/位置/同期を検査 |
| Compute.TestNormalCases.test_normal_hp_high_allow_chase_returns_chase | R | HP十分・追跡許可ありでCHASEと同期 |
| Compute.TestNormalCases.test_normal_enrage_state_does_not_chase | R | 既にENRAGEでHP十分なら怒り状態を保ち同期する |
| Compute.TestNormalCases.test_normal_allow_chase_false_does_not_chase | R | 追跡許可なしならIDLEを保ち対象と同期を更新 |
| Compute.TestAmbush.test_ambush_out_of_range_returns_no_transition | F | 元の遠距離を残して対角の範囲外拒否を追加 |
| Compute.TestAmbush.test_ambush_in_range_returns_chase | F | 元の範囲内を残して距離等値の許可を追加 |
| Compute.TestAmbush.test_ambush_without_initial_position_treats_as_chase | R | 初期位置不明では範囲制限せずCHASE |
| Compute.TestAmbush.test_ambush_without_range_treats_as_chase | R | 範囲未指定では遷移拒否しないという元の保証を保持 |

## 別件として保留した仕様判断

`TestMonsterBehaviorStateMachineApplyTransition.TestFleeFromThreat.test_flee_with_apply_enrage_emits_both` は変更していない。同tickのENRAGE/FLEE適用で最終状態と通知をどう一致させるかは別の製品判断であり、現在の通知を新しい正解として固定しない。

今回残すENRAGE行は「既にENRAGE、HP十分」の被弾判断であり、同tickのphase発火とFLEE併存ではない。製品修理、Issue作成、成長時のHP/MP判断を含めない。

## 検証

- 未編集基準37件成功: 対象13＋同ファイルの対象外19＋行動値の結果適用2＋集約接続3
- 変更後の対象16件成功
- 製品復元後の最終40件成功: 対象16＋関連24。失敗・エラー・重複nodeidなし
- Python3.10.22 / pytest8.4.1、自身のsrcを優先するオフライン実行。各対照で未使用のpycache領域を使い直列実行
- ruff0.16.8、git diff --check成功
- 全リポジトリ試験、公開コミットのCI、マージはこのローカル検証には含まない

### 旧新対照

| 意図的な変更 | 旧 成功/失敗 | 新 成功/失敗 | 区分 |
|---|---:|---:|---|
| HPの<=を<へ変更 | 13/0 | 15/1 | 等値の検出補強 |
| HP閾値を固定0.5へ変更 | 13/0 | 15/1 | 指定閾値直上の検出補強 |
| AMBUSHを直線距離へ変更 | 13/0 | 15/1 | 距離方式の検出補強 |
| AMBUSHの>を>=へ変更 | 13/0 | 15/1 | 距離等値の検出補強 |
| 通常低HPだけ対象IDをNoneにする | 13/0 | 14/2 | 対象保持の検出補強 |
| 通常低HPだけ位置をNoneにする | 13/0 | 14/2 | 位置保持の検出補強 |
| 通常低HPだけ同期Trueにする | 13/0 | 14/2 | 逃走時の同期抑止の検出補強 |
| 変更なし結果の対象既定を壊す | 12/1 | 15/1 | C3保存 |
| 変更なし結果の位置既定を壊す | 12/1 | 15/1 | C3保存 |
| 変更なし結果の解除既定を壊す | 12/1 | 15/1 | C3保存 |
| 変更なし結果の同期既定を壊す | 12/1 | 15/1 | C3保存 |
| FLEE_ONLYの対象をNoneにする | 12/1 | 14/2 | C3保存 |
| FLEE_ONLYの位置をNoneにする | 12/1 | 14/2 | C3保存 |
| FLEE_ONLYの解除をFalseにする | 12/1 | 14/2 | C3保存 |
| FLEE_ONLYの同期をTrueにする | 12/1 | 14/2 | C3保存 |
| CHASEの解除をTrueにする | 12/1 | 13/3 | C3保存 |
| CHASEの同期をFalseにする | 12/1 | 13/3 | C3保存 |
| HP比較の左右を交換し>=で表す | 13/0 | 16/0 | 意味を保つ変更 |

F3に対する7改善変異は、等値/直上/対角の該当行、または追加した対象/位置/同期assertで失敗した。PATROLへ移した4項目も個別に壊し、それぞれ該当assertで失敗した。構築エラーや無関係な拒否を検出として数えていない。

10保存変異は旧試験も失敗するため、新しい検出力に数えない。17変異＋意味を保つ変更1件を旧新で計36回実行。終了後に1601製品.pyと変異用試験を完全復元し、hashを照合した。
