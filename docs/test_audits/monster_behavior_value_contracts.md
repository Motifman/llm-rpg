# 行動状態の値型契約の監査

## 目的と範囲

`MonsterBehaviorState` の生成・復元・値の更新・同一性を扱う19宣言を監査した。初期値やコンストラクタの確認を一律に削らず、公開契約として意味のあるものを保持する。対象IDが入力と出力で同じ、リセット前からカウンタが0、新しい実体だけを見て元値の変更を見ない、という3種類の検査不足を補強した。

- 元19宣言: R15（保持）、F3（検査補強）、C1（同じ責務の表へ統合）、D0
- 変更後18宣言、パラメータ展開27件。元の全入力と全assertを保持
- 対象 `tests/domain/monster/value_object/test_monster_behavior_state.py`
- 試験行数346→409、差分+107/-44。製品・共通支援の変更0
- 基準main `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`

先行する集約反応29（#1713）、追跡値12（#1717）、被弾判断13（#1719）、縄張り判断7（#1721）は別計上。今回19が完了しても残38宣言は未完とする。

## 所有者と保持した独立契約

値型は値の生成・適用・保持を所有する。集約は生死/出現の許可、追跡の接続、通知を所有し、SQLiteは保存と復元を所有する。似た状態を検査していても、この責務差は削除理由にならない。

- `create_idle` は集約の初期構築や出現時に使われ、IDLE、対象なし、既定のカウンタ0と初期位置を定める
- `from_parts` は実際のSQLite復元経路が使う。値の保持に加え、負の巡回/探索/失敗カウンタを0へ丸める
- 直接コンストラクタは負カウンタを `MonsterStatsValidationException` で拒否する。復元時の丸めとは異なる契約であり、各項目の拒否と理由を残す
- `with_attacked`、`with_transition`、帰還/出現/対象消去、巡回更新は実集約が呼ぶ。巡回点到達のhandlerは集約経由で点数を渡す
- `with_attacked(no_transition=True)` の同じ実体の返却は公開説明に明記されている。集約が先にこの条件を返すことを理由に、値型の公開保証を削らない
- 変更時の新しい実体も公開契約。IDLEへIDLEを適用する例や、元から空の対象を消す例の `is not` も維持する

