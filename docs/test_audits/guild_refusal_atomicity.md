# ギルドの拒否操作で会員情報と未発行イベントが変わらないことを確認する

## 結果

招待・役職変更を拒否する既存4例に、公開される会員情報と未発行イベント列の保存確認を追加した。例外を投げながら会員を追加・昇格してしまう変更、成功イベントだけを残す変更、既存イベントを消す変更を検出する。

- 対象: GuildAggregateとGuildIdの2ファイル、31宣言。前後とも31件を収集・実行
- 全宣言の分類: R27 / F4 / C0 / D0。削除・統合はなし
- 基準: 31件合格を2回。変更後: 31件合格を2回
- 関連する別責務の試験: 基準・変更後とも42件合格
- 7種類の意図的改変は、変更前の31件がすべて合格し、変更後に対象4例の該当する状態・イベント比較だけが失敗
- 製品コードは変更なし。テストは1ファイル +32/-2行。対象2ファイルの合計は308→338行
- ruff、差分の空白検査と独立保存レビューは合格。リモートCIは公開後に確認する

試験数削減や高速化を目的とした変更ではない。例外確認は有用な拒否契約として残し、失敗後の部分変更を検出できるようにした。

## 範囲

基準の上流コミット: `0b51eb28d4692635a932dcf4063ab9b231768bf0`

- `tests/domain/guild/test_guild_aggregate.py`: 18宣言、224→254行。4例のみ編集
- `tests/domain/guild/value_object/test_guild_id.py`: 13宣言、84行。変更なし
- 製品の主所有者: `guild_aggregate.py` 261行、`guild_id.py` 43行。最終差分0
- GuildBankは別の所有者。11件を関連試験として実行したが、今回の全宣言監査31件には含めていない

重複加入拒否、非会員の脱退拒否、役職変更の対象がいない場合の3例は既存のまま保持した。解散の拒否、複数の後継候補の順位も今回の修理対象ではない。**ギルドの全拒否操作の状態保存を網羅したという報告ではない。**

## 変更した4例

- 非会員による招待: 例外後も招待先を追加せず、既存会員とイベント列を保つ
- 通常会員による招待: 同様に加入を反映せず、既存状態とイベント列を保つ
- 通常会員による役職変更: 変更対象を昇格させず、既存の会員情報とイベント列を保つ
- リーダーの自己降格: リーダーを失わず、会員情報とイベント列を保つ

拒否の直前に `members` と `get_events()` を取得し、拒否後に同じ公開APIから読んだ値と比較する。比較前には既に作成・合法な加入で生じたイベントがあり、非空であることも確認する。最初にイベントを消す準備をしていないため、既存イベントの誤消去も検出できる。

`members` は辞書のコピー、会員値とドメインイベントは不変の値、`get_events()` は列のコピーである。私有属性の構造・オブジェクト同一性・内部呼出順を固定しない。試験用の製品引数や公開口も追加しない。

## 公開呼び出し元と主要な証拠

