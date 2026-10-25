# 物理地図の公開照会・配置契約の監査

> 過去の試験監査（2026-10-25追記、Issue #1862）。削除済みのタイルマップ・当たり判定に関する実装や試験の記述を含む。
> 本文の呼出元・保持先・件数は監査当時の記録で、現在の保証ではない。現存する領域もあるため一括して退役とは扱わない。[世界の現在の構成](../game/world_architecture.md)を参照。

## 範囲と判断

基準は `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。物理地図、構成エンティティ、識別子の9試験ファイル・132宣言を一つの所有範囲として確認した。
判断は維持112、検査修正15、保持先へ統合5、単独削除0。単純な構築・照会・拒否も独立した契約があれば残す。
試験の変更は集約の2ファイルだけで、他7ファイル、製品コード、共通の試験支援は変更しない。

| 元の試験ファイル（`tests/domain/world/` 配下） | 元宣言 | 維持 | 修正 | 統合 |
|---|---:|---:|---:|---:|
| `aggregate/test_physical_map_aggregate.py` | 88 | 70 | 13 | 5 |
| `aggregate/test_physical_map_aggregate_multi_objects.py` | 5 | 3 | 2 | 0 |
| `entity/test_spot.py` | 3 | 3 | 0 | 0 |
| `entity/test_tile.py` | 3 | 3 | 0 | 0 |
| `entity/test_world_object.py` | 8 | 8 | 0 | 0 |
| `entity/test_actor_component.py` | 3 | 3 | 0 | 0 |
| `value_object/test_spot_id.py` | 7 | 7 | 0 | 0 |
| `value_object/test_world_id.py` | 8 | 8 | 0 | 0 |
| `value_object/test_world_object_id.py` | 7 | 7 | 0 | 0 |

## なぜ検査を変えるか

- 群れ検索の通常型アクターは群れIDが `None` なので、自律型限定を誤って外しても群れ不一致で除外される。元の `None` 入力を残し、同じ群れIDの通常型を追加して型選別を区別する
- 同座標の複数物体を内部辞書だけで検査すると、公開の `get_objects_at` が1体しか返さない故障を見逃す。配置と除去を公開の一覧・ID取得で確認する
- 一括範囲の期待値を単体照会自身から作ると、両方の同じ誤りを正解として扱う。独立した固定ID一覧で空結果、所属、件数、多重度を確認する
- 同座標移動の通知0だけでは、忙しさ期限を誤って設定しても通る。元の通知検査に座標と期限の不変を加える
- 順序試験で全枠が同じ結果なら逆順を区別できない。異なる結果を返す既存保持先を先に補強して統合する

## 主たる契約の所有者

`PhysicalMapAggregate` は配置の整合性と、操作から状態更新・通知蓄積へ至る接続を所有する。
`MapGeometryService`、`MapInteractionPolicy`、`ChestInteractionPolicy`、`MapTriggerEngine`、`WeatherEffectService` の計算試験だけでは、この接続を置き換えられない。
範囲・視線の12宣言、トリガー6宣言、天候3宣言は残した。水・透明壁・物体・階層・地図外などの異なる入力も維持した。
`WorldObject` と構成要素の既定値・公開辞書・方向・忙しさ期限の等号、識別子22宣言の変換・下限・等価・ハッシュ・不変性も残した。

実呼出では `MonsterTargetContextBuilder.build_target_context` が群れを照会し、`PlaceObjectService` と死亡後の除去処理が物体を取り除く。
相互作用は `InteractionCommandService` とNPC側処理から集約へ届き、保存へ進む。呼出側の代役を使う試験は集約自身の型選別や同座標の複数物体を代替しない。
群れの呼出側にも自律型確認があるため、今回の検出力改善を直ちに実利用者の誤選択と同一視しない。

設計上の分担は `docs/refactoring/phase2-3-refactoring-plan.md` と `docs/refactoring/llm-agent-refactoring-roadmap.md` を確認した。
履歴 `2a37bdc` は同座標の複数物体、`0691cec` は時間と移動費用、`90132e3` は相互作用失敗時の通知・忙しさ不変を導入している。
`6f76228` は収納・取得の忙しさ確認漏れを直しているため、各入口の拒否試験を共通方針の試験だけへ集約しない。
一括APIには基準時点の製品直接呼出が見つからないが、`3756164` は明示的に公開機能として追加している。未使用だけを理由に廃止しない。

## 修正15宣言と保持する証拠

以下の関数は、特記した2件以外すべて `test_physical_map_aggregate.py` にある。

| 元宣言 | 修正と保持内容 |
|---|---|
| `test_move_success` | 公開 `add_object` で準備し、座標・出発到着の通行・期限・通知を維持 |
| `test_move_fails_when_busy` | 公開配置へ変更し、元の期限・時刻・例外を維持 |
| `test_move_to_same_position_does_nothing` | 公開配置へ変更し、通知0に座標と期限の不変を追加 |
| `test_move_to_occupied_tile_raises_error` | 公開配置へ変更し、元の2物体・座標と拒否を維持 |
| `test_move_to_wall_raises_error` | 公開配置へ変更し、既定能力で壁を拒否する入力を維持 |
| `test_set_blocking_updates_walkability` | 公開配置へ変更し、通行と通知の両検査を維持 |
| `test_change_to_wall_with_object_raises_error` | 公開配置へ変更し、物体のいる地形の変更拒否を維持 |
| `test_perform_action_fails_when_busy` | 公開配置へ変更し、元の忙しさ拒否を維持 |
| `test_move_object_from_wall_stays_impassable` | 元の壁Falseを残し、非公開属性Noneの代わりに壁を道へ変えた後Trueを確認 |
| `test_bulk_returns_same_as_individual_calls` | `test_bulk_returns_expected_objects_for_each_query` へ改名。固定 `[[1,2],[],[3]]` にし、元の実体所属・非所属・件数も維持 |
| `test_bulk_multiple_centers_same_map` | 元の型付きIDと件数を残し、`[[1],[2],[1,2,3]]` で全所属と多重度を追加 |
| `test_batch_deduplicates_same_pair` | `test_batch_preserves_repeated_pairs` へ改名。元の3入力とFalseの型・件数を維持。計算回数の削減は主張しない |
| `test_players_and_non_autonomous_actors_excluded` | 元の通常型 `None` 行と2物体を残し、同群れ通常型行を追加。両行とも型付きID2だけを返す |
| 複数物体の `test_multiple_non_blocking_objects_can_share_coordinate` | 公開一覧 `[1,2]` と両IDの取得・座標を検査 |
| 複数物体の `test_remove_object_updates_positions_correctly` | 公開一覧の残存ID2、残存座標、削除ID1の取得例外を検査 |

公開配置で発生した準備通知を必要箇所で消すが、検査対象の操作後の通知は消さない。
一覧を集合にすると重複を失うため、各枠のID一覧を並べ替えて比較する。元の型付きID・実体所属・件数の断言も削らない。

## 統合5宣言の保持先

保持先を先に補強し、元入力の移管後に元宣言を外した。ファイル全体の廃止はない。

| 元宣言 | 保持先と入力の扱い |
|---|---|
| `TestExceptions.test_get_direction_to_same_coordinate_raises_error` | `test_coordinate.py::TestCoordinate::test_direction_to`。絶対座標でなく差ゼロを判定する同座標方向例外を既存入力が守る |
| `TestGetObjectsInRangeBulk.test_bulk_order_of_results_matches_input_order` | `test_bulk_multiple_centers_same_map`。同じ物体しか返さない3枠より、異なる3枠の固定期待値で順序を区別 |
| `TestIsVisibleBatch.test_batch_returns_same_as_individual_calls` | `test_batch_visible_pairs_return_true` へ元3ペアをそのまま移す。逆方向 `(2,2)→(0,0)` の正例も維持 |
| `TestIsVisibleBatch.test_batch_same_coordinate_returns_true` | 同じ保持先へ元 `(1,1)→(1,1)` の単数入力を移す |
| `TestChestAndDoor.test_interact_with_locked_door_raises` | `test_interact_with_locked_door_emits_no_event_and_actor_not_busy`。同じID・位置・向き・時刻の例外と副作用なしを維持 |

視線保持先の元2ペアも残すので、表は2ペア・3ペア・単数の3行になる。各行の固定長と各要素の `is True` を検査し、整数1で通る等値比較へ弱めない。
独立した第二読で、逆方向・単数入力を消す危険、件数だけの範囲保持先、同じドアの連続操作を別実体の試験で代替する危険を修正した。
`test_world_object.py::TestWorldObject::test_door_interaction` は同じ実体の施錠失敗→解錠→開放成功を守るので無変更で残す。

## 検証結果と限界

Python 3.10.22、固定依存、外部通信を遮断した実行環境で確認した。試験の識別子は各実行内で一意で、通常実行の失敗・エラー・除外は0。

| 実行 | 成功件数 |
|---|---:|
| 未編集の所有9ファイル | 132 |
| 未編集の関連18ファイル | 153 |
| 変更後の所有9ファイル | 130 |
| 製品復元後の所有＋関連 | 283 |

変更後は127宣言・表展開後130件。関連は座標・地形・ドア、幾何・相互作用・箱・トリガー・天候、配置と場所の集約、群れ・配置・相互作用・箱のアプリ入口、死亡後除去、SQLite保存、HitBox衝突の18ファイル153件。
変更2試験への Ruff 0.16.8 と `git diff --check` は成功した。所有試験は2028行から1983行へ減り、差分は追加72・削除117。製品・共通試験支援の差分は0。
既存CIの通常 `uv run --frozen pytest -n auto` が当範囲を収集するため、収集経路の変更は不要。全リポジトリ試験と遠隔CIの成功はここでは主張しない。

製品所有者へ一時的な故障を入れ、元・変更後を同じ条件で比較した。各回の後に元のバイト列へ戻し、最後に283件を再実行した。

| 故障 | 元の失敗数 | 変更後の失敗数 | 比較範囲 |
|---|---:|---:|---|
| 群れ検索が通常型も受け入れる | 0 | 1 | 所有全体 |
| 公開座標照会が末尾1体しか返さない | 0 | 1 | 所有全体 |
| 同座標移動が忙しさ期限を設定する | 0 | 1 | 所有全体 |
| 範囲の3体を `[1,1,3]` にする | 0 | 1 | 所有全体 |
| 単体・一括の空範囲を同じ物体で埋める | 0 | 1 | 所有全体 |
| 壁から離れた後も通行上書きFalseを残す | 1 | 1 | 所有全体 |
| 逆方向の可視正例だけFalseにする | 1 | 1 | 所有全体 |
| 視線結果のboolをintにする | 7 | 7 | 所有全体 |
| 視線の単数入力だけ空結果にする | 2 | 2 | 所有全体 |
| 一括範囲の結果順序を逆転する | 0 | 1 | 統合前の弱い1試験と補強後の保持先1試験のみ |

最初の5故障はこの所有範囲で見逃しを補った証拠、続く4故障は検出力を保持した証拠である。
最後の順序比較は旧全体が見逃した証拠ではない。既存の異なる結果を持つ試験へ統合できることを確認した局所比較である。
適用後の独立レビューでも、132宣言の移管、111維持宣言の構文木不変、1維持宣言への表吸収、20実行の結果、両作業木の製品復元を照合した。

## 保留するドアの追加仕様

`test_interact_with_open_door_toggles_state_and_blocking` の開状態・物体遮蔽解除・通知は無変更で残す。
静的には、配置時のタイル通行上書きと、`DoorComponent.apply_interaction_from` が直接変える物体の遮蔽フラグが同期しない可能性がある。SQLiteはタイルの上書きも保存する。
ただし製品の経路探索は `is_passable`、移動は配置検証と `get_movement_cost` を使い、物体フラグを読む。`PhysicalMapAggregate.is_walkable` の直接利用者は見つからなかった。
従って、実移動不能・経路探索不具合とは断定しない。タイル同期の追加仕様、保存復元後の影響、開閉時の視線仕様は未再現・未確定であり、この1宣言の追加主張だけを別に保留する。
元のドア契約や他の131宣言の証拠を捨てる理由にはしない。製品修理やAPI廃止はこの変更に含めない。
