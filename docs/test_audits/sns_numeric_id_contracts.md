# SNS数値IDの契約監査

## 対象と結論

PostId、ReplyId、UserId、NotificationIdの公開値契約を対象とする。元の4ファイル54宣言をR33（保持）/F9（修理）/C12（統合）/D0（単純削除）へ分類した。12宣言を同じファイルの保持先へ統合し、NotificationIdの不変性1宣言を追加したため、最終43宣言49ケースになる。文字列生成3種類は3行の表へ移した。試験は429行から390行へ減り、製品・共有支援コードは変更しない。

最初の試験は54件すべて成功したが、Post/Reply/Userの不変性3宣言は構築するだけで再代入を試していなかった。また、等しくないIDに異なるhashを要求する条件が6箇所あり、合法な衝突を禁止していた。通常の代入拒否を観測し、等価性と集合キーの契約を残す形へ修理した。

固定原母集団はmain `ba942f5a9cad4b6d362c9e2ce59566cc8ce3396f` の54宣言。実行基準はmain `00aeddef745aba1ec7743ca3118bbe239a01b3c3` を復元した固定作業木であり、全体を最新mainへ更新した試験ではない。比較先 `e5b2b2a24646309b365772fafce431b42041ad89` と、実行対象・domain/sns所有者・依存固定・CI等83パスのblobが一致することを確認した。広い呼出元確認で異なるworld_runtime.pyはLLM_TOOL_MODE撤去の差で、数値ID利用箇所は不変だった。対象外の記憶撤去や起動設定の差は取り込んでいない。

| 元ファイル | 宣言 | 基準・比較先共通blob |
|---|---:|---|
| tests/domain/sns/test_post_id.py | 15 | 03ad7b649a18a215a30440a5e878193051325eff |
| tests/domain/sns/test_reply_id.py | 15 | 160b67863874770b37251b0e9699d84a57fd8f58 |
| tests/domain/sns/test_user_id.py | 15 | 9e5cd478a7fd9d99ad1449a6946015af8ad86b73 |
| tests/domain/sns/test_notification_id.py | 9 | 073d3e5326068fafd06783eae8492c19db3b0122 |

## 所有者と保持する理由

製品所有者は `src/ai_rpg_world/domain/sns/value_object/{post,reply,user,notification}_id.py` の4型。それぞれ直接構築、公開create、0以下の拒否、str/int、型別等価性、hashを所有する。InMemoryの4リポジトリでは型付きIDを辞書キーに使い、SQLiteの4リポジトリとsqlite_sns_state_codecは整数と型付きIDを相互変換する。public_sns_snapshot_codecも値の保存と同値キーの重複検査を行う。

InMemoryPublicSnsReadRepositoryのfind_content_by_id、scan_repliesはPostId/ReplyIdの型を区別し、NotificationCommandServiceはUserId一致で宛先を確かめる。Like/MentionはPostIdまたはReplyIdを保持し、Follow/Block/SubscribeはUserId等価性を自己参照拒否と関係照合に使う。同じ数値でも別種IDが等しくなる退行には、独立した検査が必要である。

既存のリポジトリ共通試験と具象InMemory/SQLite試験は検索・保存の保持先だが、公開factory、0/負値拒否、型別比較、通常再代入のすべてを代替しない。4つのID試験をこれらの主保持先として残した。createの直接本番呼出しが静的検索で0件でも、公開APIを撤去する根拠にはしない。

数値IDは集合キーとして同型同値が等しい契約を持つ。一方、test_sns_public_identity.pyとtest_sns_identity_persistence.pyは整数再利用時にもUUIDを別の対象へ継がない契約であり、別の所有者である。数値IDの不変性をUUID試験で代替しない。

## 統合時の保存条件

各Post/Reply/Userで、次の4宣言を同一ファイルの保持先へ統合した。保持先と元12宣言の並存状態で61件成功を確認してから退かせた。

- 最小値1の単独構築 → test_boundary_*_id_values。入力1とvalue==1を維持
- 通常文字列123の単独生成 → test_create_from_various_string_formats。valueだけでなく、返却値と当該ID型(123)の等価性を維持。0埋め00123と大きな999999も独立した期待値で残す
- 負値-1の単独拒否 → test_error_message_contains_value。同じ入力・ドメイン例外型と、診断へ含まれる-1を維持
- test_type_safety → 構築境界。isinstance(value, int)とvalue>0を維持。1.0==1であるため、数値等価性だけには弱めない

