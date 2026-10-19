# HitBox の衝突・形状・速度・設定に関する試験監査

## 範囲と結果

基準は `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。次の4ファイルの全19宣言を調べた。

- `tests/domain/combat/service/test_hit_box_collision_service.py`
- `tests/domain/combat/service/test_hit_box_config_service.py`
- `tests/domain/combat/value_object/test_hit_box_shape.py`
- `tests/domain/combat/value_object/test_hit_box_velocity.py`

17宣言を保持（R）、2宣言を修理（F）した。統合（C）・削除（D）は0。
製品コードと共通の試験支援は変更していない。廃止するファイル・試験層・試験専用の製品コードもない。
宣言数は19のまま、表の展開後は19→21件。試験行数は251→308行（75行追加・18行削除）。速度改善は主張しない。

修理したのは、飛行能力を無視しても成功する試験と、マップ外の判定を非公開関数だけで確認していた試験。
発動・寿命を扱った [#1695](https://github.com/Motifman/llm-rpg/pull/1695) の集約2ファイル・元31宣言は別の監査範囲であり、今回の変更・完了件数へ含めない。

## 実際の呼出しと試験の主担当

`WorldSimulationDefaultDependencies.resolve` が設定・衝突サービスを供給する。
`WorldSimulationHitBoxUpdater.update_hit_boxes` は速度別の細分数と衝突予算を読み、集約の `on_tick` のあとで `resolve_collisions` を呼ぶ。

衝突サービスは、集約が返す被覆座標ごとに地形を先に調べ、障害物通知と失効を処理してから対象を検索する。
使用した判定回数と予算による停止の有無を呼出側へ返す。この実マップ・実集約との境界は衝突サービスの試験が担当する。
applicationの試験は保存・通知配送・細分更新の接続を担当し、正確な返却計数、2対象への連続命中、飛行能力の有無、未存在タイルの分岐をすべて代替するものではない。

形状の `to_absolute` と速度の `is_stationary` / `apply_to_precise` は集約が使う。
形状・速度の構築はスキル回転とSQLiteの復元でも使われる。
一方、`get_substeps_per_tick`、形状生成器の `single_cell` / `cross`、速度の `apply_to` には現在の製品直接呼出しを見つけなかった。
公開操作として残る設定・形状の意味・座標変換を、呼出し数だけで試験専用と断定せず保持した。APIを廃止する変更は本監査に含めない。

十字形状の5座標は独立した期待値で確認する必要がある。集約側の複数セル試験は形状自身の相対座標から期待値を作るため、形状から腕を1本消す誤りは代替検出できない。
静止判定も同様で、速度0を誤って非静止と判定しても、位置更新側が同座標で打ち切るため、移動しないことだけでは公開判定値を証明できない。

## 飛行能力の修理と元入力の保持

元の試験は草地(0,1,0)から壁(1,1,0)へ速度(1,0,0)で進み、能力は `{FLY}`、衝突方針は `PASS_THROUGH` だった。
有効状態だけを見ていたため、飛行能力を無視して壁と判定しても、通過方針によって成功していた。

この元入力と生存の断言を表の1行目として残し、障害物通知の座標・方針、使用計数、失効通知なしを加えた。
草地はWALKを要求するため、FLYだけの元行では出発草地への通知が1件出る。一方、壁はFLYを許容するので壁への通知は出ない。

2行目は同じ経路・速度・時刻・寿命・予算で `{WALK, FLY}` と `DEACTIVATE` を指定する。
この場合は出発草地と壁の両方を通過し、障害物通知も失効通知も出ない。
既存の通常歩行 `{WALK}` と `DEACTIVATE` の試験は、同じ経路で壁に当たって失効する。2行目とはFLYの有無だけが違う対照となる。

FLYだけのままDEACTIVATEへ変えると、出発草地で先に失効して別理由の失敗になる。その変更はしていない。
通常歩行が壁に衝突しても生存する契約は、applicationの `test_tick_keeps_hitbox_active_when_obstacle_policy_pass_through` と集約の `test_record_obstacle_collision_pass_through_keeps_active` が引き続き担当する。

## マップ外判定を公開処理へ移す

元の試験は、初期座標(0,0,0)の静止判定と、別引数の正座標(10,10,0)を非公開補助へ渡して、障害物Trueだけを確認していた。

修理後も初期座標、静止速度、開始0、寿命10、全識別子とマップを保持する。
公開 `teleport_to(10,10,0)` のあとに静止 `on_tick(1)` を行い、被覆が元の判定対象(10,10,0)だけであることを確認してから `resolve_collisions` を呼ぶ。
これにより、途中の別のマップ外セルで失効した結果を元座標の証明として扱わない。

元の `PASS_THROUGH` 行は同じ座標の障害物通知1件・有効・失効通知なしを確認する。
追加した `DEACTIVATE` 行は同じ通知に加え、無効状態と理由 `obstacle_collision` の失効通知1件を確認する。
両行で使用計数1、予算停止Falseも確認する。
元試験は「マップ外なら必ず失効」とは主張していなかったため、通過方針の元行も残した。

## 全宣言の判断

以下は変更前の宣言名。Rは同じ宣言を変更せず保持。
Fは元入力を残して、順に `test_resolve_collisions_respects_movement_capabilities` と `test_resolve_collisions_treats_missing_tile_as_obstacle` の表へ修理した。

### `test_hit_box_collision_service.py`

| 宣言 | 判断 | 守る契約 | 検出する誤り・修理理由 |
| --- | --- | --- | --- |
| `test_resolve_collisions_detects_obstacle` | R | 通常歩行の判定が実マップの壁に達したとき、衝突計数を返し、上限停止ではなく障害物衝突で無効になる | 障害物検査を省略する、またはDEACTIVATEの通知接続を除く |
| `test_resolve_collisions_with_flying_capability_passes_wall` | F | 能力に合う地形は障害物とせず通過し、PASS_THROUGHは障害物に当たっても有効状態を保つ | 現試験はPASS_THROUGHのため、入力のFLYを無視して常に通常歩行で判定しても成功する |
| `test_resolve_collisions_detects_multiple_objects_in_path` | R | 2セルの移動経路上にいる別々の2対象を両方命中記録する | 終点だけを走査する、または最初の対象で走査を中断する |
| `test_resolve_collisions_respects_max_checks` | R | 衝突計数の予算1を超えず、残り走査があるとguard=Trueを返す | 予算比較を>へ変える、計数を増やさない、上限到達時の戻り値をFalseにする |
| `test_is_obstacle_coordinate_handles_out_of_bounds` | F | 正の座標でも実マップにタイルがなければ障害物として扱う | TileNotFoundExceptionを通行可能として扱う。現状のprivate直呼びはresolve_collisionsから検査・記録への接続欠落を捕捉しない |

### `test_hit_box_config_service.py`

| 宣言 | 判断 | 守る契約 | 検出する誤り・修理理由 |
| --- | --- | --- | --- |
| `test_get_substeps_per_tick_default` | R | 公開設定の既定細分数は4 | 既定値を4から変更する、getterが別値を返す |
| `test_get_substeps_per_tick_custom` | R | 公開設定に渡した正の細分数8を取得できる | 入力を無視して4固定にする |
| `test_substeps_per_tick_is_clamped_to_one_when_zero_or_negative` | R | 細分数0と負数-3は1へ切り上げる | ゼロのみ許容する、負数だけ切り上げを忘れる |
| `test_get_substeps_for_hit_box_uses_velocity_bands` | R | 速度0.25/1/2で低速2・通常4・高速8の細分数を選ぶ | 速度別の分岐を固定値へ置き換える、低速と高速の値を取り違える |
| `test_get_max_collision_checks_per_tick` | R | 衝突予算128の公開設定を返す | 入力予算を無視して既定512を返す |

### `test_hit_box_shape.py`

| 宣言 | 判断 | 守る契約 | 検出する誤り・修理理由 |
| --- | --- | --- | --- |
| `test_single_cell` | R | 単一セル形状を任意原点へ置くと、その原点だけを返す | 原点を足さない、余分なセルを加える |
| `test_cross` | R | 十字形状は中心と上下左右のちょうど5セルへ平行移動する | crossの片腕を削る・別位置へずらす、余分なセルを加える |
| `test_absolute_out_of_bounds_skips` | R | 原点(0,0)で十字の負x/負yを除外し、中心・右・上の3セルだけを返す | 負座標で例外を再送する、許容座標も一緒に除外する |
| `test_empty_fails` | R | 空の形状をHitBoxValidationExceptionで拒否する | 空配列の検証を除去する、組込みValueErrorへ変える |

### `test_hit_box_velocity.py`

| 宣言 | 判断 | 守る契約 | 検出する誤り・修理理由 |
| --- | --- | --- | --- |
| `test_zero_is_stationary` | R | zero()の公開静止判定はTrue | is_stationaryを常にFalseにする |
| `test_non_zero_is_not_stationary` | R | x方向の速度1は静止ではない | is_stationaryを常にTrueにする、比較演算の向きを誤る |
| `test_small_value_is_stationary_with_epsilon` | R | 丸め誤差程度の1e-12を静止として扱う | 全成分を厳密==0比較へ戻す |
| `test_apply_to_coordinate_with_step_ratio` | R | 整数座標への速度適用は比率0.5を掛け、x/y/zを整数投影する | step_ratioを無視する、丸めをroundへ変える、y成分を欠落させる |
| `test_apply_to_precise_position` | R | 小数速度を比率付きで3次元位置へ適用して端数を保つ | 整数化する、比率を無視する、y軸を更新しない |

速度の整数投影試験はz=0.5を0へ投影するため、z更新を省略する誤りはこの入力では検出しない。守れる範囲を過大に扱わない。

## 履歴

- [形状の導入（1cf0e10）](https://github.com/Motifman/llm-rpg/commit/1cf0e10b10ab80a45380695c6798dde5542c5bf5): 4宣言は幾何学と空形状の規則を独立に検査
- [速度・投射物効果（5d2c857）](https://github.com/Motifman/llm-rpg/commit/5d2c857b2d558bf7445b93dc573dc0fcfb327454): 静止と座標適用を導入
- [細分移動と精密位置（8ed9401）](https://github.com/Motifman/llm-rpg/commit/8ed940136e90b3bd0e65f58ad7b323fce14bcdc4): 微小量、比率、小数の保持、設定の既定・指定・最低値を追加
- [衝突サービス分離（de820b0）](https://github.com/Motifman/llm-rpg/commit/de820b09b145367184de533319b046f47f5ecffe): 能力、速度帯、予算を導入。修理した2宣言は導入時から修理前の形だった

## 検出力の比較

4種類の意図的な製品変更を、元の19件と候補21件でそれぞれ実行した。現行製品にこの不具合が存在したという意味ではない。

| 一時的な誤り | 元19件 | 候補21件 |
| --- | --- | --- |
| 移動能力を常に通常歩行として判定 | 全成功、見逃す | 2件失敗。元FLY行は通知が草地から壁へ変わり、追加WALK+FLY行は壁で失効する |
| 未存在タイルを通行可能に変更 | 非公開判定の1件失敗 | 同じ(10,10)の公開2行が失敗。元境界の検出力を保持 |
| PASS_THROUGHの障害物記録を省略 | 全成功、見逃す | 2件失敗。飛行元行とマップ外通過行で通知欠落を検出 |
| 障害物方針による失効条件を反転 | 2件失敗 | 4件失敗。元FLY-only/PASSの生存断言は旧新とも失敗し、元契約を保持 |

各変異後に製品を元のバイト列へ復元し、対象4所有者と集約のSHA256一致を確認した。保持したR17宣言の本文も元と一致する。

## 実行した検証と制限

固定依存のPython 3.10.22 / pytest 8.4.1で実行。検査対象の作業木の `src` を参照し、外部通信を遮断した。実LLM・有償APIは呼んでいない。

- 編集前の対象: 19成功、0失敗
- 編集前の関連: 139成功、0失敗
- 変異を復元した後の対象: 21成功、0失敗
- 復元後の関連: 139成功、0失敗
- 変更試験のruff 0.16.8と `git diff --check`: 成功

関連139件は対象19/21件を含まない。範囲は以下。

- `tests/domain/combat/aggregate`
- `tests/domain/skill/service/test_skill_to_hitbox_service.py`
- `tests/application/world/services/test_world_simulation_hit_box_updater.py`
- `tests/application/world/services/test_world_simulation_service.py` 全体
- `tests/infrastructure/repository/test_in_memory_hit_box_repository.py`
- `tests/infrastructure/repository/test_sqlite_hit_box_repository.py`
- `tests/domain/world/value_object/test_terrain_type.py`
- `tests/domain/world/value_object/test_movement_capability.py`

通常pytest収集の対象なのでCI登録は不要。基準失敗・製品修正はなく、全リポジトリの試験や型検査はこのローカル検証へ含めない。公開した先端のCIは別途確認する。
