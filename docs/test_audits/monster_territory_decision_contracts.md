# 縄張り帰還判断の監査

## 目的と範囲

`MonsterBehaviorStateMachine.should_return_to_territory` が、直線距離で半径を超えた場合だけ帰還を要求することを検査する。従来の7宣言はすべて軸上座標だったため、距離方式を取り違えたり、半径ちょうどで帰還するよう変えても成功していた。

- 元7宣言: R6（保持）、F1（検査補強）、C0、D0
- 変更後も7宣言。F1の1行を4行にして、対象の実行件数は7→10
- 試験ファイル全体は29宣言のまま、実行件数35→38。行数642→654、差分+17/-5
- 製品変更0、共通支援の変更0
- 対象ファイル: `tests/domain/monster/service/test_monster_behavior_state_machine.py`

この変更は被弾判断13の [#1719](https://github.com/Motifman/llm-rpg/pull/1719) に依存する。基準は同PRのhead `d433f8b75c75eeb3da107d12e825bc5cf53d4870`、tree `22c70bc4be66764af0e43aea8b53150658e0ed90`。#1719が整理した10宣言16件と文書は不変であり、今回の完了計数に含めない。同ファイルの対象外22宣言はクラス本文・入力・ASTを保存した。

## 契約の所有者と根拠

帰還要否のboolは判断サービスが所有する。`MonsterAggregate.apply_territory_return_if_needed` は出現・生存を確認し、サービスの判断に従ってRETURNへの変更、追跡の解除、状態変更通知を行う。`MonsterBehaviorCoordinator.process_actor_behavior` は通常の行動遷移を適用した後、実actorの座標を集約へ渡す。

集約の既存試験は範囲内外の適用と未出現時の拒否、`MonsterBehaviorState.with_territory_return` の既存試験はRETURN・対象/位置の消去・初期位置/巡回位置の保持を検査する。この別の責務は残し、サービスの判断表をそこで繰り返さない。

共有座標型は直線距離、マンハッタン距離、チェビシェフ距離（各軸の差の最大値）を提供する。その算術試験だけでは、モンスターの判断が誤った方式を選ぶ変更を検出できない。

抽出履歴 [3eca42d7](https://github.com/Motifman/llm-rpg/commit/3eca42d7dc8eec5d8879c28cea6d345277f45bef) の変更前集約にも、直線距離と厳密な `>` がある。追加した境界行はこの既存規則を検査し、製品仕様は変えない。ただし半径0の無効化は抽出時のサービス/試験で追加されたもので、抽出前から全条件が同じだったとは扱わない。既存の0無効化試験はそのまま残す。

## 補強した距離境界

F1を `test_return_decision_uses_euclidean_radius_boundary` へ改名した。全行がCHASE、初期位置(0,0,0)、正の半径で、無関係な拒否条件が距離判断を隠さない。

| 行 | actor座標 | 半径 | 帰還要求 | 意味 |
|---|---|---:|---|---|
| original_inside | (2,0,0) | 10 | False | 元の入力とassertを保持 |
| diagonal_inside | (3,3,0) | 5 | False | 直線距離√18は範囲内だが、マンハッタン距離6は範囲外 |
| exact_radius | (3,4,0) | 5 | False | 直線距離5は半径ちょうどで、超過していない |
| diagonal_outside | (4,4,0) | 5 | True | 直線距離√32は範囲外だが、チェビシェフ距離4は範囲内 |

期待値は固定boolで表に記述し、製品の距離関数や判断結果から生成しない。`is expected` により、元と同じくboolそのものを比較する。

## 元7宣言の台帳

すべて `TestMonsterBehaviorStateMachineShouldReturnToTerritory` 内。

| 元宣言 | 判定 | 保持する入力・契約と保持先 |
|---|---|---|
| test_returns_false_when_territory_radius_none | R | CHASE、座標(100,0,0)、初期位置(0,0,0)、半径NoneでFalse。無変更 |
| test_returns_false_when_initial_position_none | R | CHASE、座標(100,0,0)、初期位置None、半径5でFalse。無変更 |
| test_returns_false_when_not_chase_or_enrage | R | 座標(100,0,0)、初期位置(0,0,0)、半径5でIDLE/FLEE/SEARCH/RETURN各False。既存4状態を無変更 |
| test_returns_true_when_outside_radius_chase | R | CHASE、座標(10,0,0)、初期位置(0,0,0)、半径5でTrue。無変更 |
| test_returns_true_when_outside_radius_enrage | R | ENRAGE、座標(10,0,0)、初期位置(0,0,0)、半径5でTrue。無変更 |
| test_returns_false_when_inside_radius | F | 元の座標(2,0,0)/半径10/CHASEでFalseを距離境界表のoriginal_inside行へ保持 |
| test_returns_false_when_territory_radius_zero | R | CHASE、座標(100,0,0)、初期位置(0,0,0)、半径0でFalse。無変更 |

設定欠損、対象状態、半径0は独立した拒否条件であり、軸上の範囲内外試験では代替できない。元の拒否状態4種をPATROLまで検査済みとは主張しない。負半径は製品テンプレートが拒否しており、今回新たな受理仕様を加えない。

## 検証

- 未編集の正式基準11件成功: 対象7＋集約3＋値型1、重複nodeidなし
- 最初の基準起動は集約の親クラス名の誤指定で収集0件・終了コード4。これは成功基準にも製品失敗にも含めず、ASTで正しいクラス階層を確認して別名で再実行した
- 変更後の対象10件成功
- 復元後の最終42件成功: 対象10＋同ファイル対象外28＋集約3＋値型1。42件すべて一意、失敗/エラーなし
- Python3.10.22 / pytest8.4.1、自身のsrcを優先するオフライン実行。旧新の各対照は未使用のpycache領域を使い直列実行
- ruff0.16.8、git diff --check成功
- 全リポジトリ試験、公開コミットのCI、マージはこのローカル検証には含まない

### 旧新対照

製品の縄張り判断メソッドだけを一時変更し、同じ対象クラスの旧7件と新10件を比較した。

| 意図的な変更 | 旧 成功/失敗 | 新 成功/失敗 | 検査するもの |
|---|---:|---:|---|
| 直線距離をマンハッタン距離へ変更 | 7/0 | 8/2 | diagonal_insideとexact_radiusで誤った帰還要求を検出 |
| 半径比較の > を >= へ変更 | 7/0 | 9/1 | exact_radiusの等値を区別 |
| 直線距離をチェビシェフ距離へ変更 | 7/0 | 9/1 | diagonal_outsideの範囲外を区別 |
| 元の(2,0,0)/半径10/CHASEだけTrueにする | 6/1 | 9/1 | 旧insideと新original_insideで元入力の保持を確認 |
| 比較を半径 < 距離の向きで表現 | 7/0 | 10/0 | 意味を保つ変更で旧新とも成功 |

3目的変異は旧で成功し、新の狙った行のbool比較で失敗した。元入力の保存対照は旧新とも失敗するため、新しい検出力には数えない。構築エラーや別の拒否条件で落ちた結果はない。4変異と意味を保つ変更1件を旧新で計10回実行し、終了後に1601製品.pyと変異用試験を完全復元してhashを照合した。

## 保留範囲

今回の7以外の残り57宣言は完了扱いにしない。同tickのENRAGE/FLEE適用で最終状態と通知をどう一致させるかは、対象外の遷移適用試験を変更せず、別の製品判断として保留する。
