# モンスターとプレイヤーの攻撃実行試験の監査

## なぜ

不発の理由が正しくても、被害や通知、攻撃時刻だけを誤って更新する実装はあり得ます。
従来の拒否試験の一部は、返された理由だけを検査していました。
また、致命攻撃後の配置試験は攻撃先へ渡していないグラフを調べていたため、
実際の攻撃処理が配置を消す誤りを検出できませんでした。

## 範囲と判断

基準は `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f` です。
元の6ファイル39宣言を読み、保持31、補強8、統合0、削除0と判断しました。
3つの値オブジェクトの試験は、公開の値・制約・等価性を守るため無変更で保持します。
モンスター集約の攻撃待ち時間や生命状態を対象にした別の監査とは範囲を分けています。

| 元の対象 | 宣言 | 保持 R | 補強 F |
|---|---:|---:|---:|
| `service/test_monster_skill_execution_domain_service.py` | 7 | 6 | 1 |
| `service/test_spot_monster_attack_service.py` | 8 | 5 | 3 |
| `service/test_spot_player_attack_service.py` | 6 | 2 | 4 |
| `value_object/test_attacker_ref.py` | 7 | 7 | 0 |
| `value_object/test_monster_attack_status_effect_declaration.py` | 5 | 5 | 0 |
| `value_object/test_monster_skill_info.py` | 6 | 6 | 0 |

上表の接頭辞は `tests/domain/monster/` です。
配置試験1宣言を `tests/application/world_graph/test_spot_player_attack_presence.py` へ移します。
元と移管先を合わせて39宣言、表の展開後46件を維持します。退役するファイルはありません。
製品コードと共有の試験補助は変更しません。

## 補強する契約と保持する入力

1. 技能の同tick再使用では、元の初回10・再試行10・MP費用10・詠唱停止1・待ち時間5を
   残します。名称を詠唱停止へ正し、`SkillCastLockActiveException` とcast文言を検査します。
   旧試験は詠唱停止ガードが消えても、後段の再使用待ち例外で成功していました。
   再使用待ち自体は既存アプリ試験の10→12と装備集約が検査するため、新しい行は追加しません。
2. モンスター側の使用不可・不可視・対象ダウンの3試験で、既存入力と拒否理由を残し、
   被害適用と攻撃時刻記録が呼ばれないことを検査します。不可視は実際の視認サービスを通ります。
   代役は協力者への呼出を観測するだけで、実際のHP計算の正しさまでは主張しません。
3. プレイヤー側の攻撃者ダウン・対象未出現・攻撃力0の3試験で、同じ実モンスターを保持し、
   HP30と通知なしを実行前後に確認します。不発結果を返しながら対象を変更する誤りを検出します。
4. 致命後の配置は、グラフを受け取る実際の `SpotAttackOrchestrator.execute_player_attack` へ
   移します。HP5・攻撃999・tick20・モンスター101・世界物体9001・場所1・グラフ1・
   プレイヤー1、元のテンプレート値と直接のALIVE構築を保持します。
   元の致命結果、配置あり、場所1という3断言を残し、実行成立とHP0も確認します。
   同じグラフを呼出先へ渡すので、その入口での配置除去を検出できます。

移管先は1試験だけの新しいファイルにし、既存の非致命アプリ試験の入力や準備を変えません。
必要な元定数で直接準備し、別の試験モジュールや製品の検査用引数には依存しません。
リポジトリの代役は保存を受けるだけです。この試験が保証するのは呼出直後の配置であり、
永続保存や、その後のイベント配送で起こる配置変更は対象に含めません。

## 検出力の対照

各対照は製品を一時変更し、元6ファイルと変更後7ファイルを別々に実行しました。
8補強に対して9種の改善対照を使いました。不可視の2副作用は別々に変更しています。