抽出 [67392cb8](https://github.com/Motifman/llm-rpg/commit/67392cb89a7117a55a9859ad1aaa89e64f8b4a7f) と改名 [35cd329f](https://github.com/Motifman/llm-rpg/commit/35cd329ff56a09686200d1939e5633b0fa1158ca) を確認した。不変の値型、新しい実体、変更なしのself返却、復元時の丸めは抽出時から存在する。`from_legacy` から `from_parts` への改名を、別の受理仕様の導入とは扱わない。

## 補強した3契約

### 出力が別の対象を指す場合

元のCHASE状態は対象3001、既知位置(1,1,0)。SEARCH/位置(2,2,0)の出力で、元の対象3001行を残し、対象3002への変更行を加えた。出力Noneによる対象/位置消去の別試験は変更していない。

「非Noneの出力なら古い対象を残すが、Noneなら消す」という退行を区別できる。対象を常に残すだけの変異は旧None消去行も失敗するため、改善の証拠には使わなかった。

### リセットする前に値が存在する場合

SEARCH、対象5001、既知位置(1,1,0)、初期位置(0,0,0)、巡回2から、新初期位置(100,200,0)へ出現時リセットする元入力を残す。

| 行 | リセット前の探索タイマー | リセット前の失敗回数 | 結果 |
|---|---:|---:|---|
| original_zero_counters | 0 | 0 | 元の全assertを保持 |
| nonzero_counters | 5 | 3 | IDLE、対象/位置なし、新初期位置、巡回/探索/失敗すべて0 |

操作前に指定した2値へ到達していることも確認する。初めから0だったために、リセットを省略しても成功する状態を避けた。

### 新しい結果を返しても元の状態を壊さないこと

元の `create_idle(initial_position=(0,0,0))` に対する次の6操作を、個別の行へ分けた。

1. 被弾結果FLEE/対象1/位置(1,1,0)/追跡解除True/同期Falseの適用
2. IDLE/対象None/位置Noneの出力適用
3. 縄張り帰還
4. 初期位置(1,1,0)への出現時リセット
5. 元から空の対象の消去
6. 点数3での巡回更新

全行で元の `is not` を残し、操作後も元状態の公開11項目が固定初期値のままであることを追加確認する。期待値はIDLE、対象/既知位置None、初期位置(0,0,0)、3カウンタ0、4拡張値Noneという定数で、製品の生成関数から作らない。

保証はこの初期状態と既存6操作に限定する。非既定のスポット拡張値の保持、全更新メソッドの網羅、frozen属性への代入拒否までは検査済みとしない。

## 統合した非正の巡回点数

`test_nonpositive_count_returns_self` に次の全入力を残してから、負点数の別宣言を除いた。

| 生成経路 | 巡回位置 | 点数 | 元からある保証 |
|---|---:|---:|---|
| create_idle() | 0 | 0 | result is state |
| create_idle() | 0 | -1 | result is state |
| from_parts(IDLE,None,None,None,patrol_index=1) | 1 | -5 | result is state |

負数というだけで同じ入力とは扱わず、index1/count-5をindex0/count-1で代替しない。初期位置None、探索/失敗0と生成経路も保持した。

## 元19宣言の台帳

以下のクラス名は共通の `TestMonsterBehaviorState` 接頭辞を省略する。

| 元宣言 | 判定 | 保持先・理由 |
|---|---|---|
| CreateIdle.test_creates_idle_state_with_defaults | R | IDLE、対象/位置/初期位置None、3カウンタ0を保持 |
| CreateIdle.test_creates_idle_with_initial_position | R | 指定初期位置(10,20,0)を保持 |
| FromParts.test_builds_from_individual_fields | R | CHASE/対象1001/既知(5,6,0)/初期(1,2,0)/巡回2/探索5/失敗1を復元 |
| FromParts.test_clamps_negative_values_to_zero | R | 巡回-1/探索-2/失敗-1を0へ丸める独立契約 |
| Validation.test_rejects_negative_patrol_index | R | 巡回-1をドメイン例外と該当項目の理由で拒否 |
| Validation.test_rejects_negative_search_timer | R | 探索-1を同様に拒否。他カウンタは0でガードを分離 |
| Validation.test_rejects_negative_failure_count | R | 失敗-1を同様に拒否。他カウンタは0でガードを分離 |
| WithAttacked.test_no_transition_returns_self | R | 変更なしの結果では同じ実体を返す |
| WithAttacked.test_applies_transition_when_not_no_transition | R | FLEE/対象2001/位置(10,10,0)へ適用し初期位置/巡回を保持、新実体 |
| WithTransition.test_applies_transition_output | F | 元出力3001を残し、同じ主試験へ3002の対象変更行を追加 |
| WithTransition.test_handles_none_target_and_position | R | 存在する対象3001と位置(1,1,0)をNoneへ消す |
| WithTerritoryReturn.test_sets_return_and_clears_target | R | RETURNと対象/位置消去、初期位置/巡回3を保持 |
| WithSpawnReset.test_resets_to_idle_with_initial_position | F | 元探索0/失敗0を残し、探索5/失敗3をリセットする行を追加 |
| WithTargetCleared.test_clears_target_keeps_state | R | 対象6001/位置(3,4,0)を消しSEARCH/初期位置/巡回を保持 |
| AdvancePatrolIndex.test_advances_index | R | index1/count4で2へ進み、新実体を返す |
| AdvancePatrolIndex.test_wraps_around_at_count | R | index2/count3で0へ周回する |
| AdvancePatrolIndex.test_zero_count_returns_self | R | test_nonpositive_count_returns_selfへ改名し、元create_idleの0/-1を保持 |
| AdvancePatrolIndex.test_negative_count_returns_self | C | 同じ保持先へfrom_partsのindex1/count-5とis selfを移管 |
| Immutability.test_all_mutations_return_new_instance | F | test_updates_preserve_original_state_and_return_new_instanceの6行へ全旧操作/is notを保持し、元11項目の初期値保持を追加 |

## 検証

- ASTで全selectorを検証してから、未編集基準25件が初回で成功。対象19＋集約5＋SQLite1
- 変更後の対象27件成功、製品復元後の最終33件成功（対象27＋同じ関連6）
- 最終33件は全て一意で、失敗・エラー・除外なし。関連6をこの19宣言の完了数へ加算しない
- Python3.10.22 / pytest8.4.1、自身のsrcを優先するオフライン実行。各旧新対照は未使用のpycache領域を使い直列実行
- ruff0.16.8、git diff --check成功
- 製品1601ファイルと変異用試験は基準bytesへ完全復元して照合
- 全リポジトリ試験、公開コミットのCI、マージはこのローカル検証には含まない

### 旧新対照

| 意図的な変更 | 旧 成功/失敗 | 新 成功/失敗 | 区分 |
|---|---:|---:|---|
| 非Noneの出力対象だけ旧対象を残す | 19/0 | 26/1 | 対象変更の改善 |
| 出現時リセットで探索だけ元値を残す | 19/0 | 26/1 | リセットの改善 |
| 出現時リセットで失敗回数だけ元値を残す | 19/0 | 26/1 | リセットの改善 |
| 被弾適用が元探索タイマーを書き換えて別実体を返す | 19/0 | 26/1 | 元値保持の改善 |
| 出力適用が同様に元値を書き換える | 19/0 | 26/1 | 元値保持の改善 |
| 縄張り帰還が同様に元値を書き換える | 19/0 | 26/1 | 元値保持の改善 |
| 出現時リセットが同様に元値を書き換える | 19/0 | 26/1 | 元値保持の改善 |
| 対象消去が同様に元値を書き換える | 19/0 | 26/1 | 元値保持の改善 |
| 巡回更新が同様に元値を書き換える | 19/0 | 26/1 | 元値保持の改善 |
| index0/count0だけ別実体を返す | 18/1 | 26/1 | 同一実体の保存 |
| index0/count-1だけ別実体を返す | 18/1 | 26/1 | 同一実体の保存 |
| index1/count-5だけ別実体を返す | 18/1 | 26/1 | C1の保存 |
| 元の被弾入力だけselfを返す | 18/1 | 26/1 | 新実体保証の保存 |
| IDLE→IDLE出力だけselfを返す | 18/1 | 26/1 | 新実体保証の保存 |
| 元の初期IDLEへの帰還だけselfを返す | 18/1 | 26/1 | 新実体保証の保存 |
| 元のIDLE/(1,1,0)へのresetだけselfを返す | 18/1 | 26/1 | 新実体保証の保存 |
| 元から空の対象消去だけselfを返す | 18/1 | 26/1 | 新実体保証の保存 |
| 元のindex0/count3だけselfを返す | 18/1 | 26/1 | 新実体保証の保存 |
| 巡回加算を1+indexの順序へ交換 | 19/0 | 27/0 | 意味を保つ変更 |

改善9は旧で成功し、新の狙った1行で失敗した。元値保持の6変異は正しい新実体の生成後に元の探索タイマーだけを壊すため、新実体確認と元値確認を切り分けている。保存9は旧新とも失敗し、検出力の改善件数には含めない。18変異＋意味を保つ変更1件を旧新で計38回実行し、構築エラーや無関係な拒否による失敗を数えていない。

## 範囲外

同tickのENRAGE/FLEE通知、成長時のHP/MP、今回の初期値以外での全スポット状態保持、全属性の代入拒否はこの監査で解決したとは扱わない。製品修理やIssue作成も含めない。
