# Monster の観測・状態入力・遷移適用の試験契約

## 範囲と結論

残っていた元38宣言を読み、R21（保持）/F8（修理）/C9（統合）/D0と判定した。今回は通知仕様の判断を要するF1を保留し、元37宣言の監査を完了した。保留試験は削除せず、元の本文・入力・確認式を保持する。

対象は観測からの遷移意図20、状態snapshot6、遷移適用とEventSpec12の3ファイル。37の内訳はR21/F7/C9。9宣言の統合により、対象は38宣言38実行行から29宣言48実行行になった。表の行数は入力を独立に保つためのもので、完了宣言数とは分けて数える。

同じファイルにある先行被弾13・縄張り7は、現在の17宣言26実行行をデコレータを含め全文・AST不変で保持した。先行範囲と関連試験を今回の完了に加算しない。製品と共有支援コードの変更はない。

## 基準と依存関係

- 元の主基準: `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`
- この変更の固定base: #1721 の `237b5394cec4aeb3200983ac88cdc86ed1903cab`、branch `codex/test-audit-monster-territory-20261014`
- #1719の被弾判断と#1721の縄張り判断が同じ試験ファイルを変更しているため、その成果に積む。元38宣言の本文ASTは主基準と一致する
- 監査開始時の最新mainとopen59件を再照合し、対象3試験の変更が重なるものは上記の依存2件だけだった

## 主担当と他層に残す契約

| 境界 | 主担当 | 別に残す証拠 |
| --- | --- | --- |
| 観測から遷移意図を作る | `BehaviorStateTransitionService.compute_transition` | `MonsterBehaviorCoordinator.process_actor_behavior` が実観測と集約snapshotを渡す接続 |
| snapshotの値・既定・外部変更拒否 | `BehaviorStateSnapshot` | 集約 `to_behavior_state_snapshot` のHP/テンプレート/tuple変換 |
| 状態・追跡命令・通知仕様の計算 | `MonsterBehaviorStateMachine.apply_transition` | 集約 `apply_behavior_transition` の実状態・追跡実体・実イベントへの反映 |

`clear_pursuit=True` は純粋サービスが返す解除命令として検査する。追跡を実際に終了したことや通知の外部配信は、この試験の保証には含めない。EventSpecの生成3件は実際の適用計算が同じ値を生成する試験へ移し、集約のイベント変換とは混同しない。

SpotTargetParamsの必須引数だけの生成は独立した既定値契約として残した。compute_transitionは省略時にもNoneを明示して渡すため、観測側だけではコンストラクタの既定値の誤変更を捕捉できない。SpotTargetParamsとsnapshotの属性代入拒否も残す。

snapshotの実入力は全てtupleである。返却値のtuple型・等値・append拒否を移管先でも保持した。リストを受理してコピーする新しい仕様は追加していない。テンプレートのリストをtupleにするのは集約側の責務である。

## 修理した7契約と具体的な入力

- ENRAGEは先頭phase閾値以下だけ。旧HP0.3/phase=(0.5,0.25)を残し、0.5と0.51を追加した。0.3は2番目の閾値を使う誤りの対照にもなる
- 最寄り脅威は直線距離で選ぶ。actor=(5,5)、旧2脅威と旧3脅威の順序・全座標を残した。(10,5)対(8,8)はマンハッタンと、(9,9)対(10,5)はチェビシェフと順位が逆転する。期待id/座標は固定値で書いた
- 空適用では旧IDLE/None/Noneを残し、CHASE/target4001/(4,6)を追加した。状態・対象・位置の誤消去を別々に検出する
- 単独の脅威逃走は旧id999/(10,10)の状態と命令を保持し、spottedの座標とIDLE→FLEEの値、各1件の仕様だけを返すことを検査した
- spotは元2001/(2,1)/HP1/明示0・True/既定0.2・Trueを残した。元EventSpecの1/(2,3)、明示0の有効性、True/Falseの既定上書き、None時の既定利用を別行にした
- spotのHP境界は旧0.3/明示0.5/既定0.2を残し、0.5、0.51、明示Noneで既定0.5を使う行を追加した。状態・追跡命令・仕様値を固定期待値と比較した
- 対象喪失では旧CHASE/321/(7,8)を残し、元EventSpecの2/(4,5)を追加した。喪失の最終位置とCHASE→SEARCHが各1件であることを検査した

