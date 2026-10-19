# プレイヤーの結果と対象可否の試験監査

## なぜ

対象の状態を問う試験が、許可でも任意の拒否でも通っていた。蘇生の正の対照も、成功しなくても死亡拒否の文言がなければ通る条件だった。判定と実際の身体変化を検査する保持先を先に作り、同じ入力の重複だけをまとめた。

製品コードは変更していない。結果の語彙・表示、終局後の不変性、通知の値と回数、未確定者の照会、呼出元から共通判定への配線を保持する。

## 範囲と判断

基準は main `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。割当3ファイルの36宣言を全て読み、R27（保持）、F2（検査修理）、C7（保持先へ統合）、D0（契約なしの削除）と判断した。最終はdomainに27宣言、既存applicationファイルへ移した2宣言の計29宣言。保持先にもともとある12宣言は今回の36宣言へ加算しない。

- `test_actionable_target.py`: ACTIVE・INCAPACITATED・PRESENTと立位・昏倒を組み合わせた6入力で、許可か正確な拒否コードかを検査する。元の同一入力5宣言をこの表へ統合した。自己・別地点・行為者昏倒・退場・手当て対象の死亡確定・拒否理由は残した
- `test_player_outcome.py`: Enum3宣言とRegistry10宣言を全て保持。空集合や未登録IDの既定動作は実際の公開契約であり、一括して削除しない
- `test_player_outcome_elimination.py`: 退場True2行とFalse3行を主担当とし、「少なくとも一つTrue/False」の2宣言だけを統合。EJECTEDの保存語彙、DEADとの区別、確定性と表示差、全メンバのbool型検査は残した。bool型検査だけで将来の結果の意味まで決まる、という説明は訂正した
- 手当ての2宣言: `tests/application/llm/services/executors/test_spot_graph_tend_to_player.py` へ移した。既存の実PlayerStatusAggregateの準備を使い、元と同じin-scope入口・ID1/2・地点1・対象名セナ・DEAD/UNRESOLVEDを保持。死亡拒否のFalseと「戻らない」は維持し、成功はTrue・昏倒解除・HP60で検査する

## 所有者と別の層

ドメインの対象判定はexecutorと対人操作サービスから使われる。結果レジストリはランタイムの生成、死亡猶予、会議、結果規則、保存復元から使われる。これらの所有者は試験だけの機能ではない。なお、`all_resolved` と `unresolved_player_ids` の直接の製品呼出元は見つからなかった。導入時から明示された公開照会契約として保持し、今回のテスト限定監査ではAPI撤去を扱わない。

判定関数を直接調べる試験と、executorが確定結果をその判定へ渡す試験は異なる責任を持つ。移管した手当て試験も公開ツール全体の確定区間を保証するとは主張せず、元の `_execute_tend_to_player_in_scope` の配線を守る。確定区間未配線を拒む既存application試験はそのまま残した。

graph終局判定のPR #1744、所持品の #1699、状態・成長の #1722〜#1732 は別の編集範囲。最新83本の公開案のheadと変更パスを照合し、対象テストとの直接衝突はなかった。他のPRは編集していない。

## 背景の一次資料

- [対象判定の導入](https://github.com/Motifman/llm-rpg/commit/a18c5f55ed1dc2ab19a21cc78566cf39eb64fe56): is_downだけでは確定死者を蘇生できたため、結果も共通判定へ渡す。拒否理由とエラーコードは行動ごとに保持する
- [確定区間を必須化](https://github.com/Motifman/llm-rpg/commit/a4fad8f7244fb58a2347008dfec90947f12d993a): 公開入口と確定区間内の処理を分離した
- [個別結果の導入](https://github.com/Motifman/llm-rpg/commit/78c051c61b002c597decf1b1e270382d6da3f35c): 集団勝敗と分け、初期状態・一度限りの確定・通知・空集合の扱いを定義した
- [追放の導入](https://github.com/Motifman/llm-rpg/commit/b204677f43c7ffc00b32d87310c70ac9529984ce): 死と追放を区別し、救助と取り残されを全滅数へ混ぜない
- `docs/design_decisions.md` の58・60・61、および `docs/memory_system/meeting_and_voting_design.md` §6.2: 結果・身体状態・表示と保存の責任を分ける

## 試験と対照

安全なオフライン実行で、元の所有44件と関連47件の一意91件が成功した。保持先を先に追加して旧試験も共存させた64件も成功。その後の最終所有40件と関連49件の一意89件が成功した。関連には手当てexecutor、結果codec、追放の実行経路、陣営全滅評価、ダウンhandlerを含む。これは全リポジトリの試験結果ではない。

7種類を旧新それぞれに当て、計14実行で意図した検査の成否を確認した。

| 意図的な欠陥 | 元の対象試験 | 保持先 |
|---|---|---|
| PRESENTを誤って拒否 | 成功して見逃す | None検査で失敗 |
| ACTIVE/INCAPACITATEDの状態ガードを省略 | 元の網羅ループは成功して見逃す | 非None検査で失敗 |
| UNRESOLVEDの手当てを一般失敗へする | OR条件が成功して見逃す | success=True検査で失敗 |
| revive呼出だけ省略 | OR条件が成功して見逃す | 実状態is_down検査で失敗 |
| 全結果を非退場にする | 失敗 | DEAD/EJECTEDの厳密Trueで失敗 |
| 全結果を退場にする | 失敗 | UNRESOLVED/RESCUED/STRANDEDの厳密Falseで失敗 |
| 死亡確定ガードを省略 | 失敗 | 移管後もsuccess=Falseで失敗 |

ここでの旧試験は指定した宣言との比較であり、旧suite全体がこれらを全て見逃すとは主張しない。特にACTIVE/INCAPACITATEDの旧個別試験は同じガード省略を検出しており、その検出力を表へ移した。

各対照の製品変更は復元済みで、追跡中の製品1601ファイルのハッシュ一致を確認した。変更ファイルのruffと `git diff --check` も成功。基準不具合は見つからなかった。編集前の独立第二読を受け、編集後の保持レビューでも元の入力・検査と保持先を照合する。

## 行数

- 割当テスト: 489行 → 378行
- 移管先の既存テストも含めると778行 → 721行、純減57行
- このうち埋込の準備関数は103行 → 91行、純減12行
- 製品コード: 増減0行。別の共通支援ファイル: 増減0行

## 元の全36宣言と保持先

識別子はコードの実名を残す。Rの手当て拒否1本は移管、Fの正の対照1本も同じ保持先へ移した。

| 元の宣言 | 判断 | 保持先・保証 |
|---|---|---|
| `TestUniversalRules::test_a_valid_target_passes` | C | TestEveryRequirementIsHandled::test_each_requirement_checks_both_target_states。同席し双方活動中で結果未確定の相手はACTIVE要求を通る |
| `TestUniversalRules::test_you_cannot_target_yourself` | R | 同じ宣言。本人IDと対象IDが同じならTARGET_IS_SELFを返す |
| `TestUniversalRules::test_a_target_elsewhere_is_rejected` | R | 同じ宣言。同席していなければNOT_IN_SAME_SPOTを返す |
| `TestUniversalRules::test_a_downed_actor_cannot_act_on_others` | R | 同じ宣言。倒れた行為者はACTOR_IS_DOWNで拒否する |
| `TestUniversalRules::test_an_eliminated_target_is_rejected` | R | 同じ宣言。DEADとEJECTEDはACTIVE要求でもTARGET_IS_ELIMINATEDで拒否する |
| `TestRequirementActive::test_a_downed_target_is_rejected` | C | TestEveryRequirementIsHandled::test_each_requirement_checks_both_target_states。ACTIVE要求は倒れた相手をTARGET_IS_DOWNで拒否する |
| `TestRequirementActive::test_a_standing_target_passes` | C | TestEveryRequirementIsHandled::test_each_requirement_checks_both_target_states。ACTIVE要求は立っている相手を通す |
| `TestRequirementIncapacitated::test_a_standing_target_is_rejected` | C | TestEveryRequirementIsHandled::test_each_requirement_checks_both_target_states。INCAPACITATED要求は立っている相手をTARGET_IS_NOT_DOWNで拒否する |
| `TestRequirementIncapacitated::test_a_downed_target_passes` | C | TestEveryRequirementIsHandled::test_each_requirement_checks_both_target_states。INCAPACITATED要求は倒れた相手を通す |
| `TestRequirementIncapacitated::test_an_eliminated_target_is_still_rejected` | R | 同じ宣言。INCAPACITATED要求でもDEAD確定はTARGET_IS_ELIMINATEDで拒否する |
| `TestEveryRequirementIsHandled::test_no_requirement_falls_through_silently` | F | TestEveryRequirementIsHandled::test_each_requirement_checks_both_target_states。全TargetRequirementについて立位・昏倒の双方を評価する。元のassertはNone又は非空コードのみで、許可と拒否の取り違えを見逃す |
| `TestEveryRequirementIsHandled::test_a_rejection_always_carries_a_message` | R | 同じ宣言。自己・別地点・行為者昏倒・死亡確定・対象昏倒の各拒否には非空メッセージがある |
| `TestTendNoLongerRevivesTheConfirmedDead::test_a_confirmed_dead_target_cannot_be_revived` | R | application: TestTendNoLongerRevivesTheConfirmedDead::test_a_confirmed_dead_target_cannot_be_revived。実executor入口がレジストリのDEADを共通判定へ渡し、失敗と「戻らない」の説明を返す |
| `TestTendNoLongerRevivesTheConfirmedDead::test_a_merely_downed_target_can_still_be_revived` | F | application: TestTendNoLongerRevivesTheConfirmedDead::test_a_merely_downed_target_can_still_be_revived。実executor入口でUNRESOLVEDの昏倒者を蘇生できる。元のORは成功以外でも「戻らない」がなければ通る |
| `TestPlayerOutcomeEnum::test_unresolved` | R | 同じ宣言。UNRESOLVED.is_resolvedはFalse |
| `TestPlayerOutcomeEnum::test_rescued_dead_stranded` | R | 同じ宣言。RESCUED/DEAD/STRANDED.is_resolvedはTrue |
| `TestPlayerOutcomeEnum::test_display_label_japanese` | R | 同じ宣言。RESCUED/DEAD/STRANDEDの表示は救助/死亡/取り残され |
| `TestRegistryInit::test_new_players_all_players_unresolved` | R | 同じ宣言。new_for_players([1,2])は両IDをUNRESOLVEDに初期化する |
| `TestRegistryInit::test_unregistered_player_get_outcome_unresolved` | R | 同じ宣言。未登録99の取得はUNRESOLVEDを返す |
| `TestRegistryInit::test_empty_registry_all_resolved_true` | R | 同じ宣言。空レジストリのall_resolvedはTrue |
| `TestSetOutcome::test_unresolved_dead_treated_changed` | R | 同じ宣言。未確定1をDEADへ変更するとTrueを返しDEADを保持する |
| `TestSetOutcome::test_resolved_op` | R | 同じ宣言。RESCUED確定後のDEADはFalseを返しRESCUEDを保持する |
| `TestSetOutcome::test_unresolved_op` | R | 同じ宣言。UNRESOLVEDへの再設定はFalseを返す |
| `TestCallback::test_calls_callback` | R | 同じ宣言。結果変更の通知はID1・旧UNRESOLVED・新DEADの1件 |
| `TestCallback::test_resolved_set_callback_does_not_call` | R | 同じ宣言。確定後の再設定は通知を追加しない |
| `TestAggregateQueries::test_all_players_all_resolved_true` | R | 同じ宣言。2人をRESCUEDとDEADへ確定するとall_resolvedはTrue |
| `TestAggregateQueries::test_one_unresolved_rendered` | R | 同じ宣言。3人中1だけ確定すると未確定ID集合は正確に{2,3} |
| `TestEjectedIsItsOwnOutcome::test_ejected_exists` | R | 同じ宣言。EJECTEDの保存・分析語彙は文字列EJECTED |
| `TestEjectedIsItsOwnOutcome::test_ejected_is_not_dead` | R | 同じ宣言。EJECTEDとDEADは異なる結果として区別できる |
| `TestEjectedIsItsOwnOutcome::test_ejected_is_resolved` | R | 同じ宣言。EJECTEDは終局済みで再遷移不可の対象 |
| `TestEjectedIsItsOwnOutcome::test_ejected_has_its_own_label` | R | 同じ宣言。EJECTEDの表示はDEADと異なる |
| `TestEliminationPredicate::test_removed_outcomes_are_eliminated` | R | 同じ宣言。DEADとEJECTEDは厳密なTrueで退場を表す |
| `TestEliminationPredicate::test_others_are_not_eliminated` | R | 同じ宣言。UNRESOLVED/RESCUED/STRANDEDは厳密なFalseで非退場を表す |
| `TestEveryMemberDeclaresElimination::test_predicate_is_a_bool` | R | 同じ宣言。全enumメンバのis_eliminatedはbool。将来メンバの意味選択を強制する試験とは主張しない |
| `TestEveryMemberDeclaresElimination::test_at_least_one_member_is_eliminated` | C | TestEliminationPredicate::test_removed_outcomes_are_eliminated。少なくとも一つ退場結果がある。既存のDEAD/EJECTEDの厳密True表に包含される |
| `TestEveryMemberDeclaresElimination::test_at_least_one_member_is_not` | C | TestEliminationPredicate::test_others_are_not_eliminated。少なくとも一つ非退場結果がある。既存のUNRESOLVED/RESCUED/STRANDEDの厳密False表に包含される |
