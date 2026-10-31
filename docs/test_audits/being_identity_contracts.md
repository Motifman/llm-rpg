# 主体の接続拒否と人格の保持を確かめる

> D1928-2 で `unique_attached_being` と `find_all_attached_to` は消え、誰がどのプレイヤーを動かすかはゲームの側の対応表 (`PlayerBeings`) が持つ。


> D1469-1 で `BeingIdentity` は `Persona` に、`Being` は `being/domain/being.py` に移り、`MemoryKind` と記憶の種類の宣言は消えた。以下は当時の記録。

## なぜ

主体の識別と接続を扱う6ファイル48宣言をすべて読み、例外を投げた後の誤更新、接続を解除したときの主体情報の喪失、一人称だけに残る検証漏れを見つけた。対象の基準試験は成功していたが、これらを壊す変更を既存の対象48件が見逃していた。

今回の目的は検出力を補うこと。解除の戻り値だけを調べる重複準備1件を整理した。MemoryKindの4種類固定は撤去計画と意味的に重なるため、削除案を採用せず保留した。ID・既定値・構築・型・等価性・hashの契約は単純という理由では消していない。

基準は main `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f`。原48宣言のうち47宣言はR35/F11/C1/D0、1宣言は保留。人格への外部代入禁止を1宣言追加し、最終48宣言、入力表展開後59件。試験は474行から541行（追加131行・削除64行、差引67行増）。準備関数19行は試験行数の内数で変わらない。独立した試験補助ファイルと製品コードの差分は0。

## 何を変えたか

1. 接続済みの再接続拒否と型違反の拒否で、元の接続と接続フラグが変わらないことを確認する。型違反は未接続・既接続の両方を試す。拒否表には元の(2,2)、同じ対(1,2)、別世界・別身体(2,99)を置く
2. 世界だけ変える元入力と、世界・プレイヤーをともに変える追加行を残し、解除中と再接続後に、明示した主体ID・人格・非空の種類宣言が残ることを確認する。期待値を操作後の主体から作らない
3. 入力リストの更新と、取得した宣言集合への局所的な和集合代入が、主体の宣言へ波及しないことを確認する。これは主体状態の隔離の検査であり、取得値に対するすべての操作の禁止まで証明するものではない
4. 取得済み列の一意性違反は2件／3件を試し、件数条件が2件だけへ狭まる変更を捕まえる
5. 接続の世界／プレイヤー、人格の名前／一人称を一方ずつ変え、片方の比較を落とす変更を捕まえる。名前だけだった空白・型・正規化の入力表を一人称にも広げる
6. 人格の名前と一人称への外部代入を拒否し、元の両値が残ることを確認する。特定のdataclass例外型には固定しない
7. 解除の戻り値検査は解除後の状態を検査する主試験へ先に移した。MemoryKindの既存4メンバーの検証を含むファイル全体は基準から変更していない

## 所有する契約と残す層

- [Being](../../src/ai_rpg_world/domain/being/aggregate/being.py) が構築・接続遷移・種類宣言の状態を所有する。実際の呼出しは [BeingProvisioningService](../../src/ai_rpg_world/application/being/being_provisioning_service.py) と [BeingSnapshotCodec](../../src/ai_rpg_world/domain/being/service/being_snapshot_codec.py)。準備サービスの再保存、codecの形式変換は別の責務として関連試験を残す
- [unique_attached_being](../../src/ai_rpg_world/domain/being/service/unique_attached_being.py) は取り出した列の件数規則を所有する。[BeingAttachmentResolver](../../src/ai_rpg_world/application/being/being_attachment_resolver.py) の実取得・世界差・プレイヤー差・未接続除外と混ぜない
- 各値オブジェクトの検証・正規化・等価性はその値の試験が主所有者。BeingIdは実際にインメモリ保存の辞書キーに使う。保存・再構築試験だけでは、正規化されていない入力や誤った等価性のすべてを代替しない
- `declares` と `with_declared_memory_kinds` に試験以外の直接呼出しは見つからなかった。ただし導入時に意図した公開APIと明記されているため、試験だけの迂回口と断定して廃止しない
- 退役ファイルと削除する製品側の補助入口は無い。記憶機能・SNS・保存形式は変更していない