単独遷移の仕様は件数・種別ごとの一意性・値を比較する。新たなイベント順序の保証は追加していない。

## 元38宣言の台帳

Rのうち統合先になる4宣言は元入力と全確認式を保って拡張した。残るR17と保留1は全文・ASTを変更していない。C9は旧入力と全確認式を移管先へ入れ、元C9を残した段階版57件の成功を確認してから除去した。

### 観測からの意図20: `test_behavior_state_transition_service.py`

| 元宣言 | 判定 | 守る契約・保持先 |
| --- | --- | --- |
| `TestSpotTargetParams.test_create_with_required` | R | target1/(5,5)の指定値とoptional省略時のNoneを守る公開生成契約。compute_transitionはNoneも明示して生成するため、観測側だけへ移すとdataclass既定値の誤変更を見逃す。旧CをRへ訂正する。 |
| `TestSpotTargetParams.test_create_with_optional` | C | 指定threshold0.3/allowTrueの格納は、実観測からSpotTargetParamsを生成する主試験へ旧target2/(3,4)入力を追加して保持できる。 保持先: `TestBehaviorStateTransitionServiceNormal.test_compute_transition_spot_target_when_selected_target_no_threats`。旧target2/(3,4),threshold0.3,allowTrueの行を、元target1/(7,5)を残して主試験へ追加する。旧2assertに加えid/座標の出力も検査する。 |
| `TestSpotTargetParams.test_spot_target_params_is_frozen` | R | SpotTargetParamsの外部属性代入拒否。遷移計算の読み取り専用結果が可変になる退行を防ぐ |
| `TestStateTransitionResult.test_create_defaults` | C | compute_transitionの無変化経路はStateTransitionResult()を実際に生成してそのまま返すため、7既定値の主所有者にできる。 保持先: `TestBehaviorStateTransitionServiceNormal.test_compute_transition_no_change_returns_empty_result`。元のapply_enrage=False、flee_id/coordinate=None、spot=None、do_lose=False、lost_id/last_known=Noneをすべて実計算の空結果へ移す。StateTransitionResultの生成入力は同じ引数なし。 |
| `TestBehaviorStateTransitionServiceNormal.test_compute_transition_no_change_returns_empty_result` | R | 観測も対象もphaseもない時に何も遷移しない。無条件FLEE/CHASE/loseの退行を捕捉 |
| `TestBehaviorStateTransitionServiceNormal.test_compute_transition_enrage_only_when_phase_below_threshold` | F | 0.3だけでは閾値等値と上側拒否を守れない。先頭閾値0.5、次0.25はそのまま、HP0.3/0.5/0.51を検査する。0.3は次閾値より大きく、先頭利用の既存対照でもある。 保持先: `TestBehaviorStateTransitionServiceNormal.test_compute_transition_enrage_at_first_phase_threshold`。 |
| `TestBehaviorStateTransitionServiceNormal.test_compute_transition_enrage_not_applied_when_already_enrage` | R | 既にENRAGEなら重複適用しない。phase条件のみで何度もイベントを生成する退行を防ぐ |
| `TestBehaviorStateTransitionServiceNormal.test_compute_transition_enrage_not_applied_when_already_flee` | R | FLEEをENRAGEで上書きしない。逃走優先の別状態拒否契約 |
| `TestBehaviorStateTransitionServiceNormal.test_compute_transition_flee_when_visible_threats` | F | 旧2脅威と重複側3脅威の全入力を残し、距離順位が逆転する2行を追加する。直線距離方式は抽出前StrategyとCoordinate公開APIで根拠付ける。 保持先: `TestBehaviorStateTransitionServiceNormal.test_compute_transition_selects_nearest_threat_by_euclidean_distance`。 |
| `TestBehaviorStateTransitionServiceNormal.test_compute_transition_spot_target_when_selected_target_no_threats` | R | 脅威なし対象ありでid/座標/growth値を伝播しloseなし。成長条件取り違えを捕捉 |
| `TestBehaviorStateTransitionServiceNormal.test_compute_transition_lose_target_when_no_threats_no_selected_has_target_id` | R | CHASEから対象喪失意図を作りid/最終位置を保持。共有pursuitへの接続に必要な情報消失を検出 |
| `TestBehaviorStateTransitionServiceNormal.test_compute_transition_lose_target_last_known_none` | R | 最後の位置が未知でもidつきlose意図を返す。位置Noneで例外/喪失抑止になる退行を捕捉 |
| `TestBehaviorStateTransitionServiceNormal.test_compute_transition_search_preserves_existing_target_identity` | R | SEARCH継続で対象identityを保持。実バグ8a43436由来、CHASE限定処理へ戻す退行を防ぐ |
| `TestBehaviorStateTransitionServiceNormal.test_compute_transition_search_reacquires_same_target_as_normal_spot_target` | R | SEARCHから同じ対象を再発見すると通常spot意図へ戻る。6c15d81由来の再捕捉回帰 |
| `TestBehaviorStateTransitionServiceBoundary.test_visible_threats_take_priority_over_selected_target` | R | 脅威と選択対象が同時にあれば脅威優先でspotなし。条件順序逆転を捕捉 |
| `TestBehaviorStateTransitionServiceBoundary.test_enrage_then_flee_when_phase_and_visible_threats` | R | phase0.3/0.5と脅威200/(6,5)からapply_enrage=Trueとflee_id=200という両意図を返す契約を保持する。ここは通知を生成しない。適用側の最終状態と通知先の整合は証明せず、named deferの解消とは数えない。 |
| `TestBehaviorStateTransitionServiceBoundary.test_already_flee_does_not_trigger_spot_target` | R | FLEE中は選択対象がいてもspot意図を返さない。既存逃走を追跡へ切替える退行を防ぐ |
| `TestBehaviorStateTransitionServiceBoundary.test_already_flee_with_visible_threats_no_duplicate_flee` | R | 既FLEE時は見える脅威で重複逃走意図を生成しない。再通知/相手変更の退行を防ぐ |
| `TestBehaviorStateTransitionServiceBoundary.test_nearest_threat_selected_among_multiple` | C | 最寄り脅威という同一契約の別具体入力。元far203/(0,0),mid202/(8,5),near201/(5,6)と順序を主試験の別行へ移して2assertを保持する。 保持先: `TestBehaviorStateTransitionServiceNormal.test_compute_transition_selects_nearest_threat_by_euclidean_distance`。元3脅威の入力順序とid/coordinateの2assertをformer_three_threats行へ移す。元2脅威も残す。 |
| `TestBehaviorStateTransitionServiceGrowthContext.test_spot_target_params_without_growth_context` | R | growth省略時は閾値/追跡許可をNoneで渡し適用側の既定に委ねる。無条件False/0を詰める退行を捕捉 |