- [GuildCommandServiceの招待](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/src/ai_rpg_world/application/guild/services/guild_command_service.py#L176-L185) と [役職変更](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/src/ai_rpg_world/application/guild/services/guild_command_service.py#L239-L253) は実集約へ委譲し、成功後に保存する
- [アプリ側の招待拒否試験](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/application/guild/services/test_guild_command_service.py#L236-L256) と [役職変更拒否試験](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/application/guild/services/test_guild_command_service.py#L354-L382) は例外変換の契約として残す。手元の集約の状態・イベント保存を代替する証拠ではない
- ドメインの合法な招待・昇格の成功例は正の対照として維持。作成・脱退・後継任命も独立した契約として維持した
- [QuestCommandService](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/src/ai_rpg_world/application/quest/services/quest_command_service.py#L337-L346) が公開の `can_approve_quest` を直接利用する。承認権限の4例は私有述語をなぞる試験ではない
- [InMemoryGuildRepository](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/src/ai_rpg_world/infrastructure/repository/in_memory_guild_repository.py#L36-L55) はGuildIdを辞書キーに使い、読み出した集約を複製する。永続化の巻き戻しと、直接操作後の集約状態の保存は別責務
- [SqliteGuildRepository](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/src/ai_rpg_world/infrastructure/repository/sqlite_guild_repository.py#L40-L124) は `int(GuildId)` を保存・検索・採番で利用。IDの変換・等価性・hashは独立した公開契約として残した
- `GuildId.create` の製品内の静的な直接呼び出しは見つからなかったが、初期から存在する公開生成口。呼び出しなしだけを根拠にAPI削除やその唯一の証拠の削除をしない
- [ギルド基盤の導入](https://github.com/Motifman/llm-rpg/commit/3d3eaf3fb2bcaaf68461603bde7f9f918f9f1430) と [リーダー脱退の契約変更](https://github.com/Motifman/llm-rpg/commit/2fd86259ae58ff45dcde623c92d5754afd7cb2c2) を確認。初期の拒否条件を捨てず、既に変更された「他会員がいるリーダーは脱退不可」という古い仕様を復活させない

廃止する層・ファイルや製品補助口はない。既存の主担当ファイルで検証を補強する。

## 実測結果

Python 3.10.22、pytest 8.4.1。指定のローカル作業ツリーの製品コードを読むことを確認し、通信を遮断して実行した。外部LLMは利用していない。

| 実行 | 結果 | 実時間 | 子プロセスCPU |
|---|---:|---:|---:|
| 主対象・基準1 | 31件合格 | 0.5698秒 | 0.5684秒 |
| 主対象・基準2 | 31件合格 | 0.3789秒 | 0.3782秒 |
| 主対象・最終1 | 31件合格 | 0.5381秒 | 0.5332秒 |
| 主対象・最終2 | 31件合格 | 0.4290秒 | 0.4284秒 |
| 関連・基準 | 42件合格 | 1.4621秒 | 1.4613秒 |
| 関連・最終 | 42件合格 | 1.3151秒 | 1.3143秒 |

主対象は集約18件＋ID13件。関連42件はGuildBank 11件、GuildCommandService 28件、SQLiteギルド保存3件で、主対象の31件とは別に数えた。基準失敗はない。

主対象は短い試験で、起動・キャッシュの揺れが相対的に大きい。この時間差から高速化・低速化を判断しない。全リポジトリの試験やGitHub CIはまだ実行していない。

再現する試験範囲:

- 主対象: `uv run --frozen pytest tests/domain/guild/test_guild_aggregate.py tests/domain/guild/value_object/test_guild_id.py`
- 関連: `uv run --frozen pytest tests/domain/guild/aggregate/test_guild_bank_aggregate.py tests/application/guild/services/test_guild_command_service.py tests/infrastructure/repository/test_sqlite_guild_repository.py`
- 静的検査: `ruff check tests/domain/guild/test_guild_aggregate.py tests/domain/guild/value_object/test_guild_id.py`
- 通常CIはPython 3.10で `uv run --frozen pytest -n auto`。今回のファイルは通常の発見規則に含まれ、試験登録の変更は不要

## 7種類の意図的改変と実際の失敗位置

すべて製品所有者を一時的に変更し、変更前と変更後のテストを同じ31件の範囲で実行した。変更前は各回31件合格。変更後は下記の比較で失敗し、例外型が変わったための失敗や前提準備の失敗ではなかった。

| 改変 | 旧試験 | 新試験 | 失敗位置（変更後の集約テスト） |
|---|---:|---:|---|
| m1-invite-state: 招待の会員登録を招待者の在籍・権限検査より前へ移す | 31件合格 | 29件合格、2件失敗 | 121行 members比較 / 138行 members比較 |
| m2-role-permission-state: 役職変更の権限検査を会員置換より後へ移す | 31件合格 | 30件合格、1件失敗 | 205行 members比較 |
| m3-self-demotion-state: 自己降格検査を会員置換より後へ移す | 31件合格 | 30件合格、1件失敗 | 233行 members比較 |
| m4-invite-event: 会員は変更せず、加入イベントを招待者検査より前へ追加する | 31件合格 | 29件合格、2件失敗 | 122行 イベント列比較 / 139行 イベント列比較 |
| m5-role-event: 会員は変更せず、役職変更イベントを権限・自己降格検査より前へ追加する | 31件合格 | 29件合格、2件失敗 | 206行 イベント列比較 / 234行 イベント列比較 |
| m6-invite-clear: 招待の入口で既存の未発行イベントを誤って消す | 31件合格 | 29件合格、2件失敗 | 122行 イベント列比較 / 139行 イベント列比較 |
| m7-role-clear: 役職変更の入口で既存の未発行イベントを誤って消す | 31件合格 | 29件合格、2件失敗 | 206行 イベント列比較 / 234行 イベント列比較 |

改変下の正常例も含めて全31件を実行し、旧試験では正常な招待・役職変更・リーダー継承などの既存例が合格することを確認した。これは**既存の具体的な正常入力の結果を保った**という確認であり、全入力に対する意味の同一性を証明したものではない。

各改変の直後に製品をバイト単位で復元し、7回すべてで下記と一致した。

- 製品ファイルのGit blob: `d800ec24122f94842db223bc82929b1df59a56ce`（基準コミットと一致）
- SHA-256: `a8b8029d353e76a06b0cab37d82a648bea5d413e1632e1fca4a95d13518169bb`
- 最終の製品差分: 0

各改変の差分、旧・新それぞれの生ログ、JUnitと測定JSON、実際の失敗位置と復元ハッシュを記録した。既存製品の不具合修正ではなく、従来の試験が見逃した部分変更を検出するための証拠である。

## 全31宣言の台帳

R=維持、F=契約を残して検証を補強、C=別の主担当へ統合、D=削除。リンクと行番号は基準コミットに固定した。31宣言はすべて残し、2回の基準・2回の最終実行で合格した。

### tests/domain/guild/test_guild_aggregate.py

| 宣言 | 分類 | 保護する契約・検出する退行 |
|---|---|---|
| [TestGuildAggregate::TestCreateGuild::test_create_guild_success](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/test_guild_aggregate.py#L64-L81) | R | 作成者がリーダーになり、名称・説明を前後空白なしで保持し、作成イベントを出す。役職初期値・正規化・作成通知の欠落を検出。 |
| [TestGuildAggregate::TestCreateGuild::test_create_guild_empty_name_raises](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/test_guild_aggregate.py#L83-L92) | R | 空白だけの名称を拒否する。空名でギルドが作られる誤りを検出。既存集約の更新操作ではないため、不変状態の補強対象にはしない。 |
| [TestGuildAggregate::TestAddMember::test_add_member_success](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/test_guild_aggregate.py#L95-L100) | R | 合法な招待で会員が追加され、MEMBER役職と加入イベントが見える。追加忘れ・役職誤り・通知欠落を検出。拒否補強の正の対照。 |
| [TestGuildAggregate::TestAddMember::test_add_member_already_member_raises](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/test_guild_aggregate.py#L102-L107) | R | 既存会員への重複招待を専用例外で拒否する。重複加入を許す誤りを検出。今回の前倒し改変は重複確認の後なので、この契約を補強済みとは主張しない。 |
| [TestGuildAggregate::TestAddMember::test_add_member_inviter_not_member_raises](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/test_guild_aggregate.py#L109-L114) | F | 非会員による招待拒否の契約は残す。会員登録を在籍確認前に移すと同じ例外のまま新会員が残るため、membersと未発行イベント列の保存を追加済み。 |
| [TestGuildAggregate::TestAddMember::test_add_member_member_cannot_invite_raises](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/test_guild_aggregate.py#L116-L124) | F | 通常会員による招待拒否の契約は残す。会員登録を権限確認前に移すと同じ例外のまま加入が反映されるため、membersと未発行イベント列の保存を追加済み。 |
| [TestGuildAggregate::TestLeave::test_leave_success](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/test_guild_aggregate.py#L127-L131) | R | 通常会員が脱退でき、会員から消えて脱退イベントが出る。削除または通知の欠落を検出。 |
| [TestGuildAggregate::TestLeave::test_leave_leader_when_only_member_success](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/test_guild_aggregate.py#L133-L136) | R | 唯一のリーダーも脱退できる。後継候補必須と誤って制限する変更を検出。 |
| [TestGuildAggregate::TestLeave::test_leave_leader_when_other_members_appoints_successor](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/test_guild_aggregate.py#L138-L151) | R | 他の会員がいる場合は脱退者を除き、残る会員をリーダーにして役職変更・脱退イベントを出す。リーダー不在化を検出。候補1人なので最古順の証拠とはしない。 |
| [TestGuildAggregate::TestLeave::test_leave_not_member_raises](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/test_guild_aggregate.py#L153-L155) | R | 非会員の脱退を専用例外で拒否する。黙って成功・KeyError漏出などを検出。招待・役職変更とは別操作のため今回の編集対象外。 |
| [TestGuildAggregate::TestChangeRole::test_change_role_to_officer_success](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/test_guild_aggregate.py#L158-L168) | R | リーダーの合法な昇格操作で役職と役職変更イベントが見える。無処理や通知欠落を検出。拒否補強の正の対照。 |
| [TestGuildAggregate::TestChangeRole::test_change_role_changer_not_officer_raises](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/test_guild_aggregate.py#L170-L184) | F | 通常会員による役職変更拒否は残す。変更者の古い値を保持して対象の置換だけ先に行うと、同じ例外で対象が昇格する。membersとイベントの保存を追加済み。 |
| [TestGuildAggregate::TestChangeRole::test_change_role_target_not_member_raises](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/test_guild_aggregate.py#L186-L194) | R | 権限のある変更者でも存在しない対象は専用例外で拒否する。勝手な会員作成やKeyError漏出を検出。 |
| [TestGuildAggregate::TestChangeRole::test_change_role_leader_cannot_demote_self](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/test_guild_aggregate.py#L196-L204) | F | リーダーの自己降格拒否は残す。取得済みtargetを使う検査前に辞書だけ置換すると、同じ例外のままリーダーが失われる。membersとイベントの保存を追加済み。 |
| [TestGuildAggregate::TestCanApproveQuest::test_leader_can_approve_quest](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/test_guild_aggregate.py#L207-L208) | R | リーダーのクエスト承認権限という公開照会契約。リーダーを不許可とする変更を検出。QuestCommandServiceが直接使用する。 |
| [TestGuildAggregate::TestCanApproveQuest::test_officer_can_approve_quest](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/test_guild_aggregate.py#L210-L218) | R | オフィサーの承認権限。リーダーだけに誤って制限する変更を検出。実際の役職変更で準備する。 |
| [TestGuildAggregate::TestCanApproveQuest::test_member_cannot_approve_quest](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/test_guild_aggregate.py#L220-L221) | R | 通常会員はクエスト承認不可。全会員に権限を与える誤りを検出。 |
| [TestGuildAggregate::TestCanApproveQuest::test_non_member_cannot_approve_quest](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/test_guild_aggregate.py#L223-L224) | R | 非会員はクエスト承認不可。在籍確認漏れやNone参照を検出。 |

### tests/domain/guild/value_object/test_guild_id.py

| 宣言 | 分類 | 保護する契約・検出する退行 |
|---|---|---|
| [TestGuildId::test_create_positive_int_id](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/value_object/test_guild_id.py#L10-L13) | R | 正の最小側のIDを作成し値を保持する。1を拒否する下限ずれを検出。 |
| [TestGuildId::test_create_large_positive_int_id](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/value_object/test_guild_id.py#L15-L18) | R | 999999のIDを保持する。根拠のない上限・桁切りを検出。単なる代入形でも入力範囲の公開契約として保持。 |
| [TestGuildId::test_create_from_int_create_method](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/value_object/test_guild_id.py#L20-L24) | R | 公開createが整数をGuildIdとして返す。整数経路だけ未対応になる変更を検出。製品内の静的な直接呼び出しは未発見だが、初期からの公開生成口で削除根拠は不足。 |
| [TestGuildId::test_create_from_str_create_method](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/value_object/test_guild_id.py#L26-L30) | R | 公開createが整数文字列を数値IDとして返す。文字列保持・変換欠落を検出。create削除の互換性判断は今回行わない。 |
| [TestGuildId::test_create_zero_id_raises_error](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/value_object/test_guild_id.py#L32-L35) | R | コンストラクタで0をドメイン例外として拒否。比較を<へ緩める誤りを検出。 |
| [TestGuildId::test_create_negative_id_raises_error](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/value_object/test_guild_id.py#L37-L42) | R | -1と-100をドメイン例外として拒否。負値許可を検出。2つの入力は1宣言として記録。 |
| [TestGuildId::test_create_from_negative_str_raises_error](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/value_object/test_guild_id.py#L44-L47) | R | 文字列-5も公開createを通じて正値制約を受ける。変換後の検証回避を検出。 |
| [TestGuildId::test_create_from_zero_str_raises_error](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/value_object/test_guild_id.py#L49-L52) | R | 文字列0も公開createを通じて正値制約を受ける。0の特別扱いや変換経路だけの制約漏れを検出。 |
| [TestGuildId::test_create_from_invalid_str_raises_error](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/value_object/test_guild_id.py#L54-L61) | R | abc、12.5、空文字をドメイン例外で拒否。float経由の切り捨てや組込みValueErrorの漏出を検出。3つの入力は1宣言として記録。 |
| [TestGuildId::test_str_conversion](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/value_object/test_guild_id.py#L63-L66) | R | str(GuildId)が数値の十進表現になる。例外文面にも使われる表示契約。dataclass表現へ戻る変更を検出。 |
| [TestGuildId::test_int_conversion](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/value_object/test_guild_id.py#L68-L71) | R | int(GuildId)が値を返す。SQLiteの保存・検索で実際に使う変換契約。削除や別値返却を検出。 |
| [TestGuildId::test_equality](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/value_object/test_guild_id.py#L73-L79) | R | 同じIDは等しく異なるID・文字列・裸の整数とは等しくない。リポジトリのキー同一視と型分離を守る。 |
| [TestGuildId::test_hash](https://github.com/Motifman/llm-rpg/blob/0b51eb28d4692635a932dcf4063ab9b231768bf0/tests/domain/guild/value_object/test_guild_id.py#L81-L84) | R | 等しいGuildIdが同じhashを返す。InMemoryの辞書キー利用を守る。具体的なhash値や実装式は固定していない。 |

## 残した範囲・判断しなかったこと

- 重複加入拒否、非会員の脱退拒否、変更対象がいない場合は例外契約をそのまま維持し、失敗後の状態・イベント保存は今回追加していない
- 解散の拒否や、複数のオフィサー・通常会員から後継者を選ぶ順位は今回の補強対象に含めていない。ドメインの後継者例は候補が1人で、アプリの関連例もオフィサーは1人のため、複数候補の最古順選定を証明していない
- GuildBankは関連試験として合格を確認したが、全宣言監査を行った31件へ算入しない
- IDの真偽値・小数など、既存の契約と試験が扱わない入力型の仕様は今回変更していない
- 例外の文言・内部の検査順序を固定していない。同じ外部契約を保つガードの統合や順序変更を、検出すべき退行とは扱わない
- 製品不具合の修正、試験専用の本体コードの削除、API廃止、全リポジトリの保証は行っていない

## 独立保存レビュー

元の31宣言の保持と変更が4例だけであること、既存会員・非空イベント前提、比較用の値が内部コンテナの別名ではないことを独立確認した。7改変の旧新JUnitでは意図したmembers/event比較だけが失敗し、製品SHAの完全復元、最終31件×2と関連42件の成功も照合した。保持欠落の指摘はない。重い試験の再実行は行わず、実行証拠とコードを照合した。
