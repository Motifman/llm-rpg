# クエストの完了条件と拒否後の状態保存

## 目的と範囲

クエストの試験は、受託や取消の拒否を例外だけで確認していたため、例外前に状態を書き換えたり、未発行イベントを増減したりする誤りを見逃していた。また、全目標達成の条件を単一目標でしか確かめておらず、「全て」を「どれか」に変える誤りを区別できなかった。

対象は `tests/domain/quest/test_quest_aggregate.py` の全33宣言と、所有者 `src/ai_rpg_world/domain/quest/aggregate/quest_aggregate.py`。固定基準は `0b51eb28d4692635a932dcf4063ab9b231768bf0`。製品コードは変更しない。

この変更は既存試験の検出力の改善であり、現行製品の不具合修正ではない。クエスト領域の全ファイルや全リポジトリの監査完了も意味しない。

## 変更

- 別人による再受託、直接依頼の宛先違い、未達成の完了、第三者による取消の既存4宣言で、拒否前後の公開状態と未発行イベント列が同じであることを確認する
- `status` / `acceptor_player_id` / `objectives` は公開プロパティから取得する。目標は不変の値で、公開目標リストはコピーなので、比較元が同時に書き換わることはない
- 発行・合法な受託のイベントを消さず、比較前に非空であることを確認する。成功イベントの混入だけでなく、既存イベントの誤消去も検出する
- 未達成の完了拒否は、従来の KILL_MONSTER / 対象101 / 必要数2 / 進捗0 の入力を残す。同じ宣言に、達成済みの別目標を前へ加えた入力を追加する
- 非ギルド発行の重複1宣言を削除する。OPEN の確認は `test_issue_quest_success`、発行イベントの確認は `test_issue_quest_emits_event` に同じ入力で残る

分類は R28 / F4 / C0 / D1。変更前33宣言33ケースから変更後32宣言33ケースとなる。試験ファイルは488行から529行へ、60行追加・19行削除。製品コード・共有の試験支援は増減なし。監査文書の行数は試験の増減に含めない。

## 所有者を分ける理由

`QuestCommandService` は受託や取消の前に可否を確認する。その拒否試験だけでは、集約の操作が途中で状態を書き換えた場合の原状保持を保証できない。一方、今回の集約試験は、リポジトリの巻き戻しや報酬の決済を保証するものではない。

`QuestProgressReactionService._process_accepted_quests` は進捗の更新後に全目標の達成を判定し、完了・報酬付与・保存へ進む。「どれかの達成」で完了してしまう誤りは、その判定を所有する集約の試験で捉える。

公開可否照会はコマンドサービスから直接使われるため保持した。ギルドの承認待ち、発行時の予約報酬、正常な状態遷移とイベント発行も別の契約として保持した。空目標での作成失敗や全ての拒否例へ、機械的に状態比較を加える変更ではない。

## 重複削除の根拠と履歴

削除した `TestIssueQuest.test_issue_quest_without_guild_id_sets_open` は、issuer_player_id=None / guild_id=None と既存の同じフィクスチャで発行し、OPEN と先頭イベントの型だけを確認していた。

残す `test_issue_quest_success` は同じ入力の OPEN を含む作成状態を、`test_issue_quest_emits_event` は同じ入力のイベント型・件数1・集約IDを確認する。確認の移動や製品口の削除は不要である。