整数factoryと直接構築、解析不能文字列と解析後の0拒否、0と負値、str/intとvalue取得は別の契約として残す。既存の「!= None」は比較実装を通る必要があり、「is not None」へ変えていない。整数1を持つ兄弟3型も非等価比較へ追加した。

NotificationIdにもvalue再代入の拒否と元値維持を1宣言で追加し、既存の文字列・整数factoryは同型IDとの等価性で返却型を補強した。型注釈外のfloat/bool/Noneを一律拒否する新仕様は導入しない。999999を真の最大値とも扱わない。

## 元54宣言の台帳

各見出しは元ファイル、名前はそのファイルのTestクラスに属する元宣言。Rは維持、Fは契約を維持して観測を修理、Cは指定保持先へ移した宣言である。追加したNotificationId.test_immutabilityは元54の外として扱う。

### tests/domain/sns/test_post_id.py

| 印 | 元宣言 | 契約・残る保持先 |
|---|---|---|
| C | `test_create_post_id_success` | 直接構築した最小正数1をvalueに保持する。保持先: test_boundary_post_id_values |
| C | `test_create_post_id_from_string_success` | 公開createが文字列123から同じ型の数値IDを返す。保持先: test_create_from_various_string_formats |
| R | `test_create_post_id_from_int_string_success` | 公開createが整数123を値を変えず受け付ける |
| R | `test_invalid_post_id_zero_raises_error` | 0の直接構築を対応するドメイン例外で拒む |
| C | `test_invalid_post_id_negative_raises_error` | 負数-1を対応するドメイン例外で拒む。保持先: test_error_message_contains_value |
| R | `test_invalid_post_id_string_raises_error` | 解析不能文字列を対応するドメイン例外へ写す |
| R | `test_boundary_post_id_values` | 直接構築で1と大きな正数999999の値を保持する |
| F | `test_equality_comparison` | 同種・同値は等しく、同種・別値は異なる。非等値hash条件を除き、等価性・等値hash・集合利用を各主保持先へ残す |
| R | `test_string_representation` | strとintの公開変換が123を正確に返す |
| F | `test_immutability` | 通常のvalueへの再代入が拒否され、値が変化しない。value=2の拒否と元値1を観測 |
| F | `test_hash_functionality` | 等しいIDのhashは等しく、集合では同値が統合され別値が残る。非等値hash条件を除き、等価性・等値hash・集合利用を各主保持先へ残す |
| R | `test_comparison_with_non_post_id` | 文字列1・整数1・Noneを同一IDとして扱わない |
| R | `test_create_from_various_string_formats` | 通常文字列、0埋め文字列、大きな正数文字列を数値へ正規化する |
| R | `test_error_message_contains_value` | 負値-1の拒否時に入力値を診断へ含める |
| C | `test_type_safety` | 整数1を入力した結果valueがint型で正である。保持先: test_boundary_post_id_values |

### tests/domain/sns/test_reply_id.py

| 印 | 元宣言 | 契約・残る保持先 |
|---|---|---|
| C | `test_create_reply_id_success` | 直接構築した最小正数1をvalueに保持する。保持先: test_boundary_reply_id_values |
| C | `test_create_reply_id_from_string_success` | 公開createが文字列123から同じ型の数値IDを返す。保持先: test_create_from_various_string_formats |
| R | `test_create_reply_id_from_int_string_success` | 公開createが整数123を値を変えず受け付ける |
| R | `test_invalid_reply_id_zero_raises_error` | 0の直接構築を対応するドメイン例外で拒む |
| C | `test_invalid_reply_id_negative_raises_error` | 負数-1を対応するドメイン例外で拒む。保持先: test_error_message_contains_value |
| R | `test_invalid_reply_id_string_raises_error` | 解析不能文字列を対応するドメイン例外へ写す |
| R | `test_boundary_reply_id_values` | 直接構築で1と大きな正数999999の値を保持する |
| F | `test_equality_comparison` | 同種・同値は等しく、同種・別値は異なる。非等値hash条件を除き、等価性・等値hash・集合利用を各主保持先へ残す |
| R | `test_string_representation` | strとintの公開変換が123を正確に返す |
| F | `test_immutability` | 通常のvalueへの再代入が拒否され、値が変化しない。value=2の拒否と元値1を観測 |
| F | `test_hash_functionality` | 等しいIDのhashは等しく、集合では同値が統合され別値が残る。非等値hash条件を除き、等価性・等値hash・集合利用を各主保持先へ残す |
| R | `test_comparison_with_non_reply_id` | 文字列1・整数1・Noneを同一IDとして扱わない |
| R | `test_create_from_various_string_formats` | 通常文字列、0埋め文字列、大きな正数文字列を数値へ正規化する |
| R | `test_error_message_contains_value` | 負値-1の拒否時に入力値を診断へ含める |
| C | `test_type_safety` | 整数1を入力した結果valueがint型で正である。保持先: test_boundary_reply_id_values |