| 意図した誤り | 元の対象 | 変更後の対象 |
|---|---|---|
| 詠唱停止ガードを外す | 成功。再使用待ちの例外を受容 | 専用例外の不一致で失敗 |
| 使用不可でも攻撃時刻を記録 | 成功 | 未呼出の断言で失敗 |
| 不可視でも被害を適用 | 成功 | 未呼出の断言で失敗 |
| 不可視でも攻撃時刻を記録 | 成功 | 未呼出の断言で失敗 |
| 対象ダウンでも攻撃時刻を記録 | 成功 | 未呼出の断言で失敗 |
| 攻撃者ダウンでも被害1を適用 | 成功 | HP29と期待30の違いで失敗 |
| 未出現対象にも被害通知を追加 | 成功 | 通知なしの断言で失敗 |
| 攻撃力0でも被害0の通知を追加 | 成功 | 通知なしの断言で失敗 |
| 致命攻撃の処理後に配置を除去 | 成功 | 実行成立・HP0・致命結果を通過し、配置ありの断言で失敗 |

保持の5対照は、元と変更後の両方で失敗しました。
MP費用Noneをそのまま演算へ渡す、致命結果をfalseにする、攻撃者IDを取り違える、
確率にboolを受理する、技能情報の等価比較から射程を外す、の5種です。
合計14種28実行で、準備・後始末の失敗はありません。

これは対象の断言が何を検出するかの比較です。別階層の既存試験を含めた
全リポジトリで、その誤りを誰も検出できなかったとは主張しません。

## 通常の検証と復元

- 未編集の対象46件と関連71件が成功
- 変更後の対象46件が成功
- 変異終了後、変更した製品8ファイルを全バイト復元し、候補試験7ファイルも変更前の候補と一致
- 復元後に対象46件と関連71件、合計117件が成功。範囲間の試験ID重複なし
- 変異対照の各呼出に未使用のバイトコード保存先を割り当て、Python3.10.22と固定依存で実行
- 通信を遮断し、実LLMや外部APIは使用せず、自身の作業木のsrcを読むことを検査
- 変更試験のruff 0.16.8と差分の空白検査が成功

関連71件は、技能アプリ10、攻撃の統括5、視認6、技能選択20、
SQLiteテンプレート13、SQLiteモンスター10、状態異常付与7です。
全リポジトリの結果は、この変更を公開する正確なコミットのCIで確認します。
ローカルの関連検証から全体成功は主張しません。

対象試験は848行から909行へ変わり、追加124・削除63行です。
移管先の直接準備と不発後の状態確認が増えるため、行数や速度の削減は目的にしていません。
製品・共有補助の増減は0です。

## 保持する責務と設計上の区別

- 値オブジェクトの生成、0境界、大値、ID排他、同値hash、不変性は独立した公開契約として残します
- 不同値に異なるhashを強制する制約は加えません
- 状態異常の型・値検証と、シナリオ変換・保存・実行時の付与は別責務です
- 技能拒否より前に入力集約のMP消費が実行されますが、正式保存の喪失を示したものではありません。
  アプリ側は取得と成功時保存を担います。入力の巻き戻しを新しい要件として追加せず、製品修理と混ぜません

## 履歴