- [クエスト基盤の追加](https://github.com/Motifman/llm-rpg/commit/569186222a2e725ab6eb28daa2bceb50863728cf) に、今回補強した拒否例と全目標判定が含まれる
- [ギルド承認の追加](https://github.com/Motifman/llm-rpg/commit/3d3eaf3fb2bcaaf68461603bde7f9f918f9f1430) で、非ギルド側の対照として削除対象が追加された。対照の契約は上の2例が既に保持している

2026-10-13 14:05 UTC時点で開いている23件のPRの変更ファイルを確認し、今回の集約と試験の編集競合はなかった。

## 基準と変更後の検証

Python 3.10.22 / pytest 8.4.1、固定済み依存を使い、対象の作業ツリーのソースを読み込んだことを確認して実行した。外部ネットワークを遮断し、実LLMや有償APIは呼んでいない。ローカルの安全な測定実行器から pytest を直列実行した。CIの通常試験では `uv run --frozen pytest -n auto` の対象となる。

|実行|結果|起動を含む実時間|
|---|---|---|
|変更前・第1回|33成功|0.497秒|
|変更前・第2回|33成功|0.448秒|
|変更後・第1回|33成功|0.447秒|
|変更後・第2回|33成功|0.390秒|
|関連・変更前|96成功|1.832秒|
|関連・変更後|96成功|1.473秒|

主対象はもともと起動を含めて約0.4〜0.5秒である。実行時間の短縮や速度の改善率は主張しない。重複した説明を減らし、見逃していた退行を検出する変更である。

関連96件は次の7ファイル（値オブジェクトは4ファイル）で、全宣言監査の33件とは別の検証範囲である。

- `tests/domain/quest/value_object/`
- `tests/application/quest/services/test_quest_command_service.py`
- `tests/application/quest/handlers/test_quest_progress_handler.py`
- `tests/infrastructure/repository/test_sqlite_quest_repository.py`

通常環境での再実行:

```bash
uv run --frozen pytest tests/domain/quest/test_quest_aggregate.py
uv run --frozen pytest tests/domain/quest/value_object \
  tests/application/quest/services/test_quest_command_service.py \
  tests/application/quest/handlers/test_quest_progress_handler.py \
  tests/infrastructure/repository/test_sqlite_quest_repository.py
uv run --frozen ruff check tests/domain/quest/test_quest_aggregate.py
git diff --check
```

ruff と差分の空白検査は成功した。公開後のCIは、このローカル検証とは別に確認する。

## 公開前の新しい main への追従

上の基準・変更後比較と24改変実行は、旧基準 `0b51eb28d4692635a932dcf4063ab9b231768bf0` で行った。その後、公開前の基準を `f8224b8cc805107785524d7255a68b88e1e4b65f` へ進めた。

新しい main でも所有者のバイト列、変更前の対象試験、候補試験はそれぞれ旧検証時と一致した。主対象33件と関連96件を再実行して成功し、ruff と差分の空白検査も成功した。製品コードや依存はこの変更で修正していない。旧基準の計測結果を、新しい main の計測結果と混ぜていない。

## 12種類の改変による保全確認

所有者に一時的な改変を加え、同じ改変に対する従来試験と変更後試験を比べた。各改変は実行前に構文を確認した。結果は計24実行で、以下の意図した例外または断言で失敗した。収集失敗や準備中の例外を検出の証拠にしていない。

|改変|従来|変更後|確認した失敗|
|---|---|---|---|
|全目標判定を all から any に変更|33件成功|混在入力だけ失敗|未達成例外が出ない|
|受託者代入を受託の状態確認前へ移動|33件成功|再受託と宛先違いが失敗|受託者が変化|
|COMPLETED代入を達成確認前へ移動|33件成功|未達成の両入力が失敗|状態が変化|
|CANCELLED代入を当事者確認前へ移動|33件成功|第三者取消が失敗|状態が変化|
|受託イベントを拒否確認前へ移動|33件成功|受託の2拒否例が失敗|成功イベントが余分にある|
|完了イベントを達成確認前へ移動|33件成功|未達成の両入力が失敗|成功イベントが余分にある|
|取消イベントを当事者確認前へ移動|33件成功|第三者取消が失敗|成功イベントが余分にある|
|受託拒否時に既存イベントを消去|33件成功|受託の2拒否例が失敗|既存の非空イベントが失われる|
|未達成完了の拒否時に既存イベントを消去|33件成功|未達成の両入力が失敗|既存の非空イベントが失われる|
|第三者取消の拒否時に既存イベントを消去|33件成功|第三者取消が失敗|既存の非空イベントが失われる|
|非ギルド発行をOPEN以外に変更|主担当2件のうち作成状態が失敗|同じ主担当が失敗|OPENの確認|
|非ギルド発行を承認待ちイベントに変更|主担当2件のうちイベント例が失敗|同じ主担当が失敗|QuestIssuedEventの型確認|

前半10種類は正常系を含む主対象ファイル全件、後半2種類は削除後も残す主担当2件を実行した。後半の改変は既存の検出契約を保っていることを示し、新しい検出力として数えない。

全ての一時改変後、製品所有者を元のバイト列へ復元した。復元前後のSHA-256は `86a2f57389f94f40d3377eda398cc44c104054d0ae39d4e46dc07e0a6da73448`。候補試験も元の候補バイト列と一致し、最後に主対象2回と関連96件を再実行して成功した。

## 保留する観点

- 承認の拒否や進捗更新のFalse経路、全終端状態の組合せは今回補強していない
- 全てのイベント項目の正しさや、複数目標の進捗分配を網羅した変更ではない
- 公開プロパティと構築口は保存・復元・コマンド・報酬付与が利用する。単純な取得だからという理由で削除していない
- 新旧の取引集約や、別領域の試験はこの変更に含めない

## 全33宣言の台帳

行番号は固定基準時点。Rは保持、Fは既存例の補強、Dは既存の強い確認に完全包含される重複の削除を示す。

### QuestAggregate

tests/domain/quest/test_quest_aggregate.py

分類: R28 / F4 / C0 / D1

|行|判定|宣言|根拠|
|---|---|---|---|
|93|R|`TestQuestAggregate.TestIssueQuest.test_issue_quest_success`|非ギルド発行のID・OPEN・発行者なし・受託者なし・目標数・報酬・範囲。D候補のOPENを受け持つ|
|110|R|`TestQuestAggregate.TestIssueQuest.test_issue_quest_emits_event`|非ギルド発行イベントの型・件数1・ID。D候補のイベント型を受け持つ|
|124|R|`TestQuestAggregate.TestIssueQuest.test_issue_quest_empty_objectives_raises`|空目標で発行できない。作成拒否であり既存集約の原状保持とは異なる|
|137|R|`TestQuestAggregate.TestIssueQuest.test_issue_quest_with_reserved_rewards_player_issued`|発行者と予約金額・予約アイテムが失われない。取消返却と報酬付与が利用する|
|157|R|`TestQuestAggregate.TestIssueQuest.test_issue_quest_system_issued_has_no_reserved`|システム発行の予約金額0・予約アイテムなしという既定値|
|170|R|`TestQuestAggregate.TestIssueQuest.test_issue_quest_with_guild_id_sets_pending_approval`|ギルド掲示が承認待ちとなり、ギルドID付きの承認待ちイベント1件を発行する|
|190|D|`TestQuestAggregate.TestIssueQuest.test_issue_quest_without_guild_id_sets_open`|93行の作成状態例と110行の発行イベント例が同一入力・全確認を包含する|
|206|R|`TestQuestAggregate.TestApproveBy.test_approve_by_success`|承認待ちからOPENへの遷移と承認者付きイベント|
|225|R|`TestQuestAggregate.TestApproveBy.test_approve_by_when_not_pending_raises`|承認待ちでないOPENの再承認を拒否する|
|231|R|`TestQuestAggregate.TestAcceptBy.test_accept_by_success`|公開クエストを受託すると受託者・ACCEPTED・受託イベントが設定される|
|238|F|`TestQuestAggregate.TestAcceptBy.test_accept_when_not_open_raises`|既受託を別人が受託できない。原状保持を非空イベントと公開状態の拒否前後比較で補強する|
|242|F|`TestQuestAggregate.TestAcceptBy.test_accept_direct_scope_wrong_player_raises`|直接依頼の宛先以外は受託できない。原状保持を非空イベントと公開状態の拒否前後比較で補強する|
|257|R|`TestQuestAggregate.TestAcceptBy.test_accept_direct_scope_correct_player_succeeds`|直接依頼の宛先は受託でき、受託者になる|
|274|R|`TestQuestAggregate.TestAdvanceObjective.test_advance_objective_success`|対象種別・対象IDが合う受託中目標の進捗が1増える|
|280|R|`TestQuestAggregate.TestAdvanceObjective.test_advance_objective_wrong_type_returns_false`|対象IDが同じでも目標種別違いは進捗成功と返さない|
|286|R|`TestQuestAggregate.TestAdvanceObjective.test_advance_objective_wrong_target_returns_false`|目標種別が同じでも対象ID違いは進捗成功と返さない|
|292|R|`TestQuestAggregate.TestAdvanceObjective.test_advance_objective_when_not_accepted_returns_false`|未受託の目標更新を進捗成功と返さない|
|300|R|`TestQuestAggregate.TestAdvanceObjective.test_advance_objective_caps_at_required`|必要数に達した集約の目標を追加イベントで増やさず完了判定を保つ|
|308|R|`TestQuestAggregate.TestAdvanceObjective.test_advance_objective_take_from_chest_with_secondary_success`|宝箱の主IDと副IDの一致で進捗・達成へ至る|
|333|R|`TestQuestAggregate.TestAdvanceObjective.test_advance_objective_take_from_chest_wrong_secondary_returns_false`|主ID一致でも副ID不一致ならFalseで進捗0を維持する|
|358|R|`TestQuestAggregate.TestComplete.test_complete_success`|達成済みで受託中のクエストだけがCOMPLETEDになり完了イベントを積む|
|378|R|`TestQuestAggregate.TestComplete.test_complete_when_not_accepted_raises`|OPENの完了を状態例外で拒否する。未達成例外との区別がある|
|382|F|`TestQuestAggregate.TestComplete.test_complete_when_objectives_not_done_raises`|未達成1個に加え、達成済みと未達成が混在する入力を追加。全て／どれかを区別し、拒否後の状態とイベントを守る|
|389|R|`TestQuestAggregate.TestCancelBy.test_cancel_by_acceptor_success`|受託者が取消でき、CANCELLEDと取消イベントになる|
|395|R|`TestQuestAggregate.TestCancelBy.test_cancel_by_issuer_success`|未受託の発行者が取消できる。受託者経路とは別|
|409|F|`TestQuestAggregate.TestCancelBy.test_cancel_by_other_player_raises`|第三者の取消を拒否する。原状保持を非空イベントと公開状態の拒否前後比較で補強する|
|415|R|`TestQuestAggregate.TestCancelBy.test_cancel_when_completed_raises`|合法に完了させたクエストを取消できない|
|437|R|`TestQuestAggregate.TestCanBeAcceptedBy.test_open_public_can_be_accepted_by_any`|公開クエストの問い合わせが異なる両プレイヤーに受託可を返す。アプリが直接使う|
|443|R|`TestQuestAggregate.TestCanBeAcceptedBy.test_accepted_quest_cannot_be_accepted`|既受託の問い合わせが受託不可を返す。アプリが直接使う|
|448|R|`TestQuestAggregate.TestCanBeAcceptedBy.test_open_guild_scope_can_be_accepted_by_any_player_aggregate_only`|承認前は不可、承認後の集約は会員制限をしない。会員制限はアプリ所有|
|469|R|`TestQuestAggregate.TestIsIssuerOrAcceptor.test_issuer_is_included`|取消の当事者照会に発行者を含める。アプリが直接使う|
|482|R|`TestQuestAggregate.TestIsIssuerOrAcceptor.test_acceptor_is_included`|取消の当事者照会に受託者を含める。アプリが直接使う|
|485|R|`TestQuestAggregate.TestIsIssuerOrAcceptor.test_other_player_not_included`|取消の当事者照会に第三者を含めない。アプリが直接使う|