### tests/domain/sns/test_user_id.py

| 印 | 元宣言 | 契約・残る保持先 |
|---|---|---|
| C | `test_create_user_id_success` | 直接構築した最小正数1をvalueに保持する。保持先: test_boundary_user_id_values |
| C | `test_create_user_id_from_string_success` | 公開createが文字列123から同じ型の数値IDを返す。保持先: test_create_from_various_string_formats |
| R | `test_create_user_id_from_int_string_success` | 公開createが整数123を値を変えず受け付ける |
| R | `test_invalid_user_id_zero_raises_error` | 0の直接構築を対応するドメイン例外で拒む |
| C | `test_invalid_user_id_negative_raises_error` | 負数-1を対応するドメイン例外で拒む。保持先: test_error_message_contains_value |
| R | `test_invalid_user_id_string_raises_error` | 解析不能文字列を対応するドメイン例外へ写す |
| R | `test_boundary_user_id_values` | 直接構築で1と大きな正数999999の値を保持する |
| F | `test_equality_comparison` | 同種・同値は等しく、同種・別値は異なる。非等値hash条件を除き、等価性・等値hash・集合利用を各主保持先へ残す |
| R | `test_string_representation` | strとintの公開変換が123を正確に返す |
| F | `test_immutability` | 通常のvalueへの再代入が拒否され、値が変化しない。value=2の拒否と元値1を観測 |
| F | `test_hash_functionality` | 等しいIDのhashは等しく、集合では同値が統合され別値が残る。非等値hash条件を除き、等価性・等値hash・集合利用を各主保持先へ残す |
| R | `test_comparison_with_non_user_id` | 文字列1・整数1・Noneを同一IDとして扱わない |
| R | `test_create_from_various_string_formats` | 通常文字列、0埋め文字列、大きな正数文字列を数値へ正規化する |
| R | `test_error_message_contains_value` | 負値-1の拒否時に入力値を診断へ含める |
| C | `test_type_safety` | 整数1を入力した結果valueがint型で正である。保持先: test_boundary_user_id_values |

### tests/domain/sns/test_notification_id.py

| 印 | 元宣言 | 契約・残る保持先 |
|---|---|---|
| R | `test_create_valid_notification_id` | 直接構築した1のvalue/int/strが一致する |
| R | `test_create_notification_id_from_string` | 公開createが文字列123を数値へ変換する |
| R | `test_create_notification_id_from_int` | 公開createが整数456を保持する |
| R | `test_invalid_notification_id_zero` | 0を対応する例外と正値要件の診断で拒否する |
| R | `test_invalid_notification_id_negative` | -1を対応する例外と正値要件の診断で拒否する |
| R | `test_invalid_string_notification_id` | 解析不能文字列をドメイン例外へ写す |
| R | `test_invalid_zero_string_notification_id` | 解析できる文字列0も値検査を経て拒否される |
| R | `test_equality` | 同種同値が等しく、異値・文字列とは異なる |
| R | `test_hash` | 同種同値は同じhashで集合内で統合される |

## 独立確認と変異検査

編集前の独立第二読で、factoryの返却型とint値型を移管先へ残すこと、Noneを同一性比較へ弱めないこと、兄弟IDの同値比較、NotificationIdの不変性追加を確認した。元の全入力・診断を維持し、別件のLike試験や製品の型拒否仕様へ範囲を広げていない。

別の作業木で30種類を旧新それぞれ実行し、60実行がすべて計画した成否になった。変異後は製品・試験を元のバイト列へ戻し、差分が空であることを確認した。最終候補の製品ファイルも基準と一致する。

| 区分 | 意図的な変更 | 種類 | 旧 / 新 |
|---|---|---:|---|
| 改善 | 4型の通常再代入を許す | 4 | 成功 / 失敗 |
| 改善 | 同値を持つ他のID型まで等しい扱いにする | 4 | 成功 / 失敗 |
| 改善 | 整数factoryだけ別ID型を返す | 4 | 成功 / 失敗 |
| 改善 | Notificationの文字列factoryだけ別ID型を返す | 1 | 成功 / 失敗 |
| 保存 | Post/Reply/Userの文字列factoryを別ID型へ変える | 3 | 失敗 / 失敗 |
| 保存 | 同値IDのhashをインスタンス依存にする | 4 | 失敗 / 失敗 |
| 保存 | Post/Reply/Userの構築値を1.0へ変える | 3 | 失敗 / 失敗 |
| 保存 | Post/Reply/Userで負値を受理する | 3 | 失敗 / 失敗 |
| 保存 | Post/Reply/Userで最小正数1を拒否する | 3 | 失敗 / 失敗 |
| 合法対照 | 4型のhashを定数へ変えて衝突させる | 1 | 旧6件失敗 / 新49件成功 |