### 入力snapshot6: `test_behavior_state_snapshot.py`

| 元宣言 | 判定 | 守る契約・保持先 |
| --- | --- | --- |
| `TestBehaviorStateSnapshotCreation.test_create_with_required_only` | R | stateのみの既定値は公開生成契約。元IDLE省略入力と明示既定CHASE入力を同じ生成表の別行として保持する。 保持先: `TestBehaviorStateSnapshotCreation.test_create_with_default_values`。 |
| `TestBehaviorStateSnapshotCreation.test_create_with_defaults_explicit` | C | 指定既定値は同じ公開コンストラクタの表へ統合する。引数省略と明示指定の経路差は2行を分けて保持する。 保持先: `TestBehaviorStateSnapshotCreation.test_create_with_default_values`。元CHASE、targetNone、lastNone、hp1、空tuple、flee0の明示入力を丸ごと別行へ保持し、元state/target/phaseの3assertを含める。 |
| `TestBehaviorStateSnapshotCreation.test_create_with_all_fields` | R | 全6指定値の格納は独立した公開値契約。単一tupleと元append入力を加え、tuple返却型とappend不可も実際の戻り値に対して保持する。 保持先: `TestBehaviorStateSnapshotCreation.test_create_preserves_values_and_immutable_thresholds`。 |
| `TestBehaviorStateSnapshotCreation.test_create_with_tuple_phase_thresholds` | C | IDLE・tuple(0.5,)の値と型という契約を同じ公開生成表へ移す。tupleであることを単に組込み確認として捨てない。 保持先: `TestBehaviorStateSnapshotCreation.test_create_preserves_values_and_immutable_thresholds`。元IDLE/phase=(0.5,)の2引数入力と、tuple等値・isinstance(tuple)をsingle_threshold_tuple行へ移す。 |
| `TestBehaviorStateSnapshotImmutability.test_snapshot_is_frozen` | R | state/target/hpの外部属性代入拒否。計算snapshotが可変になる退行を捕捉 |
| `TestBehaviorStateSnapshotImmutability.test_phase_thresholds_is_immutable_tuple` | C | 元の実入力はIDLEとtuple(0.5,0.25)。返却値のappend拒否は公開不変性契約として保持する。名前・説明のlist受理主張は根拠がなく、VOへ変換仕様を追加しない。 保持先: `TestBehaviorStateSnapshotCreation.test_create_preserves_values_and_immutable_thresholds`。元IDLE/phase=(0.5,0.25)の2引数入力とappend(0.1)のAttributeErrorをformer_append_input行へ移す。既存全指定/単一tupleの行と混同しない。 |