### 導入履歴

- [ae9086b](https://github.com/Motifman/llm-rpg/commit/ae9086b89b2ce51ea705184737f20bd094a60dcb): 世界・実験を跨ぐ文字列IDと人格の不変核、集約の公開APIを導入。値は空白除去後に検証する設計
- [a0c0876](https://github.com/Motifman/llm-rpg/commit/a0c08764b91a098aa5beb34fc1f7ea7f923a046c): 接続は高々1つ、既接続を拒否、解除前値を返し未接続の解除は無操作と規定
- [715ac7e](https://github.com/Motifman/llm-rpg/commit/715ac7ea0646451be0a75ebfd54f8e91fb9e66f0): 種類だけを宣言する不変集合と副作用なし差替えAPIを導入。4種類は当時の段階であり、将来の関係種類を明記。この導入履歴だけで今回の閉集合試験削除を進めず、最新の撤去方針と合わせて保留
- [c737ae3](https://github.com/Motifman/llm-rpg/commit/c737ae397bdacb5b726590f04d51abc2fffc54eb): 取得をアプリケーションへ、一意性判断を純粋なドメイン関数へ分ける。設計判断131と整合

## 原48宣言の判定

Rは保持、Fは契約を保持して検査を修理、Cは先に主試験へ移管。今回のDは0。完了候補のR35宣言は構文木が元のまま。保留1宣言も基準へ戻した。Fは既存の意味を保持し、本文や入力表を補った。

ファイル略号:

- B: [test_being.py](../../tests/domain/being/aggregate/test_being.py)
- U: [test_unique_attached_being.py](../../tests/domain/being/service/test_unique_attached_being.py)
- A: [test_being_attachment.py](../../tests/domain/being/value_object/test_being_attachment.py)
- I: [test_being_id.py](../../tests/domain/being/value_object/test_being_id.py)
- N: [test_being_identity.py](../../tests/domain/being/value_object/test_being_identity.py)
- M: [test_memory_kind.py](../../tests/domain/being/value_object/test_memory_kind.py)

| ID | 判定 | 原宣言 | 守る契約 | 具体的な退行 |
|---|---|---|---|---|
| BI-01 | R | B: `TestBeingConstruction.test_being_id_identity_can_create` | 明示した識別子と人格を持ち、接続省略時は未接続である | コンストラクタが識別子・人格を取り違える／接続を勝手に作る |
| BI-02 | R | B: `TestBeingConstruction.test_attachment_can_create` | 復元などの入口から接続済み主体を構築できる | 渡された接続を無視する／is_attachedが初期接続を認識しない |
| BI-03 | R | B: `TestBeingConstruction.test_being_id_being_id_raises_type_error` | 集約IDにはBeingIdを要求する既存の公開型契約 | 生の文字列を集約IDとして通す |
| BI-04 | R | B: `TestBeingConstruction.test_id_entity_being_id_entity_raises_type_error` | 集約人格にはBeingIdentityを要求する | 生の文字列を人格として通す |
| BI-05 | R | B: `TestBeingConstruction.test_attachment_being_attachment_raises_type_error` | 構築時の接続はBeingAttachmentまたはNoneである | 不正文字列の接続を構築時に受け入れる |
| BI-06 | R | B: `TestBeingConstruction.test_initial_state_has_no_events` | 新規Beingは公開イベントAPIを利用でき、未発行イベントは空である | super初期化を落としてget_eventsが壊れる／生成だけで架空イベントを積む |
| BI-07 | R | B: `TestBeingAttachDetach.test_attach_attachment_updated` | 未接続から指定の世界・プレイヤーへ接続する | attachが何も変更しない／誤った接続を保存する |
| BI-08 | F | B: `TestBeingAttachDetach.test_attach_raises_exception` | 既に接続済みなら再接続を拒否し元の接続を保持する | 接続先を上書きしてからBeingAlreadyAttachedExceptionを投げる |
| BI-09 | F | B: `TestBeingAttachDetach.test_attach_vo_raises_type_error` | 不正型の接続を拒否し、未接続・既接続いずれも元の状態を保持する | 不正型の拒否分岐でattachmentへ不正値を代入する、または既存の接続をNoneへ消してからTypeErrorを投げる |
| BI-10 | F | B: `TestBeingAttachDetach.test_returns_none_detach_attachment` | 接続解除が未接続状態と解除前の対を同時に返す | 接続を消さずに旧値だけ返す／消すが常にNoneを返す |
| BI-11 | C | B: `TestBeingAttachDetach.test_returns_detach_before_value` | 解除前の接続対を戻り値に残す | detachが常にNoneを返す |
| BI-12 | R | B: `TestBeingAttachDetach.test_attach_detach_none_raises_exception` | 最初から未接続の主体を解除してもNoneを返し例外にしない | 未接続解除を状態違反として扱う |
| BI-13 | F | B: `TestBeingAttachDetach.test_detach_attach` | 世界を乗り換えても主体ID・人格・記憶種類宣言は継続する | detach時に宣言集合や人格を初期化する |
| BI-14 | R | B: `TestBeingDeclaredMemoryKinds.test_omitted_attachments_default_to_empty_set` | 宣言省略時は空の記憶種類集合でMEMOを所有宣言しない | 既定でMEMOを足す／宣言なしを全部所有と扱う |
| BI-15 | F | B: `TestBeingDeclaredMemoryKinds.test_kind_declares_true` | 入力から独立した不変な種類集合と正確な所属判定を公開する | frozensetを可変setへ置き換え、取得した集合の更新がBeingを書き換える |
| BI-16 | R | B: `TestBeingDeclaredMemoryKinds.test_duplicate_kind_frozenset` | 同じ種類を重複入力しても宣言は集合として一度だけ保持する | リストや多重集合へ変えて重複を保持する |
| BI-17 | R | B: `TestBeingDeclaredMemoryKinds.test_memory_kind_raises_type_error` | 宣言の各要素はMemoryKindでなければ拒否する | 文字列memoをEnumと同じものとして通す |
| BI-18 | R | B: `TestBeingDeclaredMemoryKinds.test_declared_memory_kinds_being` | 宣言差替えは元の主体に副作用を与えずIDと人格を継承する | selfを直接書き換える／新主体のID・人格を取り違える |
| BI-19 | R | B: `TestBeingDeclaredMemoryKinds.test_declared_memory_kinds_attachment` | 宣言差替えで既存の接続も引き継ぐ | 新しいBeingを返す際にattachment引数を落とす |
| BI-20 | R | U: `TestUniqueAttachedBeing.test_empty_sequence_returns_none` | 取得列が空ならNoneを返す | 空列の先頭を読みIndexErrorになる |
| BI-21 | R | U: `TestUniqueAttachedBeing.test_single_being_returns_that_being` | 1件なら渡されたBeingそのものを選ぶ | Noneまたは別のBeingを作って返す |
| BI-22 | F | U: `TestUniqueAttachedBeing.test_multiple_beings_raises_exception` | 2件以上では任意の主体を選ばず一意性違反にする | len(matches)>1を==2へ狭め、3件以上なら先頭を黙って返す |
| BI-23 | R | A: `TestBeingAttachmentValidation.test_world_id_player_id_can_create` | 異なる型の世界IDとプレイヤーIDを対応する項目で公開する | 片方を取り違えたり捨てたりする |
| BI-24 | R | A: `TestBeingAttachmentValidation.test_world_id_world_id_raises_validation_exception` | 世界側はWorldIdを要求しドメイン検証例外を出す | 生のintを世界IDに受け入れる |
| BI-25 | R | A: `TestBeingAttachmentValidation.test_player_id_player_id_raises_validation_exception` | プレイヤー側はPlayerIdを要求しドメイン検証例外を出す | 生のintをプレイヤーIDに受け入れる |
| BI-26 | R | A: `TestBeingAttachmentEquality.test_same_world_player_equals` | 同じ世界とプレイヤーの対は同じ接続として比較できる | 等価性を参照同一性へ変える |
| BI-27 | F | A: `TestBeingAttachmentEquality.test_world_not_equal` | 世界とプレイヤーのどちらが違っても接続は別である | player_idを比較対象から落として別身体を同一視する |
| BI-28 | R | A: `TestBeingAttachmentEquality.test_hashable` | 同値の接続を集合・辞書の鍵として同一視できる | hashを無効化する／同値接続に参照別のhashを付ける |
| BI-29 | R | I: `TestBeingIdValidation.test_string_can_create` | 非空の任意文字列を主体の識別子として保持する | UUID形式だけに制限する／値を勝手に変える |
| BI-30 | R | I: `TestBeingIdValidation.test_empty_string_being_id_raises_validation_exception` | 空IDは保存・解決へ流さない | 空文字を有効な保存キーとして通す |
| BI-31 | R | I: `TestBeingIdValidation.test_blank_being_id_raises_validation_exception` | 空白だけのIDは正規化後の空として拒否する | 元文字列の長さだけ検査して空白IDを通す |
| BI-32 | R | I: `TestBeingIdValidation.test_around_blank` | 前後空白を除去したIDが公開・保存される | strip結果を書き戻さず別のキーにする |
| BI-33 | R | I: `TestBeingIdValidation.test_being_id_raises_validation_exception` | 数値などの文字列以外はドメイン例外で拒否する | intをstrへ暗黙変換する／stripでAttributeErrorにする |
| BI-34 | R | I: `TestBeingIdEquality.test_same_value_equals` | 独立に作った同値IDを同じ主体として扱う | IDを参照同一性で比較する |
| BI-35 | R | I: `TestBeingIdEquality.test_value_not_equal` | 別文字列のIDを別主体として扱う | すべてのBeingIdを等しいものにする |
| BI-36 | R | I: `TestBeingIdEquality.test_hashable` | 同値IDは同じ鍵、別値IDは別の集合要素になる | hash無しになる／同値のhashが一致しない／全IDが等値になる |
| BI-37 | R | I: `TestBeingIdEquality.test_returns_str_value` | 文字列化は保存上の主体IDそのものを返す | dataclass表現や装飾付き文字列を返す |
| BI-38 | R | N: `TestBeingIdentityValidation.test_name_first_person_can_create` | 名乗る名前と一人称の両方を別々に保持する | 一人称に名前を複写する／片方を固定値にする |
| BI-39 | R | N: `TestBeingIdentityValidation.test_name_empty_being_id_entity_raises_validation_exception` | 名前の空文字は拒否する | 名前が空でも受け入れる |
| BI-40 | R | N: `TestBeingIdentityValidation.test_first_person_empty_being_id_entity_raises_validation_exception` | 一人称の空文字は拒否する | 一人称の検証を丸ごと省く |
| BI-41 | F | N: `TestBeingIdentityValidation.test_name_blank_raises_exception` | 名前も一人称も空白だけなら拒否する | 一人称だけ元文字列の長さを見て空白を通す |
| BI-42 | F | N: `TestBeingIdentityValidation.test_name_around_blank` | 名前と一人称の双方を前後空白除去して保持する | 一人称だけstrip結果を書き戻さない |
| BI-43 | F | N: `TestBeingIdentityValidation.test_case_raises_exception` | 名前・一人称の型違反はBeingIdentityValidationExceptionになる | 一人称だけstrへ暗黙変換して数値を許す |
| BI-44 | R | N: `TestBeingIdentityEquality.test_same_equals` | 名前と一人称が同じ人格核は等価である | 人格比較を参照同一性へ変える |
| BI-45 | F | N: `TestBeingIdentityEquality.test_first_person_not_equal` | 名前または一人称が違えば人格核は異なる | nameを比較から除外して別名の主体を同一人格にする |
| BI-46 | 保留（現状保持） | M: `TestMemoryKindValues.test_four` | 現在の4種類固定の試験は現状保持し、撤去計画との意味的な整理を保留する | 既存試験が語彙追加で失敗することは確認したが、#1631/#1625の記憶再設計と保存方針の判断に合わせて採否を決める |
| BI-47 | R | M: `TestMemoryKindValues.test_value_snake_case_string` | 保存形式で使う4種類の文字列値を変更しない | episodicをepisodeへ変え既存snapshotとの互換を破る |
| BI-48 | R | M: `TestMemoryKindValues.test_str` | MemoryKindは文字列と比較できる | strの継承を落としてEnumだけにする |

### 移管と名前変更

BI-11の解除前戻り値は、BI-10の保持先 `TestBeingAttachDetach.test_detach_returns_previous_attachment_and_clears_state` へ移管した。BI-13の乗換え試験にも元からあった解除前戻り値検査を残す。BI-46は閉集合試験の削除判断を保留し、完了信用に含めない。BI-47の保存文字列とBI-48の文字列互換も含め、MemoryKindのファイル全体を元のまま保持する。

修理時に具体名へ変えた宣言:

- `test_returns_none_detach_attachment` → `test_detach_returns_previous_attachment_and_clears_state`
- `test_detach_attach` → `test_switching_attachments_preserves_identity_and_declarations`
- `test_kind_declares_true` → `test_declared_memory_kinds_are_isolated_from_caller_updates`
- `test_world_not_equal` → `test_different_world_or_player_is_not_equal`
- `test_name_blank_raises_exception` → `test_blank_identity_field_is_rejected`
- `test_name_around_blank` → `test_identity_field_whitespace_is_trimmed`
- `test_case_raises_exception` → `test_non_string_identity_field_is_rejected`
- `test_first_person_not_equal` → `test_different_identity_field_is_not_equal`

新規は `TestBeingIdentityImmutability.test_identity_fields_cannot_be_reassigned` の1宣言2行。外部代入禁止という不変核の契約を公開動作で調べる。BeingId／BeingAttachmentの追加代入禁止は今回の必須条件にしなかった。これらは単純なfrozen除去を既存hash試験が捕まえる。

## 変異で確認した検出力

対象の旧48件では成功する15種類の一時変異を、新しい主保持試験が意図したassertionまたは期待した拒否の不発で検出した。これは対象領域の比較であり、リポジトリ全体で初めて検出可能になったとの主張ではない。

| 変異 | 旧対象48件 | 新しい主保持試験 |
|---|---|---|
| `attach-refusal-overwrites`: 例外後に元の接続が保持されるassertion | 成功（見逃し） | 失敗（検出） |
| `invalid-attach-pollutes`: 未接続・既接続ともに不正値を代入しないassertion | 成功（見逃し） | 失敗（検出） |
| `invalid-attach-clears-existing`: 既接続の対を失わないassertion | 成功（見逃し） | 失敗（検出） |
| `detach-loses-declarations`: 解除直後の非空宣言の保持assertion | 成功（見逃し） | 失敗（検出） |
| `detach-loses-identity`: 解除直後の人格保持assertion | 成功（見逃し） | 失敗（検出） |
| `detach-loses-id`: 解除直後の主体ID保持assertion | 成功（見逃し） | 失敗（検出） |
| `mutable-declared-kinds`: 取得集合への|=が主体へ波及しないassertion | 成功（見逃し） | 失敗（検出） |
| `aliased-input-kinds`: 入力リストclear後も主体の宣言が保持されるassertion | 成功（見逃し） | 失敗（検出） |
| `unique-allows-three`: 3件の違反にDID NOT RAISE | 成功（見逃し） | 失敗（検出） |
| `attachment-ignores-player`: プレイヤーだけ違う行の不等価assertion | 成功（見逃し） | 失敗（検出） |
| `identity-accepts-blank-first-person`: 一人称空白行にDID NOT RAISE | 成功（見逃し） | 失敗（検出） |
| `identity-coerces-first-person-type`: 一人称数値行にDID NOT RAISE | 成功（見逃し） | 失敗（検出） |
| `identity-leaves-first-person-untrimmed`: 一人称正規化の明示文字列assertion | 成功（見逃し） | 失敗（検出） |
| `identity-ignores-name`: 名前だけ違う行の不等価assertion | 成功（見逃し） | 失敗（検出） |
| `identity-becomes-mutable`: 名前・一人称代入ともにDID NOT RAISE | 成功（見逃し） | 失敗（検出） |

保持契約の対照:

- `detach-return-dropped`: 旧試験も移管後の主試験も失敗。解除前値の検出を失っていない
- MemoryKindの値変更と互換的な語彙追加を調べた2観測は、採用した差分の価値に数えない。以下の保留記録に移す

各実行の前に作業ツリー内の `__pycache__` を除去し、`PYTHONDONTWRITEBYTECODE=1` を指定した。各旧新実行で所有者の変異前後のSHA256と失敗箇所を照合し、終了時は製品6ファイルと候補6試験ファイルを元バイト列へ復元した。補助実行器では、pytestの短縮表示や色付き表示についての前提を修正した。実際の失敗が意図した比較であることを確認し、表示検査を直して再実行した。製品の失敗や試験の不安定さではない。

## 試験

Python 3.10.22で実行。元の作業ツリーとは別の固定基準ツリーからソースを読むことを確認し、秘密情報を含む環境変数を除き、外部通信を禁止した。実LLM・live_api・qualityは実行していない。

- 未変更基準: 対象48件成功、関連75件成功
- 最終候補: 対象59件成功を2回、関連75件成功
- 変更した対象4ファイルのruffと `git diff --check`: 成功
- 全リポジトリ試験とCIは未実施。公開・統合前の独立確認は別途行う

対象は上記6ファイル。関連は `test_being_snapshot_codec.py`、`test_being_attachment_resolver.py`、`test_being_provisioning_service.py`、`test_in_memory_being_repository.py`、`test_sqlite_being_repository.py` の5ファイル。

## 保存レビューで見つけた入力の欠落

独立確認で、元の接続先(2,2)を(2,99)へ置き換えた候補が、世界だけ違う接続の拒否を失うと分かった。拒否の表に元の(2,2)を戻し、乗換えも(2,2)/(2,99)の両行にした。単に同じ分岐へ到達するだけでは元入力の代替にならない。

- 既接続の条件を「世界が同じ、またはプレイヤーが違う場合だけ拒否」へ誤変更すると、原試験は赤、弱まった候補57件は緑、復元後の59件は(2,2)行で赤になった
- 接続時に指定された世界を1へ落とす変異では、元の乗換え試験と復元した(2,2)行の双方が接続先比較で赤になった
- 15種類の検出強化と戻り値移管1対照は、復元後の固定試験でもすべて再実行した。追加の保存レビュー対照2件は、15種類の新規検出とは区別する

## 次の確認

固定差分と原assertionの保存先、一人称の3境界を別々に壊した失敗、C後の検出維持とMemoryKindの完全復元、製品バイト列の復元を独立に確認してから公開する。確認された製品不具合は無く、製品修正や外部Issueは含めない。公開後もマージは別の判断とする。

## 保留した1宣言

MemoryKindの閉集合比較 `test_four` は今回の完了信用に含めない。[#1631](https://github.com/Motifman/llm-rpg/issues/1631) は古い記憶のコード・設定・試験をまとめて整理する方針であり、保存の形 [#1625](https://github.com/Motifman/llm-rpg/issues/1625) を先に決める依存関係がある。直接の変更パスが重ならないだけでは独立した監査と判断できないため、削除案を外してファイル全体を基準バイト列へ戻した。

保存文字列を変える変異では従来の保存値試験が失敗し、互換的な5種類目を足す変異では閉集合比較だけが失敗した。いずれも保留判断の読取材料であり、今回採用した差分の改善件数には数えない。原48宣言のうち監査完了候補は47宣言、1宣言は保留である。
