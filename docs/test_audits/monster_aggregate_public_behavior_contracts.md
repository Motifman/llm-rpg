# モンスター集約: 行動・追跡の公開入口32宣言の監査

## 結論

元32宣言をR15/F9/C8として監査した。公開の状態・追跡実体・未配信イベントを保持し、生成された値や例外型の検査を強めた。旧32入力は全て残し、追加3行を含む24宣言35行へまとめた。C8は移管先を含む段階版43行の成功後に除去した。製品・共通の準備・支援コードの変更はない。

試験ファイルは1990→2084行（+190/-96）。全文108宣言のうち対象外76宣言は本文・デコレータ・AST不変。R15のうち元ID14はCの保持先、元ID89は実際の検査に合わない説明だけを修正し、他13宣言は原文・AST不変。親88試験を子が再収集しない準備分離も維持した。

## 依存と併用の条件

- 基準は[#1718](https://github.com/Motifman/llm-rpg/pull/1718)、固定先端 `000d3e765c36f594f0ceb4f7e9680200e1bccb59`。共通の収集修理[#1712](https://github.com/Motifman/llm-rpg/pull/1712)を含む
- [#1715](https://github.com/Motifman/llm-rpg/pull/1715)は兄弟PR。固定先端 `6309e6aeab1e5f1274f0b347471a2a2cc46776d2` の4宣言の差分を、このPRには収載しない
- 別のローカル作業木で両固定差分を合成した。候補にも#1715の元の差分が通常適用でき、4宣言は同PRと全文一致、残り96宣言は候補と一致した。既監査7契約の11行は基準・最終とも成功した
- 作業時のmainは `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。未完了PR61件の変更先を確認し、当該試験ファイルの重なりは予定済み#1712/#1715/#1718だけだった

## 契約を持つ層

純粋な状態機械は、状態値・EventSpec・追跡操作の命令を返す。値オブジェクトは新しい行動/追跡の値を作る。今回は、集約が現在値を渡し、返った値を自身へ代入し、実際の追跡を作成・更新・解除して実イベントを蓄える接続を検査した。下位の純粋試験だけでは、集約の引数や代入先の取り違えは見えない。

MonsterBehaviorCoordinatorは観測、適用、縄張り、失敗判定、行動記録、保存/同期配信を調整する。CombatAggroHandlerはrecord_attacked_byを呼び、移動ハンドラは巡回点到着時にadvance_patrol_indexを呼ぶ。既存の模擬オブジェクトの委譲試験は順序や引数を守るが、実集約の値を代替しない。

ここでいう実イベントは集約の未配信イベント列への追加であり、観測配送を証明するものではない。現行のTargetSpotted/TargetLostは配信先解決側で配信せず、観測文整形も観測を返さない。同時刻 ENRAGE/FLEEの通知整合 `MONSTER_ENRAGE_FLEE_EVENT_CONSISTENCY` は別担当の保留を維持し、この32では入力や期待値を追加していない。

## 修理した検査

- 追跡失敗は元CHASE行を残し、公開喪失操作によるSEARCH行を追加。最後の観測(4,0,0)/時刻3と元スナップショット(3,0,0)を区別し、失敗イベント1件の行為者/標的/理由/両観測値を確認する。追跡・標的・行動位置の消去も残す
- 空結果は旧IDLE/空イベント行を維持。新しい行では先にCHASE・実追跡・未配信通知を作り、集約から判断へ渡す現在状態・標的・位置が失われないことを確認する
- FLEEは元モンスター番号1/世界オブジェクト番号1行に世界オブジェクト番号1001の行を追加。実TargetSpottedとActorStateChangedが各1件、指定した標的/座標、IDLE→FLEE、行為者識別子を持つことを確認する。イベント順序は新たな契約にしない
- 元の未出現・公開死亡の入力と例外型を残し、拒否直前の行動/追跡または所有するイベント列を比較する。死亡操作の副作用は比較開始前に完了させる。未出現は公開作成契約上DEADであり、NotSpawnedの別ガードを通ったとは扱わない
- 最終既知情報なしの拒否は、元の公的な復元入力を維持。追跡とスナップショットは存在するが最終観測と行動位置はないため、後段拒否に到達する。元イベント列は空なので、非空の通知保持を証明したとは書かない
- 正常な移動/相互作用、SEARCH保持/再発見、FLEE_ONLY、縄張り内外と追跡解除、段階の閾値、巡回順序は独立した契約として保持した。設定・既定値・委譲という見た目だけで削除しない

## 元32宣言と保持先

試験ファイル: `tests/domain/monster/aggregate/test_monster_aggregate.py`。番号は元108宣言の台帳ID。下表の保持先は同じファイル内。全旧入力・旧確認式・例外型は対応する保持先へ残す。

| 元ID | 元試験名 | 判定 | 保持する契約・移管先 |
|---|---|---|---|
| 11 | `test_apply_behavior_transition_spot_target_starts_aligned_pursuit` | R | 発見からCHASEへ進み追跡対象・地点・最終観測時刻を揃える |
| 12 | `test_apply_behavior_transition_lose_target_keeps_pursuit_for_search` | R | 見失ってSEARCHとなっても元の標的スナップショットと更新した最終位置を区別する |
| 13 | `test_apply_behavior_transition_lose_target_reuses_existing_last_known_when_result_omits_it` | R | 喪失結果の座標省略時は既存の最終位置を維持する |
| 14 | `test_record_attacked_by_starts_pursuit_when_monster_chases` | R | 被弾起点のCHASEも共通追跡対象・最終位置/時刻を作る。元3001行とC49の200行を保持 |
| 15 | `test_apply_behavior_transition_reacquires_same_target_from_search` | R | SEARCH中に同じ対象を再発見するとCHASEへ戻り同じ行為者/標的と新観測値を保持する |
| 16 | `test_fail_pursuit_clears_monster_target_and_last_known_state` | F | 追跡失敗で対象/最終位置/追跡を消し理由を通知する。`test_fail_pursuit_clears_monster_target_and_last_known_state` で上記の観測を補強 |
| 17 | `test_fail_pursuit_when_no_active_pursuit_raises` | F | 有効な追跡がないfail_pursuitは専用例外。`test_fail_pursuit_when_no_active_pursuit_raises` で上記の観測を補強 |
| 18 | `test_fail_pursuit_when_no_last_known_state_raises` | F | 追跡はあるが最終既知情報も行動位置もないfail_pursuitは専用例外。`test_fail_pursuit_when_no_last_known_state_raises` で上記の観測を補強 |
| 19 | `test_non_pursuit_exit_clears_aligned_pursuit_state` | R | 逃走と縄張り復帰という別入口の退出で共通追跡状態を消す |
| 49 | `test_record_attacked_by_sets_chase` | C | 通常個体の被弾で標的と最終位置を設定しCHASEになる。`test_record_attacked_by_starts_pursuit_when_monster_chases` の元入力を置換しない別行へ移す |
| 50 | `test_record_attacked_by_flee_only_sets_flee` | R | FLEE_ONLY個体は被弾するとFLEEになり攻撃者を標的にする |
| 51 | `test_record_attacked_by_when_not_spawned_raises` | F | 未出現個体への被弾反応はMonsterAlreadyDeadException。`test_record_attacked_by_rejects_unavailable_actor` で上記の観測を補強 |
| 52 | `test_record_attacked_by_when_dead_raises` | C | 死亡個体への被弾反応はMonsterAlreadyDeadException。`test_record_attacked_by_rejects_unavailable_actor` の元入力を置換しない別行へ移す |
| 89 | `test_to_behavior_state_snapshot_after_spawn` | R | 出現直後の行動スナップショットはIDLE・標的なし・HP比1・逃走閾値0.2。実確認式にない初期位置の説明を修正 |
| 90 | `test_to_behavior_state_snapshot_phase_thresholds_from_template` | R | テンプレートのボス閾値順序をスナップショットへ渡す |
| 91 | `test_apply_behavior_transition_success_empty_result` | F | 空の遷移結果でIDLEが変わらず新規通知もない。`test_apply_behavior_transition_success_empty_result` で上記の観測を補強 |
| 92 | `test_apply_behavior_transition_when_not_spawned_raises` | F | 未出現の行動適用はMonsterAlreadyDeadException。`test_apply_behavior_transition_rejects_unavailable_actor` で上記の観測を補強 |
| 93 | `test_apply_behavior_transition_when_dead_raises` | C | 死亡後の行動適用はMonsterAlreadyDeadException。`test_apply_behavior_transition_rejects_unavailable_actor` の元入力を置換しない別行へ移す |
| 94 | `test_apply_behavior_transition_flee_result_updates_state` | F | 脅威によるFLEE適用は標的/状態と発見/状態変更通知を出す。`test_apply_behavior_transition_flee_result_updates_state` で上記の観測を補強 |
| 95 | `test_apply_behavior_transition_lost_target_moves_chase_to_search` | R | 復元されたCHASEが喪失でSEARCHへ進み追跡を補い標的喪失/状態変更を通知する |
| 96 | `test_apply_territory_return_when_outside_radius` | R | 縄張り外のCHASEはRETURNへ進み状態変更を通知する |
| 97 | `test_apply_territory_return_when_inside_radius_no_change` | R | 縄張り内はCHASEのままでRETURN通知も出ない |
| 98 | `test_apply_territory_return_when_not_spawned_raises` | F | 未出現の縄張り判定はMonsterAlreadyDeadException。`test_apply_territory_return_when_not_spawned_raises` で上記の観測を補強 |
| 99 | `test_record_move_success` | R | 移動意図通知1件に行為者・座標・地点・時刻を載せる |
| 100 | `test_record_move_when_not_spawned_raises` | F | 未出現の移動記録はMonsterAlreadyDeadException。`test_unavailable_actor_rejects_action_without_events` で上記の観測を補強 |
| 101 | `test_record_move_when_dead_raises` | C | 死亡後の移動記録はMonsterAlreadyDeadException。`test_unavailable_actor_rejects_action_without_events` の元入力を置換しない別行へ移す |
| 103 | `test_record_use_skill_when_not_spawned_raises` | C | 未出現の技能記録はMonsterAlreadyDeadException。`test_unavailable_actor_rejects_action_without_events` の元入力を置換しない別行へ移す |
| 104 | `test_record_use_skill_when_dead_raises` | C | 死亡後の技能記録はMonsterAlreadyDeadException。`test_unavailable_actor_rejects_action_without_events` の元入力を置換しない別行へ移す |
| 105 | `test_record_interact_success` | R | 相互作用意図通知1件に行為者・標的・地点・時刻を載せる |
| 106 | `test_record_interact_when_not_spawned_raises` | C | 未出現の相互作用記録はMonsterAlreadyDeadException。`test_unavailable_actor_rejects_action_without_events` の元入力を置換しない別行へ移す |
| 107 | `test_record_interact_when_dead_raises` | C | 死亡後の相互作用記録はMonsterAlreadyDeadException。`test_unavailable_actor_rejects_action_without_events` の元入力を置換しない別行へ移す |
| 108 | `test_advance_patrol_index` | R | 巡回点3個で索引が0→1→2→0と進む |

C49の攻撃者200/(5,5,0)/時刻1は、保持先の旧3001/(1,2,0)/時刻7と別行にした。C52は致死時刻10/要求時刻20、C93は致死時刻1/要求時刻2を維持。行動拒否のC5は移動座標(1,1,0)、技能スロット0/標的なし、相互作用の標的1を保ち、未出現時刻0・死亡後時刻2の元組を全て残した。

## 旧新の限定対照

専用の作業木で1変更ずつ行い、旧32行と新35行を同じ製品変異で実行した。改善19組は旧が全成功し、新の予定した項目が失敗。保存10組は元確認式と新保持先がともに失敗。意味保持2組は旧新とも成功した。計31組62実行で収集・準備エラー、スキップは0。共有ガードや複数入力に及ぶ変異は、複数行の失敗を意図した結果として照合した。

| 対照 | 種類 | 旧:成功/失敗 | 新:成功/失敗 |
|---|---|---:|---:|
| `01_failed_actor` | 改善 | 32/0 | 33/2 |
| `02_failed_target` | 改善 | 32/0 | 33/2 |
| `03_failed_last_known` | 改善 | 32/0 | 33/2 |
| `04_failed_snapshot` | 改善 | 32/0 | 33/2 |
| `05_failed_duplicate` | 改善 | 32/0 | 33/2 |
| `06_flee_target` | 改善 | 32/0 | 33/2 |
| `07_flee_coordinate` | 改善 | 32/0 | 33/2 |
| `08_flee_actor_identity` | 改善 | 32/0 | 34/1 |
| `09_flee_old_state` | 改善 | 32/0 | 33/2 |
| `10_flee_new_state` | 改善 | 32/0 | 33/2 |
| `11_spotted_duplicate` | 改善 | 32/0 | 33/2 |
| `12_changed_duplicate` | 改善 | 32/0 | 33/2 |
| `13_empty_state` | 改善 | 32/0 | 34/1 |
| `14_empty_target` | 改善 | 32/0 | 34/1 |
| `15_empty_position` | 改善 | 32/0 | 34/1 |
| `16_no_pursuit_consumes_queue` | 改善 | 32/0 | 34/1 |
| `17_no_last_known_clears_pursuit` | 改善 | 32/0 | 34/1 |
| `18_behavior_rejection_consumes_queue` | 改善 | 32/0 | 26/9 |
| `19_attacked_rejection_consumes_queue` | 改善 | 32/0 | 33/2 |
| `20_attacked_target` | 保存 | 31/1 | 34/1 |
| `21_attacked_position` | 保存 | 31/1 | 34/1 |
| `22_attacked_state` | 保存 | 31/1 | 34/1 |
| `23_attacked_dead_guard` | 保存 | 31/1 | 34/1 |
| `24_apply_dead_guard` | 保存 | 31/1 | 34/1 |
| `25_move_dead_guard` | 保存 | 31/1 | 34/1 |
| `26_skill_unspawned_guard` | 保存 | 31/1 | 34/1 |
| `27_skill_dead_guard` | 保存 | 31/1 | 34/1 |
| `28_interact_unspawned_guard` | 保存 | 31/1 | 34/1 |
| `29_interact_dead_guard` | 保存 | 31/1 | 34/1 |
| `30_lawful_event_actor_alias` | 意味保持 | 32/0 | 35/0 |
| `31_lawful_guard_predicate` | 意味保持 | 32/0 | 35/0 |

- 行為者識別子の取り違えは正しい型のWorldObjectIdでモンスター番号を使い、元世界オブジェクト番号1行を通した上で世界オブジェクト番号1001行を失敗させた
- 空結果の状態/標的/位置は個別に壊した。事前の追跡作成は通常どおり通し、空適用後の比較で失敗した
- C49は元攻撃者200の行だけの行動状態/標的/位置を個別に壊した。旧3001行に失敗を肩代わりさせていない
- Cの拒否入力を外した7変異は、元の操作・時刻で例外が出なくなった `DID NOT RAISE` を旧新で確認した。別の構築エラーを保存の証拠にしていない
- 元追跡なしの拒否では非空のイベント列の消費、最終既知情報なしの拒否では追跡の先行解除を分けて検査した

## 実行と復元

1. ASTで対象指定を事前確認し、未編集の対象32＋関連9＝41行が初回成功。兄弟合成7宣言11行も成功
2. C8を残した段階版43行の成功後に除去し、候補35行が成功
3. 31組62実行の旧新対照が予定どおり。候補と変異用の全1601製品Pythonファイルを基準ハッシュと照合し、変異用の元試験もバイト一致で復元
4. 復元後は当該集約全体111行＋関連9＝120行が一意に成功。兄弟合成11行も成功し、これを今回32の完了件数へ加算していない
5. Python3.10.22/pytest8.4.1、資格情報・プロキシ除去、ネットワーク遮断、各回の新しいバイトコードキャッシュで直列実行。Ruff0.16.8、git diff --checkも成功

関連9は追跡値型の解除/同期/最終観測保持4、純粋な空結果/FLEE適用2、調整サービスの委譲順序/失敗/技能/相互作用3。対象との試験識別子重複はない。全リポジトリ試験はローカルで実施せず、公開する正確な公開先端のCIを別に確認する。

## 履歴と未完

行動/スナップショット導入 `95df4baf`、公開入口分離 `40ef94a0`、被弾記録移管 `220bc4bd`、追跡整合 `64e5a311`、追跡失敗導入 `6749e3bc`、専用例外化 `5e85f0b3` の実差分を読んだ。特に追跡失敗は、追跡整合の導入履歴だけを根拠にせず、イベント・例外の別導入を確認した。

この文書の監査対象は元32だけ。既監査7は範囲外で保持し、集約本体の残り69、同時刻通知整合の製品質問、成長復元のHP/MP問題は未完として分ける。製品修理・課題票の作成・マージは含めない。