### 適用とEventSpec12: `test_monster_behavior_state_machine.py`

| 元宣言 | 判定 | 守る契約・保持先 |
| --- | --- | --- |
| `TestEventSpec.test_create_target_spotted` | C | EventSpecのkind/id/coordinate指定値を、apply_transitionが実生成する同じ値の出力へ移す。集約の実イベント変換を検査したとは称しない。 保持先: `TestSpotTargetParams.test_spot_target_parameters_select_state_and_pursuit`。元target1/coordinate(2,3,0)/kind target_spottedの3assertをformer_spotted_spec行へ移す。旧target2001/(2,1)行は置換しない。 |
| `TestEventSpec.test_create_target_lost` | C | target_lostの生成契約はapply_transitionの実生成出力へ旧id2/(4,5)で移す。 保持先: `TestDoLoseTarget.test_lose_target_chase_to_search_preserve_pursuit`。元kind target_lostとlast_known(4,5,0)の2assert、指定したtarget2をformer_lost_spec行へ移す。元target321/(7,8)は保持。 |
| `TestEventSpec.test_create_actor_state_changed` | C | CHASE→SEARCHのkind/old/newは同じ状態対の実喪失適用で検査できる。 保持先: `TestDoLoseTarget.test_lose_target_chase_to_search_preserve_pursuit`。元kind actor_state_changed、old CHASE、new SEARCHの3assertは旧CHASE→SEARCH主試験の同じ行へ保持。一意性確認を追加するが順序は固定しない。 |
| `TestMonsterBehaviorStateMachineApplyTransition.TestEmptyResult.test_empty_result_returns_unchanged_state` | F | IDLE/targetNone/positionNoneだけでは既定値への誤消去を見逃す。旧行を残しCHASE/target4001/(4,6,0)を追加して独立に保持を検査する。 保持先: `TestEmptyResult.test_empty_result_preserves_current_state_and_target`。 |
| `TestMonsterBehaviorStateMachineApplyTransition.TestApplyEnrage.test_apply_enrage_updates_state_and_emits_event` | R | ENRAGEのみの適用でstateとちょうど1つのold/newイベントを確認。通知の向き/重複を捕捉 |
| `TestMonsterBehaviorStateMachineApplyTransition.TestFleeFromThreat.test_flee_from_threat_updates_state_clears_pursuit` | F | 元IDLE→FLEE、id999/(10,10)の値とclear/sync命令を保持し、anyの代わりに一意な各EventSpecの座標・old/new・件数を検査する。実追跡の解除や外部通知配信はこの純粋出力試験の主張にしない。 保持先: `TestFleeFromThreat.test_flee_from_threat_updates_state_clears_pursuit`。 |
| `TestMonsterBehaviorStateMachineApplyTransition.TestFleeFromThreat.test_flee_with_apply_enrage_emits_both` | F（保留） | named defer MONSTER_ENRAGE_FLEE_EVENT_CONSISTENCY。最終FLEEに対しIDLE→ENRAGE通知のみという既存再現がある。意図した通知仕様の決定が必要なため本文・入力・assertは一切編集せず未完とする。 保持先: `TestFleeFromThreat.test_flee_with_apply_enrage_emits_both`。 |
| `TestMonsterBehaviorStateMachineApplyTransition.TestSpotTargetParams.test_spot_target_chase_sync_pursuit` | F | 旧target2001/(2,1),HP1,明示0/Trueと既定0.2/Trueを残す。0とFalseを未指定と誤認する退行、allowの上書き無視、None時の既定利用、EventSpecの内容/重複を検査する。 保持先: `TestSpotTargetParams.test_spot_target_parameters_select_state_and_pursuit`。 |
| `TestMonsterBehaviorStateMachineApplyTransition.TestSpotTargetParams.test_spot_target_hp_low_goes_flee_clear_pursuit` | F | 元HP0.3・明示閾値0.5・既定0.2の上書き入力を保持し、等値/直上および未指定時の既定0.5を追加。state/clear/syncを独立期待値で検査する。 保持先: `TestSpotTargetParams.test_spot_target_hp_boundary_selects_flee_or_chase`。 |
| `TestMonsterBehaviorStateMachineApplyTransition.TestDoLoseTarget.test_lose_target_chase_to_search_preserve_pursuit` | F | 旧CHASE/target321/(7,8)の保持・SEARCH・pursuit命令を残し、target_lostのlast_known値と一意性、状態変更のold/newと一意性を検査する。 保持先: `TestDoLoseTarget.test_lose_target_chase_to_search_preserve_pursuit`。 |
| `TestMonsterBehaviorStateMachineApplyTransition.TestDoLoseTarget.test_lose_target_flee_to_return_clear_pursuit` | R | FLEEで対象喪失するとRETURN、target/位置/pursuitを解除。CHASE→SEARCHとは別の終端契約 |
| `TestMonsterBehaviorStateMachineApplyTransition.TestDoLoseTarget.test_lose_target_reuses_existing_last_known_when_omitted` | R | last_known未指定なら既存位置を採用してSEARCHとpursuit保持。None伝播による追跡消失を捕捉 |

