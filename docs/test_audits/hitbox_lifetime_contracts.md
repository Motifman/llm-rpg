# HitBox の発動・寿命に関する試験監査

> 過去の試験監査（2026-10-25追記、Issue #1862）。削除済みのタイルマップ・当たり判定に関する実装や試験の記述を含む。
> 本文の呼出元・保持先・件数は監査当時の記録で、現在の保証ではない。現存する領域もあるため一括して退役とは扱わない。[世界の現在の構成](../game/world_architecture.md)を参照。

## 範囲と結論

基準は `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。対象は次の2ファイル全体。

- `tests/domain/combat/aggregate/test_hit_box_activation.py`
- `tests/domain/combat/aggregate/test_hit_box_aggregate.py`

31宣言を読み、29を保持（R）、1を補強（F）、1を同じ契約の主担当へ統合（C）した。
削除だけで済ませる宣言（D）は0。本番・共通補助コードの変更は0。
宣言数は31→30、表を展開した試験数は31→32、試験行数は579→594（33行追加・18行削除）。

既存の遅延発動試験は19/20と29/30を正しく検査していたが、速度0のため移動を止める処理の退行を見逃した。
元の静止ケースに速度1の行を加え、発動前と失効時は座標が変わらず、発動中は動くことを通知と併せて検証する。
持続時間0の拒否は、元の開始時刻0/10を両方残して生成試験へまとめた。

## 実行経路と主担当

`SkillCommandService` と `MonsterSkillApplicationService` は `HitBoxFactory.create_from_params` から集約を生成する。
`SkillToHitBoxDomainService` は開始時刻と区間の遅延から発動時刻を算出する。
`WorldSimulationHitBoxUpdater` は自身で発動可否を判定してから `on_tick` を呼ぶため、その結合試験だけでは集約内部の発動前ガード欠落が隠れる。
集約の時刻・位置・通知の契約は、集約の公開入口を実際に呼ぶ本対象の試験が主担当となる。
衝突範囲は `HitBoxCollisionDomainService` が読み、対象・障害物の記録へ進む。

既定発動時刻での14/15境界、無効化の冪等性、速度・小数移動・経路・衝突の契約は保持する。
非公開属性や計算補助を参照する2宣言も、直前の細分区間と距離2の斜め経路を独立に守っているため、今回は削除しない。
片隣を検証する既存の斜め経路条件を、仕様確認なしに両隣必須へ変更しない。
廃止するファイル・試験層・試験専用の本番コードはない。

## 全宣言の判定

Rは同じ宣言を主担当として保持、Fは契約を残して検証を補強、Cは明記した主担当に統合する。
以下は変更前の宣言名。各行の失敗例が、残す理由または修理する理由となる。

### `test_hit_box_activation.py`

| 宣言 | 判定 | 契約と検出する退行 | 残る主担当 |
| --- | --- | --- | --- |
| `test_activation_delay` | F | 発動19/20と寿命29/30、15で有効状態を保持する。退行例: 発動または失効を1ティックずらす。監査前は速度0のため発動前に移動処理しても見逃す | 同じ宣言の静止・移動2行 |
| `test_invalid_activation_tick_raises_error` | R | 生成より早い発動をHitBoxValidationExceptionで拒否。退行例: 発動時刻検証を除去 | 同じ宣言 |
| `test_zero_duration_not_allowed` | C | 開始10のduration0をHitBoxValidationExceptionで拒否。退行例: duration検証を除去 | `TestCreate::test_create_invalid_duration_raises_exception[10]` |

### `test_hit_box_aggregate.py`

| 宣言 | 判定 | 契約と検出する退行 | 残る主担当 |
| --- | --- | --- | --- |
| `TestCreate::test_create_success` | R | 生成状態と生成通知の識別子・場所・所有者・強度・形状数・効果数。退行例: 生成通知欠落または通知内容の誤設定 | 同じ宣言 |
| `TestCreate::test_create_invalid_duration_raises_exception` | R | 開始0でduration0を拒否。退行例: 0を許容する比較へ変更 | 同じ宣言の開始0/10の2行 |
| `TestCreate::test_create_invalid_power_multiplier_raises_exception` | R | 倍率0を拒否。退行例: 倍率検証欠落 | 同じ宣言 |
| `TestCreate::test_create_with_hit_effects_sets_effect_count` | R | 生成時に2効果を保持しPOISON種別と通知個数を伝える。退行例: 効果を欠落・個数0にする | 同じ宣言 |
| `TestMovement::test_teleport_to_success_adds_event_and_syncs_precise` | R | 座標移動が精密座標と移動前後の座標通知を同期する。退行例: 整数位置だけ更新する | 同じ宣言 |
| `TestMovement::test_move_to_same_coordinate_does_not_add_event` | R | 同じ位置への移動で通知を増やさない。退行例: 同じ座標での早期終了を除去 | 同じ宣言 |
| `TestMovement::test_teleport_to_inactive_raises_exception` | R | 無効な判定の移動を拒否。退行例: 無効ガード除去 | 同じ宣言 |
| `TestMovement::test_on_tick_moves_with_velocity` | R | 発動済みの1回更新が速度分だけ移動し通知する。退行例: 速度処理未接続 | 同じ宣言 |
| `TestMovement::test_on_tick_stationary_hitbox_does_not_move` | R | 静止速度では座標も通知も変化しない。退行例: 静止時にも移動通知を生成 | 同じ宣言 |
| `TestMovement::test_on_tick_substep_accumulates_precise_position` | R | 小数移動を切り捨てず蓄積し整数境界でだけ通知する。退行例: 各細分更新の小数部を破棄 | 同じ宣言 |
| `TestMovement::test_on_tick_updates_previous_coordinate_each_substep` | R | 各細分更新の経路起点を直前座標にする。退行例: 起点が作成時の位置に固定される | 同じ宣言 |
| `TestMovement::test_calculate_path_covers_all_stepped_cells` | R | 2マス斜め経路で始終点と少なくとも5セルを含む。退行例: 経路が両端のみになる | 同じ宣言 |
| `TestMovement::test_high_speed_movement_path_interpolation` | R | 10マスの実移動が途中セル0から10を衝突範囲に含む。退行例: 高速移動で途中セルを飛ばす | 同じ宣言 |
| `TestCoverage::test_get_all_covered_coordinates_includes_path` | R | テレポートでも移動前後と途中セルを含む。退行例: `teleport_to`の経路起点更新を除く | 同じ宣言 |
| `TestCoverage::test_supercover_path_diagonal_movement` | R | 1マス斜めで両端と少なくとも片隣を含む。退行例: 経路を始終点のみへ縮める | 同じ宣言 |
| `TestCoverage::test_multi_cell_shape_coverage` | R | 移動の前後双方で形状の各相対セルを合成する。退行例: 形状を終点のみへ適用 | 同じ宣言 |
| `TestHitRecording::test_record_hit_success_adds_event` | R | 対象記録と所有者・対象・当たり位置通知。退行例: 命中記録または通知の対象取り違え | 同じ宣言 |
| `TestHitRecording::test_record_hit_duplicate_does_not_add_second_event` | R | 同じ対象への二重命中通知を抑制。退行例: 命中済みのガード除去 | 同じ宣言 |
| `TestHitRecording::test_record_hit_owner_is_ignored` | R | 所有者を命中対象にも通知にも加えない。退行例: 所有者ガード除去 | 同じ宣言 |
| `TestHitRecording::test_record_hit_inactive_raises_exception` | R | 無効状態で対象記録を拒否。退行例: 無効ガード除去 | 同じ宣言 |
| `TestHitRecording::test_record_hit_deactivates_when_target_collision_policy_is_deactivate` | R | 対象衝突で命中通知後に理由target_collisionで無効化。退行例: 状態維持または通知順序逆転 | 同じ宣言 |
| `TestObstacleCollision::test_record_obstacle_collision_pass_through_keeps_active` | R | 障害物通過設定では通知しつつ有効を保つ。退行例: ポリシー分岐逆転 | 同じ宣言 |
| `TestObstacleCollision::test_record_obstacle_collision_only_once_for_same_coordinate` | R | 同座標の障害物通知を一度だけ出す。退行例: 障害物記録セットを使わない | 同じ宣言 |
| `TestObstacleCollision::test_record_obstacle_collision_deactivate_turns_inactive` | R | 障害物通知後にobstacle_collision理由で無効化。退行例: 通知順序逆転または無効化欠落 | 同じ宣言 |
| `TestObstacleCollision::test_record_obstacle_collision_inactive_raises_exception` | R | 無効状態で障害物記録を拒否。退行例: 無効ガード除去 | 同じ宣言 |
| `TestLifecycle::test_is_expired` | R | 発動時刻省略時は開始10+期間5の14/15で失効判定。退行例: 終了比較の>=を>へ変更 | 同じ宣言 |
| `TestLifecycle::test_deactivate_adds_event_once` | R | 二度の無効化で状態を無効にし理由通知を一度だけ出す。退行例: 無効化通知の重複 | 同じ宣言 |
| `TestLifecycle::test_on_tick_expired_deactivates_hit_box` | R | 既定発動時刻で期限更新がexpired通知を一度出す。退行例: 期限で通知を出さない/理由間違い | 同じ宣言 |

## 履歴

- [発動制御の導入（48bed90）](https://github.com/Motifman/llm-rpg/commit/48bed90ceddee509b85932fbe5a09ae16b395563)で、発動前の早期終了と、発動時刻から寿命を数える処理が追加された。遅延発動試験はこの契約を保つ
- [速度・衝突・効果の追加（5d2c857）](https://github.com/Motifman/llm-rpg/commit/5d2c857b2d558bf7445b93dc573dc0fcfb327454)、[細分移動と精密位置（8ed9401）](https://github.com/Motifman/llm-rpg/commit/8ed940136e90b3bd0e65f58ad7b323fce14bcdc4)、[衝突処理の分離（de820b0）](https://github.com/Motifman/llm-rpg/commit/de820b09b145367184de533319b046f47f5ecffe)が、保持する移動・衝突試験の背景
- [斜め速度の修正（#1390）](https://github.com/Motifman/llm-rpg/pull/1390)からも、精密位置と細分移動が実際の呼出し経路で必要な契約であることを確認した

## 検出力の比較

同じ本番変異を、基準の2ファイルと変更後の2ファイルでそれぞれ実行した。
現行製品に下記の不具合があったという意味ではなく、意図的な誤りを試験が検出するかの確認である。

| 本番へ一時的に入れた誤り | 基準31件 | 変更後32件 |
| --- | --- | --- |
| 発動前の早期終了を除去 | 全成功、見逃す | 移動行が15の座標変化で失敗 |
| 失効判定を移動の後へ移す | 全成功、見逃す | 移動行が30で余分に動いて失敗 |
| 持続時間0の拒否を除去 | 元の2宣言が失敗 | 開始0/10の両行が失敗 |
| 発動時刻ちょうどを未発動にする | 20で失敗 | 静止・移動の両行が20で失敗 |
| 失効時刻ちょうどを有効にする | 既存3宣言が失敗 | 同じ契約の4行が失敗 |
| 寿命を生成時刻から数える | 遅延発動の宣言が失敗 | 静止・移動の両行が失敗 |

移動後へ失効判定を移す変異でも、失効条件そのものの真偽は変えず、判定は1回のままとした。
各検査後に本番を復元し、最終的に元のバイト列と一致することを確認した。

## 実行結果と制限

Python 3.10、基準と同じ `uv.lock` の依存環境で実行。検証する作業木の `src` を参照していることを確認し、外部通信を遮断した。

- 編集前の対象2ファイル: 31成功、0失敗
- 編集後の対象2ファイル: 32成功
- 復元後の関連試験: 179成功、0失敗
- 変更2ファイルの `ruff check` と `git diff --check`: 成功

関連179件は以下の範囲。`world_simulation_service` はHitBoxに絞らずファイル全体を実行した。

- `tests/domain/combat`
- `tests/domain/skill/service/test_skill_to_hitbox_service.py`
- `tests/application/world/services/test_world_simulation_hit_box_updater.py`
- `tests/application/world/services/test_world_simulation_service.py`
- `tests/infrastructure/repository/test_in_memory_hit_box_repository.py`
- `tests/infrastructure/repository/test_sqlite_hit_box_repository.py`

対象ファイルは通常のpytest収集対象であり、CIの特別な登録変更は不要。
この監査で本番修正が必要な基準失敗は見つからなかった。
全リポジトリ試験・型検査などは、この差分を載せたコミットのCIで確認する。上記179件は全リポジトリの実行結果ではない。