改善13種類、保存16種類、合法対照1種類。元C12の保持対象には対応する保存変異がある。合法対照は衝突自体を拒否しない確認であり、定数hashを製品へ採用する推奨ではない。

[Pythonのhash契約](https://docs.python.org/3.10/reference/datamodel.html#object.__hash__)は同値のhash一致を要求するが、異値の衝突は禁止しない。同じ数値を持つ別ID型もhashは同じでよい。通常の代入拒否は[dataclassesの不変インスタンス](https://docs.python.org/3.10/library/dataclasses.html#frozen-instances)を根拠に、内部フラグではなく公開操作で確認した。

## 実行結果と限界

| 実行 | 成功ケース | 失敗・skip |
|---|---:|---:|
| 基準4ファイル | 54 | 0 |
| 基準SNS全域と保存・読取関連 | 655 | 0 |
| 保持先と元C12の並存 | 61 | 0 |
| 統合後4ファイル | 49 | 0 |
| 最終SNS全域と保存・読取関連 | 650 | 0 |

関連655/650は対象54/49をそれぞれ含むため、足し合わせない。対象外の601ケースは同じ収集IDのまま成功した。

- Python3.10.22で、各作業木のsrcを読むことを確認し、通信を遮断して直列実行。実LLM・外部APIの実行なし
- 4試験のruff0.16.8とgit diff --checkが成功。製品・共通支援の変更なし
- 通常CIの入口はPython3.10の `uv run --frozen pytest -n auto`。この監査では全リポジトリ試験と公開headのCIは実行していない
- 再現する対象コマンド: `uv run --frozen pytest tests/domain/sns/test_post_id.py tests/domain/sns/test_reply_id.py tests/domain/sns/test_user_id.py tests/domain/sns/test_notification_id.py`
- 関連はtests/domain/sns、InMemory/SQLiteのSNSリポジトリ、公開読取、UUID保存、参照束縛、通知メタデータ、SNSのJSON保存・復元を実行した

## 履歴と並行変更

Post/Reply/Userの元試験は[822a5b6](https://github.com/Motifman/llm-rpg/commit/822a5b69418a37537a93702f4cfdbfc262568cd3)、Notificationの元試験は[65fabcb](https://github.com/Motifman/llm-rpg/commit/65fabcb14f2e94fb4f87f8d56ac362024b259cc7)の包括的なSNS試験追加に由来する。代表原本との比較では本体は不変で、後続は配置とimport変更だった。製品はそれぞれ[749b9a0](https://github.com/Motifman/llm-rpg/commit/749b9a05ae5895dd48c1fbbc2ac362b1067fe86e)、[6cb1a2a](https://github.com/Motifman/llm-rpg/commit/6cb1a2ab13e3e2b71bdcbc67e992cd3a402a8fe3)で公開値として追加された。個別障害の履歴がなくても公開契約を不要とは判定しない。

2026-10-14時点の並行PRは、[#1456](https://github.com/Motifman/llm-rpg/pull/1456)が集約の集合所有権、[#1457](https://github.com/Motifman/llm-rpg/pull/1457)が画面参照寿命、[#1458](https://github.com/Motifman/llm-rpg/pull/1458)が詳細ページング、[#1462](https://github.com/Motifman/llm-rpg/pull/1462)が作者限定本文の配送を扱う。全変更パス・差分と公開headを確認し、今回の数値ID所有者・試験との直接重複はなかった。それぞれの意味を数値IDの値検査へ取り込まず、既存保持試験も変更していない。

開始後にmainが `fe8cab46646d39bf718a13cf936aecadc68e62b0` へ進んだ。e5bからの64変更を照合し、上の83パスと関連650の収集対象には交差がなかった。広い呼出元ではworld_runtime.pyが交差するが、差分は記憶呼出し・生成時の設定とstore配線で、数値IDの契約は変更していない。この最新mainを統合して実行した結果ではなく、固定00ae上の検証である。

次段は公開前のmain・並行PRの再照合と、正確な公開headのCI確認である。SNS全体の権限・配送安全性、float/boolの実行時受理、記憶の撤去判断、未監査の兄弟値型はこの結果から完了扱いにしない。