## 履歴と実利用者

- [状態遷移の抽出](https://github.com/Motifman/llm-rpg/commit/3d096463feca28d4b95752c182ae6da424536677): 抽出前のStrategyから直線距離と先頭phase閾値以下が確認できる。snapshotは導入時からfrozen/tupleで、呼出元がtuple化する
- [集約から適用状態機械を抽出](https://github.com/Motifman/llm-rpg/commit/3eca42d7dc8eec5d8879c28cea6d345277f45bef): 現在の状態、対象、追跡操作とEventSpecの所有境界を確認した
- [SEARCH時の情報保持修理](https://github.com/Motifman/llm-rpg/commit/8a4343639e4ded0124557bcb81b8ccf746d91cab)と[同一対象再捕捉の回帰](https://github.com/Motifman/llm-rpg/commit/6c15d81cdc28d92f44663c05ea73adcc51e96b18): SEARCH継続、欠損位置の再利用、再捕捉を別の意味ある契約として残した

製品の入口は `application/world/services/monster_behavior_coordinator.py`。集約のsnapshot生成からcompute_transition、apply_behavior_transitionの順につなぐ。EventSpecの実生成は状態機械、実イベントへの変換は `MonsterAggregate._emit_behavior_event` が担当する。観測formatterは状態変更のold/newを表示する。TargetSpotted/Lostは現在の観測配信から意図的に除外されているが、内部出力値の契約を捨てる理由にはしていない。

## 検証と旧新対照

- 事前に入れ子を含むnodeidをASTで検証。未編集の対象38＋関連9＝47件が初回成功
- C9を残した移管確認57件、C9除去後の候補48件が成功
- 21改善・15保存・2意味保持の38組76実行。専用作業ツリー、各実行で別cache、安全runner、直列実行を使用
- 改善21は旧38件が全成功し、新しい予定行の確認式で失敗した。1変更を複数行が検出する場合もあり、各実行の失敗名と本文を全て照合した
- 保存15は元の具体入力/確認式と新しい保持先の双方が意図した理由で失敗した。収集失敗、準備失敗、skipは0
- snapshotのlist化は型/等値で失敗し、appendを許すtuple派生値では型/等値を通過した後に旧append試験と新しい元入力行がともにDID NOT RAISEとなった。2つの失敗理由を区別した
- 意味保持2は距離の二乗による同順位選択と、同じ順序のイベントリスト複製。旧38/新48がともに成功

以下の数は「成功/失敗」。保存対照で他の同じ値契約も赤になる場合を隠さず、その失敗も独立レビューで確認した。

| 対照 | 種類 | 旧38 | 新48 |
| --- | --- | --- | --- |
| `01_enrage_strict` | 改善 | 38/0 | 47/1 |
| `02_enrage_above_ignored` | 改善 | 38/0 | 47/1 |
| `03_nearest_manhattan` | 改善 | 38/0 | 47/1 |
| `04_nearest_chebyshev` | 改善 | 38/0 | 47/1 |
| `05_empty_state_reset` | 改善 | 38/0 | 47/1 |
| `06_empty_target_reset` | 改善 | 38/0 | 47/1 |
| `07_empty_position_reset` | 改善 | 38/0 | 47/1 |
| `08_flee_event_coordinate` | 改善 | 38/0 | 47/1 |
| `09_flee_event_old_state` | 改善 | 38/0 | 47/1 |
| `10_flee_event_duplicate` | 改善 | 38/0 | 47/1 |
| `11_spot_zero_as_missing` | 改善 | 38/0 | 47/1 |
| `12_spot_allow_override_ignored` | 改善 | 38/0 | 46/2 |
| `13_spot_false_as_missing` | 改善 | 38/0 | 47/1 |
| `14_spot_allow_none_false` | 改善 | 38/0 | 47/1 |
| `15_spot_hp_strict` | 改善 | 38/0 | 47/1 |
| `16_spot_threshold_none_zero` | 改善 | 38/0 | 47/1 |
| `17_spot_event_coordinate` | 改善 | 38/0 | 38/10 |
| `18_spot_state_event_missing` | 改善 | 38/0 | 39/9 |
| `19_spot_event_duplicate` | 改善 | 38/0 | 38/10 |
| `20_lose_event_coordinate` | 改善 | 38/0 | 46/2 |
| `21_lose_event_duplicate` | 改善 | 38/0 | 46/2 |
| `22_optional_threshold` | 保存 | 37/1 | 47/1 |
| `23_optional_allow` | 保存 | 37/1 | 47/1 |
| `24_default_flee_coordinate` | 保存 | 36/2 | 46/2 |
| `25_default_lost_id` | 保存 | 37/1 | 47/1 |
| `26_default_last_known` | 保存 | 37/1 | 47/1 |
| `27_former_three_threats` | 保存 | 37/1 | 47/1 |
| `28_spec_spotted_target` | 保存 | 37/1 | 47/1 |
| `29_spec_spotted_coordinate` | 保存 | 37/1 | 47/1 |
| `30_spec_lost_coordinate` | 保存 | 37/1 | 47/1 |
| `31_spec_changed_old` | 保存 | 36/2 | 46/2 |
| `32_spec_changed_new` | 保存 | 36/2 | 46/2 |
| `33_snapshot_explicit_state` | 保存 | 37/1 | 47/1 |
| `34_snapshot_single_tuple` | 保存 | 37/1 | 47/1 |
| `35_snapshot_list_return` | 保存 | 33/5 | 43/5 |
| `36_snapshot_append_allowed` | 保存 | 37/1 | 47/1 |
| `37_lawful_squared_distance` | 意味保持 | 38/0 | 48/0 |
| `38_lawful_event_list_copy` | 意味保持 | 38/0 | 48/0 |

最寄りの保存対照27は、1脅威の構築例外を避け、3個以上のときだけ2番目を選ぶ変更にした。元3脅威と移管先だけがmidの誤選択で失敗し、旧2脅威や新しい距離方式の行を代わりの証拠にしていない。

対照終了後、候補と変異用の両作業ツリーで全1601製品.pyのhashが基準と完全一致した。変異用の旧試験3ファイルも完全復元した。復元後は3ファイル全体74＋関連9＝一意83件が成功した。内訳は今回対象48（保留1を含む）、先行被弾16、先行縄張り10、関連9。Python3.10.22/pytest8.4.1、資格情報除去・ネット遮断・自身のsrcを使った。全リポジトリのローカル実行は行っていない。

Ruff0.16.8とgit diff --checkも成功。試験3ファイルは1109→1156行（+242/-195）。共有支援・製品の変更0。公開する正確なコミットのCIは別途確認する。

## 仕様判断を要する1件

`MONSTER_ENRAGE_FLEE_EVENT_CONSISTENCY` として `test_flee_with_apply_enrage_emits_both` を保留した。既存の公開集約とformatterまでの再現では、最終状態FLEEに対し状態変更通知のnew_stateがENRAGEだった。通知先と件数の期待仕様は決めていない。現状の通知を新しい正解として固定せず、製品修理も行わない。

観測側の `test_enrage_then_flee_when_phase_and_visible_threats` は2つの意図を返す契約として保持する。このRの完了は、適用側の実通知の整合性を解決したことを意味しない。関連試験や既知製品質問は今回の37宣言に加算しない。
