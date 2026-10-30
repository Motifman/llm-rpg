# モンスター追跡値の契約監査

## 目的と範囲

`MonsterPursuitState` の元12宣言を調べ、追跡同期とプロパティ取得を同じ主試験で確認する形へまとめた。現在の対象スナップショットがない追跡状態で、最後の観測情報を古い値のまま返す退行も検出する。

- 対象: `tests/domain/monster/value_object/test_monster_pursuit_state.py`
- 判定: R6（保持）、F1（検査補強）、C5（先に保持先へ移して統合）、D0
- 変更後: 7宣言・パラメータ展開9件。試験328→274行、差分+40/-94
- 製品変更0、新規試験支援ファイル0。製品の不具合修理は含まない
- 基準main: `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`
- 前の集約反応29宣言（#1713）とは別の範囲。行動試験118宣言のうち、この12以外の後続77宣言を完了扱いにしない

## 責務と既存の証拠

所有者は `src/ai_rpg_world/domain/monster/value_object/monster_pursuit_state.py`。集約は同期時にactor・対象・現在の位置・観測tickを渡し、見失ったときは現在のスナップショットを残して最後の既知情報を更新する。解除では追跡なしの新しい状態を受け取る。

- `MonsterAggregate._sync_active_pursuit_state` が `with_sync` を呼ぶ
- `MonsterAggregate._preserve_pursuit_last_known` が `with_preserve_last_known` を呼ぶ
- `MonsterAggregate._clear_pursuit_state` が `cleared` を呼ぶ
- 公開取得と追跡失敗処理が、対象・スナップショット・最後の既知情報を読む
- `sqlite_monster_state_codec._build_pursuit_state` はスナップショットなし・最後の既知情報ありの状態も復元できる。この経路は製品ソースで確認したもので、今回SQLite試験を追加実行して実証したという意味ではない
- 共有 `PursuitState` のID整合性や「スナップショットか最後の既知情報の一方が必要」という検証は共有値の責務として残す