技能の分離は [98eab8c](https://github.com/Motifman/llm-rpg/commit/98eab8cb87463a98ea7bb3cec4844d2eb4333deb)、
None費用の回帰は [16531b2](https://github.com/Motifman/llm-rpg/commit/16531b263e9a71649cfc64bb8ea5813d3a82f8f9) で確認しました。
配置保持を検査する元の意図は [653876d](https://github.com/Motifman/llm-rpg/commit/653876d40bf554686fd3a6f78967ec2db7d325e7)、
攻撃処理の統括への移管は [69f1898](https://github.com/Motifman/llm-rpg/commit/69f1898d9c1dcf7b8ae2ab2a43cb9127151002d9) です。
ゼロ被害の通知抑制は [183850a](https://github.com/Motifman/llm-rpg/commit/183850a109dd065f2cd6782adeea34671dd5ea25)、
参照導入は [92f1c58](https://github.com/Motifman/llm-rpg/commit/92f1c589f2b79b89475e334b68139b434e47fe1f)、
状態異常の宣言化は [e60bf1d](https://github.com/Motifman/llm-rpg/commit/e60bf1d779e6ce8f73b492653ff083fae8309c03)、
技能情報の移管は [8673653](https://github.com/Motifman/llm-rpg/commit/867365382e00507fd53dd80a923b89496d40e9f2) です。

## 全39宣言の台帳

行番号と識別名は基準点のものです。Fも契約を保持して補強します。
配置以外の主試験は同じファイルに残ります。技能拒否の名称だけは
`test_execute_cast_lock_active_raises_cast_lock_exception` へ正します。

### `tests/domain/monster/service/test_monster_skill_execution_domain_service.py`

| 元の宣言（行） | 判断 | 契約と検出対象 |
|---|---|---|
| `test_execute_success_returns_spawn_params_and_updates_aggregates` (109) | R | 技能実行は生成位置(5,5,0)、MP100→90、当tickの使用不可を返す。生成なし、誤位置、MP消費漏れ、待ち時間設定漏れ |
| `test_execute_skill_without_mp_cost_keeps_mp_unchanged` (127) | R | mp_cost=Noneを0として実行しMPを維持。NoneをMP演算へ渡す既知退行 |
| `test_execute_skill_not_in_slot_raises_skill_not_found_in_slot` (149) | R | 未装備slot1を専用例外で拒否。空slotを黙って成功扱い |
| `test_execute_insufficient_mp_raises_domain_exception` (163) | R | MP100でcost200を拒否。MP不足の成功扱い |
| `test_execute_monster_not_on_map_raises_object_not_found` (179) | R | 未配置map99をObjectNotFoundExceptionで拒否。存在しない発射主体から生成 |
| `test_execute_cooldown_active_raises_domain_exception` (194) | F | 初回tick10の後、同tickの再試行を詠唱停止の専用例外で拒否。元OR断言は詠唱停止ガードを外しても後段の再使用待ち例外を受容して通る |
| `test_execute_monster_dead_raises_domain_exception` (216) | R | 死亡したモンスターからの技能を拒否。死亡状態のMP消費と発射の受理 |

### `tests/domain/monster/service/test_spot_monster_attack_service.py`

| 元の宣言（行） | 判断 | 契約と検出対象 |
|---|---|---|
| `test_neutral` (66) | R | 中立なら不発理由not_hostileで被害・攻撃記録なし。敵対条件を飛ばす、拒否でも被害や記録を作る |
| `test_can_attack_now_false` (85) | F | 使用不可ならcannot_attackで被害・攻撃記録なし。元試験は拒否時の攻撃時刻記録を見逃す |
| `test_darkness_dark_vision_2` (103) | F | 暗闇かつ暗視なしならnot_visibleで被害・攻撃記録なし。元試験は不発結果と同時に被害や記録を作る誤りを見逃す |
| `test_darkness_dark_vision` (116) | R | 暗闇かつ暗視ありなら12の攻撃成立。可視性入力の配線不良、暗視能力無視 |
| `test_downed` (133) | F | 既にダウンした対象ならtarget_downで被害・攻撃記録なし。元試験は対象ダウン拒否で攻撃時刻を記録する誤りを見逃す |
| `test_calls_apply_damage_record_attack` (151) | R | attack8を一度適用しtick20を一度記録、非致命結果。被害適用漏れ、重複、誤tick、被害前のダウン判定 |
| `test_attack_executed_false` (167) | R | attack0はzero_damageで被害・攻撃記録なし。ゼロ被害でも通知と待ち時間を進める既知退行 |
| `test_downed_outcome` (182) | R | 被害適用後のダウン状態を結果へ返す。被害適用前の状態を結果へコピー |

### `tests/domain/monster/service/test_spot_player_attack_service.py`

| 元の宣言（行） | 判断 | 契約と検出対象 |
|---|---|---|
| `test_down_true_executed_false` (93) | F | 攻撃者ダウンならattacker_down、対象HPと全通知は不変。不発結果のまま対象HPを減らす誤りを元試験は見逃す |
| `test_status_dead_executed_false` (108) | F | 死亡・未出現対象ならtarget_dead、対象HPと全通知は不変。不発結果のまま対象通知を増やす誤りを元試験は見逃す |
| `test_attack_executed_false` (126) | F | attack0ならzero_damage、対象HPと全通知は不変。0被害通知を追加してから不発を返す誤りを元試験は見逃す |
| `test_triggers_apply_damage_via_event` (141) | R | HP30へattack8で非致命、被害通知が1件でdamage8。呼出漏れ、被害量誤り、重複通知 |
| `test_target_incapacitated_true` (162) | R | HP10へattack999で致命、死亡通知1件。致命状態または死亡通知欠落 |
| `test_after_spot_graph_presence_preserved` (177) | F | HP5/attack999/tick20の致命攻撃後もmonster101のspot1配置を保つ。独立して作り呼出先に渡さないgraphを読む元試験では実所有者による除去を検出できない |

### `tests/domain/monster/value_object/test_attacker_ref.py`

| 元の宣言（行） | 判断 | 契約と検出対象 |
|---|---|---|
| `test_of_monster_sets_kind_and_monster_id` (19) | R | of_monster(101)はMONSTERと対応ID、playerなし、両種別述語。ID種別取り違え |
| `test_of_player_sets_kind_and_player_id` (28) | R | of_player(7)はPLAYERと対応ID、monsterなし、両種別述語。ID種別取り違え |
| `test_monster_kind_monster_id_none_raises_exception` (41) | R | MONSTERに必須monster_idがなければ専用例外。欠損参照の許容 |
| `test_monster_kind_player_id_raises_exception` (46) | R | MONSTERに両IDを付けると専用例外。相互排他制約の欠落 |
| `test_player_kind_player_id_none_raises_exception` (55) | R | PLAYERに必須player_idがなければ専用例外。欠損参照の許容 |
| `test_player_kind_monster_id_raises_exception` (60) | R | PLAYERに両IDを付けると専用例外。相互排他制約の欠落 |
| `test_frozen_dataclass` (69) | R | 公開参照のフィールド代入を拒否。値オブジェクトが通常代入で可変化 |

### `tests/domain/monster/value_object/test_monster_attack_status_effect_declaration.py`

| 元の宣言（行） | 判断 | 契約と検出対象 |
|---|---|---|
| `test_accepts_complete_declaration` (17) | R | POISON/0.6/10/1.5を型と値のまま保持。宣言値の取り違え |
| `test_rejects_invalid_chance` (32) | R | chance -0.01/1.01/True/文字列を拒否。範囲・bool・数値型の検証欠落 |
| `test_rejects_non_positive_integer_duration` (42) | R | duration0/-1/True/1.5を拒否。非正・bool・整数型の検証欠落 |
| `test_rejects_effect_type_string` (53) | R | 効果種別文字列を拒否。enum変換漏れを受理 |
| `test_rejects_non_numeric_value` (63) | R | 強度True/文字列を拒否。bool・数値型の検証欠落 |

### `tests/domain/monster/value_object/test_monster_skill_info.py`

| 元の宣言（行） | 判断 | 契約と検出対象 |
|---|---|---|
| `test_create_with_required_fields` (11) | R | slot0/range5/mp10の公開生成値。入力フィールドの欠落・交換 |
| `test_create_boundary_slot_index_zero` (18) | R | slot0/range1/mp0のゼロ境界を許容。0のMP費用を既定値へ置換 |
| `test_create_large_values` (25) | R | slot3/range999/mp100の大値を許容。勝手な上限丸め |
| `test_equality_by_value` (32) | R | 同値は等価でhashも等しい。値等価性の破壊。異なる値のhash相違は要求しない |
| `test_inequality_different_values` (39) | R | slot/range/mpの各差を非等価とする。比較項目を1つ外す |
| `test_info_is_frozen` (51) | R | slot/range/mpの全3属性は代入不可。どれかの公開値を可変化 |