抽出履歴は [b5ae027e](https://github.com/Motifman/llm-rpg/commit/b5ae027e80d2c02fe851f1e7739ee21bd18aa0e8)。値への責務分離として導入された。集約のSEARCH保持・再捕捉の回帰試験も別に残っており、その接続契約を値型の試験だけで置き換えない。

## 統合で保持したもの

1. 追跡省略と明示的な `pursuit=None` を生成主試験の別行にする
2. 同期結果が元の空状態とは別実体であることと、元の空状態が非追跡のままであることを両方残す
3. 同期主試験の元入力（actor1001、対象2001、spot2、座標(10,20,0)、tick50）を残す
4. プロパティ試験の元入力（actor5000、対象5001、spot1、座標(0,0,0)、tickなし）を同期主試験の別行にする
5. 対象ID、スナップショットの非Noneと対象ID、最後の既知情報の非Noneを明示する。同期結果の全値一致も残す
6. 空の `cleared()` が新しい実体を返すという既存の検査を変更しない

スナップショット保持の3分岐は統合しない。既存スナップショットあり、追跡自体なし、追跡はあるがスナップショットなしは、それぞれ別の入力契約である。

## 弱かった検査の補強

既存スナップショットなしの行は、代替スナップショットだけを確認していた。最後の既知情報を更新せずに返しても成功していたため、同じ行へ新しい最後の既知情報の全値一致を追加した。

- 旧状態: 対象4001、spot3、座標(1,1,0)、観測tickなし
- 新しい情報: 同じ対象・spot、座標(7,8,0)、観測tick200
- 代替スナップショットの元assertは残す
- IDを整合させ、last_knownを持たせるため、共有値の検証例外で意図した更新経路が隠れない

## 元12宣言の判定

表内の名前はすべて対象ファイル内の完全なクラス名・関数名。保持先の本文にはパラメータ行も含む。

| 元宣言 | 判定 | 保持先・理由 |
|---|---|---|
| TestMonsterPursuitStateCreation.test_empty_state_has_no_pursuit | R | 生成の主試験。既定と明示Noneの2行で全取得値を確認 |
| TestMonsterPursuitStateCreation.test_empty_state_with_explicit_none | C | 上のexplicit_none行へ入力とactive=Falseを移管 |
| TestMonsterPursuitStateCleared.test_cleared_from_empty_returns_empty | R | 空の解除と新実体の保証を変更せず保持 |
| TestMonsterPursuitStateCleared.test_cleared_from_active_returns_empty | R | 活動中の追跡解除を保持 |
| TestMonsterPursuitStateWithSync.test_with_sync_creates_active_pursuit | R | 同期・取得・元状態維持の主試験。元2組の入力を維持 |
| TestMonsterPursuitStateWithSync.test_with_sync_returns_new_instance | C | 同期主試験へis notと元emptyの非追跡状態を両方移管 |
| TestMonsterPursuitStateWithPreserveLastKnown.test_preserve_keeps_existing_target_snapshot | R | 異なる代替候補より既存スナップショットを優先し、最後の既知情報を更新 |
| TestMonsterPursuitStateWithPreserveLastKnown.test_preserve_uses_fallback_when_no_existing | R | 追跡自体なしの代替採用を保持 |
| TestMonsterPursuitStateWithPreserveLastKnown.test_preserve_uses_fallback_when_existing_has_no_snapshot | F | 代替採用に加えて新しい最後の既知情報を確認 |
| TestMonsterPursuitStateProperties.test_target_id_delegates_to_pursuit | C | 同期主試験のunknown_observation_tick行へ対象5001の一致を移管 |
| TestMonsterPursuitStateProperties.test_target_snapshot_delegates_to_pursuit | C | 同じ行へスナップショット非Noneと対象5001の一致を移管 |
| TestMonsterPursuitStateProperties.test_last_known_delegates_to_pursuit | C | 同じ行へlast_known非Noneを移管 |

## 実施した検証

- 未編集基準: 対象12＋関連13＝25件成功
- 変更後の単独試験: 9件成功
- 復元後の最終試験: 対象9＋関連13＝22件成功、失敗・エラー・重複nodeidなし
- 関連13は共有 `PursuitState` の6件と、集約親クラスの追跡接続7件。Coreの継承による二重収集を避けて指定し、監査完了数へ加算しない
- Python3.10.22 / pytest8.4.1、対象srcを優先するオフライン実行。各対照は新しいpycache領域を使用
- ruff0.16.8と `git diff --check` は成功
- 全リポジトリ試験、公開コミットのCI、マージはこのローカル検証に含まない

最初の基準起動は関連nodeidの指定漏れでcollectionに失敗し、実試験0件だった。起動引数だけを訂正した25件成功を正式な基準とした。

### 意図的な変更との旧新対照

| 対照 | 旧 成功/失敗 | 新 成功/失敗 | 分類 |
|---|---:|---:|---|
| 既存スナップショットなしのときだけ古いlast_knownを返す | 12/0 | 8/1 | 検出補強 |
| 空の状態を追跡中と判定する | 7/5 | 3/6 | 保持確認 |
| 同期が元の実体を書き換えてそのまま返す | 11/1 | 7/2 | 別実体の保持確認 |
| 同期が新実体を返すが元emptyも書き換える | 11/1 | 7/2 | 元状態維持の保持確認 |
| 対象IDの取得でactorを返す | 10/2 | 7/2 | 保持確認 |
| 現在スナップショットの取得でNoneを返す | 7/5 | 4/5 | 保持確認 |
| 最後の既知情報の取得でNoneを返す | 8/4 | 4/5 | 保持確認 |
| clearedをdataclasses.replaceで新しい空状態を返す形へ変更 | 12/0 | 9/0 | 意味を保つ変更 |

補強の失敗位置は追加した `updated.last_known == new_last_known`。座標と観測tickの差で失敗し、構築エラーや別のガードの失敗ではない。同期の2対照も、別実体のassertと元emptyのassertがそれぞれ独立して失敗した。

保存用の6変異は旧試験も失敗するため、新しい検出力に数えない。7変異と意味を保つ変更1件を旧新で計16回実行し、終了後は1601製品.pyのhashを全件照合して完全復元した。
