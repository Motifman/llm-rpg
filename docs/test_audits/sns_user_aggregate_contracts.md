# SNS利用者集約と公開同一性の試験所有者

## なぜ整理するか

利用者の関係操作は状態とイベントを別々の試験で確認していた。
状態側は非公開属性へ依存し、イベント側は型付き対象IDを使うため、
宣言を消すだけでは整数入力・混在型入力のどちらかを失う。
同じ操作を守る専用イベント試験へ両方の入力行を先に移し、公開状態も同時に観測する。

拒否試験は専用例外だけでは、拒否前に関係や既存イベントを消す退行を見逃す。
他者の非空状態を別行で追加し、独立したtupleを使って拒否後の保持を確かめる。
公開識別子の代入拒否も、例外だけでなく元の値が残ることを確認する。

## 固定した範囲

- 元の母集団: UserAggregate 21宣言と公開同一性5宣言、計26宣言・31実行条件・92観測点
- 元試験: 457行。最終は19宣言・42条件・357行で100行減。製品・共有補助の変更は0
- 基準: PR #1779のhead `6b5c7c4c1174a870f631e16026ce10c1d689b2e0`、tree `890bc48b4a5695b296a29adf6f3426e18187f3ca`
- main `7c7dc63c5f4be701832a3f1443e27682fe9869d1` と対象2試験、User所有者、UserCommandService、SQLite復元経路の5blobが一致することを再確認
- 分類: 保持R10、観測修理F9、統合C7、無条件削除D0
- 公開同一性の元5宣言10条件は残す。名前・整数ID・作成時刻の違いをtoken文字列の違いの代用にしない

## 何をどこで守るか

関係6操作は専用イベント6宣言に分けたまま、次の3条件をそれぞれ確認する。

1. 元状態入力の整数owner=1、target=2。空の一覧から始め、元の追加後1件・解除後0件と端点を維持する
2. 元イベント入力の整数owner=1、target=UserId(2)。元どおり前提操作後にイベントを消去し、操作後の正確な単一件数・実型・端点・集約情報を維持する
3. 実呼出しで使うUserId同士。別対象のfollow/subscribe/blockを公開操作で先に作り、対象以外の関係と既存イベントを保つ

followだけはイベントのaggregate_idがint(owner)で、それ以外はowner自身である。
試験の共通化のために型を統一しない。元の空状態行を他者ありの行へ置き換えない。

ブロック連鎖は元の整数入力による0/0/1件を残し、型付き・他者ありの別行も持つ。
Unfollowed→Unsubscribed→Blockedという観測可能なイベント順序と、既存の先頭部分を確認する。
プロフィールは両項目更新とuser_name不変を移送し、片側だけ指定する補助行も追加する。

## 全26宣言の判断

Rは独立した契約を保持、Fは契約を残した観測修理、Cは同じ操作の保持先へ原入力・観測を移して統合したことを示す。
Cの行も、元の契約を不要と判断したものではない。

| 元宣言 | 判断 | 保存する契約・入力 | 保持先 |
|---|---|---|---|
| [test_create_user_aggregate_success](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L54-L60) | F | private属性を公開user_id/sns_user/関係一覧へ。self.user_id=1という元整数入力とSnsUser参照保持も落とさない | [test_create_user_aggregate_success](../../tests/domain/sns/test_user_aggregate.py#L101-L107) |
| [test_follow_user_success](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L62-L72) | C | 整数owner1/target2の元行を保持。型付きUserId行と同一視して置換しない | [test_follow_generates_event](../../tests/domain/sns/test_user_aggregate.py#L182-L191) |
| [test_follow_blocked_user_raises_error](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L74-L83) | F | 整数target2をblock済みという先行条件を維持。block関係と既存BlockedEventを非空で保つ | [test_follow_blocked_user_raises_error](../../tests/domain/sns/test_user_aggregate.py#L110-L119) |
| [test_unfollow_user_success](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L85-L96) | C | 整数target2をfollow→unfollowする元順序と空化を保持。別利用者の残存を追加 | [test_unfollow_generates_event](../../tests/domain/sns/test_user_aggregate.py#L193-L203) |
| [test_unfollow_not_followed_user_raises_error](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L98-L103) | F | 未follow target2拒否専用例外を維持。無関係な他者関係と既存イベントを先に入れる | [test_unfollow_not_followed_user_raises_error](../../tests/domain/sns/test_user_aggregate.py#L122-L130) |
| [test_block_user_success](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L105-L115) | C | 整数owner1/target2の端点検証を保持し公開block一覧へ | [test_block_generates_event](../../tests/domain/sns/test_user_aggregate.py#L205-L214) |
| [test_unblock_user_success](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L117-L128) | C | block→unblockの元入力を保持し公開一覧へ | [test_unblock_generates_event](../../tests/domain/sns/test_user_aggregate.py#L216-L226) |
| [test_subscribe_user_success](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L130-L144) | C | follow前提→subscribeと整数端点確認を保持し公開一覧へ | [test_subscribe_generates_event](../../tests/domain/sns/test_user_aggregate.py#L228-L239) |
| [test_subscribe_not_followed_user_raises_error](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L146-L151) | F | 未follow購読がCannotSubscribeNotFollowedUserExceptionに到達。自己購読/相手ブロックを混ぜず既存非空状態を保つ | [test_subscribe_not_followed_user_raises_error](../../tests/domain/sns/test_user_aggregate.py#L133-L141) |
| [test_unsubscribe_user_success](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L153-L165) | C | follow→subscribe→unsubscribe順序と購読だけ空になることを保持 | [test_unsubscribe_generates_event](../../tests/domain/sns/test_user_aggregate.py#L241-L253) |
| [test_update_user_profile_success](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L167-L178) | C | 両値更新/username不変をイベント保持先と同時に観測。private経由だけに依存しない | [test_update_profile_generates_event](../../tests/domain/sns/test_user_aggregate.py#L260-L268) |
| [test_block_removes_follow_and_subscribe](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L180-L194) | F | 元整数入力と3集合件数を保持。他者関係を先に入れtargetだけ解除、既存event prefixとUnfollowed→Unsubscribed→Blockedの順序も確認 | [test_block_removes_follow_and_subscribe](../../tests/domain/sns/test_user_aggregate.py#L144-L170) |
| [test_create_new_user_generates_event](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L196-L216) | R | 全payload、aggregate_id UserId(1)、aggregate_type、単一件数を維持。生成状態も併せて確認 | [test_create_new_user_generates_event](../../tests/domain/sns/test_user_aggregate.py#L172-L180) |
| [test_follow_generates_event](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L218-L233) | R | 元ownerは整数1、targetはUserId(2)。既存混在型入力を保持。状態行を吸収し、型付きownerと他者関係ありの行も追加して保持 | [test_follow_generates_event](../../tests/domain/sns/test_user_aggregate.py#L182-L191) |
| [test_unfollow_generates_event](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L235-L257) | R | follow後clear→unfollowのイベント単一件数/型/端点を保持。状態行を吸収 | [test_unfollow_generates_event](../../tests/domain/sns/test_user_aggregate.py#L193-L203) |
| [test_block_generates_event](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L259-L274) | R | 事前関係なしblockの単一event型/端点を保持。連鎖解除は別行 | [test_block_generates_event](../../tests/domain/sns/test_user_aggregate.py#L205-L214) |
| [test_unblock_generates_event](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L276-L298) | R | block後clear→unblockの元順序とevent型/端点を保持 | [test_unblock_generates_event](../../tests/domain/sns/test_user_aggregate.py#L216-L226) |
| [test_subscribe_generates_event](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L300-L322) | R | follow後clear→subscribeの元順序とevent型/端点を保持 | [test_subscribe_generates_event](../../tests/domain/sns/test_user_aggregate.py#L228-L239) |
| [test_unsubscribe_generates_event](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L324-L347) | R | follow+subscribe後clear→unsubscribeの元順序とevent型/端点を保持 | [test_unsubscribe_generates_event](../../tests/domain/sns/test_user_aggregate.py#L241-L253) |
| [test_update_profile_generates_event](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L349-L366) | R | 新bio/display_name、event型、user_id、aggregate情報と単一件数を保持。状態成功行を移送済み | [test_update_profile_generates_event](../../tests/domain/sns/test_user_aggregate.py#L260-L268) |
| [test_multiple_events_are_accumulated](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_user_aggregate.py#L368-L385) | F | 件数3と型集合を保持。正確な型順序と各payload、各段階の既存prefix不変を確認。時刻差だけの不等値では検査しない | [test_multiple_events_are_accumulated](../../tests/domain/sns/test_user_aggregate.py#L270-L281) |
| [test_new_content_with_reused_integer_has_distinct_identity](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_sns_public_identity.py#L25-L31) | R | post/replyの両行、同じ整数/本文、UUID4かつ小文字32桁、異なる識別子を保持 | [test_new_content_with_reused_integer_has_distinct_identity](../../tests/domain/sns/test_sns_public_identity.py#L25-L31) |
| [test_identity_is_read_only_and_survives_copy_and_deletion](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_sns_public_identity.py#L35-L44) | F | post/replyのdeepcopy→like→delete後token同一と代入AttributeErrorを保持。非空集合所有権とは別契約。公開代入拒否後にも元tokenを保持 | [test_identity_is_read_only_and_survives_copy_and_deletion](../../tests/domain/sns/test_sns_public_identity.py#L35-L45) |
| [test_restoration_rejects_invalid_identity](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_sns_public_identity.py#L48-L54) | R | 復元tokenの空文字/post_1/大文字F32/零32の4行と専用例外をそのまま保持 | [test_restoration_rejects_invalid_identity](../../tests/domain/sns/test_sns_public_identity.py#L49-L55) |
| [test_user_identity_does_not_depend_on_name_or_integer](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_sns_public_identity.py#L57-L64) | F | 同じUserId1/hero/勇者の別生成、deepcopy同一、代入拒否を保持。公開代入拒否後にも元tokenを保持 | [test_user_identity_does_not_depend_on_name_or_integer](../../tests/domain/sns/test_sns_public_identity.py#L58-L67) |
| [test_identity_value_object_is_immutable](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_sns_public_identity.py#L67-L71) | F | 代入拒否後に元token.valueも維持されることを観測。例外後に値を変える誤実装を区別する | [test_identity_value_object_is_immutable](../../tests/domain/sns/test_sns_public_identity.py#L70-L76) |

## 実呼出しと別の保持所有者

- UserCommandServiceは全関係操作とプロフィール更新を行って保存し、followへ相手の識別子と実行元情報を渡す
- SqliteSnsUserRepositoryとsqlite_sns_state_codecは保存された関係・作成時刻・識別子を復元する
- UserQueryServiceと両リポジトリは公開getter、relationship_between、get_user_profile_infoを利用する。今回、試験専用の製品入口は追加しない
- [公開識別子の保存試験](../../tests/infrastructure/repository/test_sns_identity_persistence.py)は再接続・複製・整数再利用・移行を守る
- [作者と親の束縛試験](../../tests/infrastructure/repository/test_sns_reference_bindings.py)は参照先の置換後にも作成時の識別子を保持する
- [公開SNSのコマンド試験](../../tests/application/social/public_sns/test_public_sns_command_service.py)は実follow/likeの出典と、同じ整数の別人・別投稿への再束縛拒否を守る
- [利用者コマンドの試験](../../tests/application/social/services/test_user_command_service.py)は保存・アプリケーション例外・通知発行を守る。元の整数/混在型入力や全イベント属性の代替とは扱わない

相手側のブロックによる購読拒否はRelationshipDomainServiceが所有する。
集約のsubscribeは自己購読、follow不在、重複購読の順で検査するため、
通常のblock後に出るfollow不在の例外を「ブロック専用拒否」の成功証拠にはしない。

## 履歴と残した保留

[bed4311](https://github.com/Motifman/llm-rpg/commit/bed4311bb4c530e7d69e5d32fb587c54db3874a1)で整数IDの状態試験が導入され、
[822a5b6](https://github.com/Motifman/llm-rpg/commit/822a5b69418a37537a93702f4cfdbfc262568cd3)で専用例外と型付き対象のイベント試験が加わった。
このため、整数とUserIdの混在を単なる記述誤りとして消していない。

[6181ea6](https://github.com/Motifman/llm-rpg/commit/6181ea6c5810203ff82942b55f1acfbe7a6b3d2d)は整数採番再利用から公開参照を独立させ、
[eaade2b](https://github.com/Motifman/llm-rpg/commit/eaade2b52c4fed661c04c1588bd27ab174596482)は作者・親・通知先を作成時の対象へ束縛した。
古い集約ファイルを上書きするとこれらを失うため、製品ファイルは変更しない。

[#1456](https://github.com/Motifman/llm-rpg/pull/1456)の構築入力/取得結果の外側list・set所有権は、元26の外にある別契約として保留する。
新3宣言10条件を今回の分母へ加えず、現行のaliasを正しい期待へ反転しない。
今回のtupleは拒否前の独立した観測用であり、製品のgetter copyを修理したものではない。

## 実行根拠と限界

- Python3.10.22と固定依存、各専用作業ツリー自身のsrcを使い、外部接続を遮断して実行
- 編集前: 対象31条件・関連1091条件が成功
- C7を残した保持先先行受入: 49条件成功
- 関連範囲: tests/domain/sns、tests/application/social、SNSの永続化・参照束縛・公開読取・snapshot・通知metadata・InMemory/SQLite保存の10試験ファイル。対象件数は関連に含む
- 初回の関連指定は存在しないファイル名で収集前終了。試験失敗や成功に計上せず、正しい12選択で改めて全1091条件を実行
- 全リポジトリ試験や実LLMの評価は、このローカル検証では実行していない

- 削除後: 対象42条件・関連1102条件が成功。基準の関連1091から元対象31を引いた1060条件は変更せず保持
- 元7宣言は共存49成功と独立した保存性審査を終えてから削除。退去前後で保持する全モジュールの構文木が一致することを確認
- ruff 0.16.8による変更2試験の検査とgit diff --checkが成功
- 対照は最初の60種120実行と追補3種6実行に分けて実施し、計63種126実行。39種は旧新双方で検知、24種は旧側が見逃し保持側で検知
- 各対照は旧側31条件と保持側42条件で同じ製品退行を実行。保持側の比較中は元7宣言を選択から除外し、その現物は保存性審査まで残した
- 各回に変更した製品bytesを復元・照合し、終了後に元側・保持側・最終候補の各作業ツリーで全製品1587ファイルも照合。最終製品差分は0
- 旧新の主観測が意図したassertまたは専用例外の不発で失敗したことを確認。通知の誤型は互換payloadを持つ別の実型へ置き換え、引数不一致のTypeErrorを証拠にしていない
- 7種では型付き行の事前状態assertも退行を検知し、pytestはそれをfixture準備時errorと分類した。どれも主要な試験本体が意図したassertで別に失敗しており、準備errorだけを捕捉の根拠にしていない
- 初回の1組2実行は、上のfixture assertを集計器が基盤障害扱いして停止した。製品を復元し、集計条件だけを修正して別の出力名で全60組を再実行。この初回2実行を主126実行へ加えていない。試験や製品の期待を弱めて通したものではない

## 旧新対照の全一覧

「旧」は編集前31条件、「保持」は統合後42条件を示す。
番号1〜60が最初の主対照、61〜63が通知蓄積順序と片側プロフィール更新の追補である。
全行で製品bytesの復元を確認した。

| 番号 | 退行 | 観測する契約 | 旧 | 保持 |
|---|---|---|---|---|
| 1 | `constructor_owner_replaced` | 構築時のID保持 | 検知 | 検知 |
| 2 | `constructor_entity_replaced` | 元SnsUser参照の保持 | 検知 | 検知 |
| 3 | `follow_getter_loses_state` | 公開getterから実際の関係状態を取得 | 見逃し | 検知 |
| 4 | `block_getter_loses_state` | 公開getterから実際の関係状態を取得 | 見逃し | 検知 |
| 5 | `subscribe_getter_loses_state` | 公開getterから実際の関係状態を取得 | 見逃し | 検知 |
| 6 | `follow_state_omitted` | 元状態成功の観測を保持 | 検知 | 検知 |
| 7 | `unfollow_state_omitted` | 元状態成功の観測を保持 | 検知 | 検知 |
| 8 | `block_state_omitted` | 元状態成功の観測を保持 | 検知 | 検知 |
| 9 | `unblock_state_omitted` | 元状態成功の観測を保持 | 検知 | 検知 |
| 10 | `subscribe_state_omitted` | 元状態成功の観測を保持 | 検知 | 検知 |
| 11 | `unsubscribe_state_omitted` | 元状態成功の観測を保持 | 検知 | 検知 |
| 12 | `unfollow_clears_all_targets` | 解除対象以外の非空関係を残す | 見逃し | 検知 |
| 13 | `unblock_clears_all_targets` | 解除対象以外の非空関係を残す | 見逃し | 検知 |
| 14 | `unsubscribe_clears_all_targets` | 解除対象以外の非空関係を残す | 見逃し | 検知 |
| 15 | `follow_guard_omitted` | 元の専用例外とガード到達 | 検知 | 検知 |
| 16 | `follow_rejection_erases_events` | 拒否前の非空通知を保つ | 見逃し | 検知 |
| 17 | `follow_rejection_erases_relations` | 拒否前の独立snapshotで関係保持を観測 | 見逃し | 検知 |
| 18 | `unfollow_guard_omitted` | 元の専用例外とガード到達 | 検知 | 検知 |
| 19 | `unfollow_rejection_erases_events` | 拒否前の非空通知を保つ | 見逃し | 検知 |
| 20 | `unfollow_rejection_erases_relations` | 拒否前の独立snapshotで関係保持を観測 | 見逃し | 検知 |
| 21 | `subscribe_guard_omitted` | 元の専用例外とガード到達 | 検知 | 検知 |
| 22 | `subscribe_rejection_erases_events` | 拒否前の非空通知を保つ | 見逃し | 検知 |
| 23 | `subscribe_rejection_erases_relations` | 拒否前の独立snapshotで関係保持を観測 | 見逃し | 検知 |
| 24 | `block_skips_unfollow` | ブロック時に両方の関係を解除 | 検知 | 検知 |
| 25 | `block_skips_unsubscribe` | ブロック時に両方の関係を解除 | 検知 | 検知 |
| 26 | `block_reverses_unlink_notifications` | 連鎖解除の観測可能な通知順序 | 見逃し | 検知 |
| 27 | `profile_skips_bio` | プロフィールの両方の独立した更新 | 検知 | 検知 |
| 28 | `profile_skips_display_name` | プロフィールの両方の独立した更新 | 検知 | 検知 |
| 29 | `profile_replaces_username` | 更新しないuser_nameを保持 | 検知 | 検知 |
| 30 | `create_new_user_omits_event` | 専用通知の単一件数を保持 | 検知 | 検知 |
| 31 | `follow_omits_event` | 専用通知の単一件数を保持 | 検知 | 検知 |
| 32 | `unfollow_omits_event` | 専用通知の単一件数を保持 | 検知 | 検知 |
| 33 | `block_omits_event` | 専用通知の単一件数を保持 | 検知 | 検知 |
| 34 | `unblock_omits_event` | 専用通知の単一件数を保持 | 検知 | 検知 |
| 35 | `subscribe_omits_event` | 専用通知の単一件数を保持 | 検知 | 検知 |
| 36 | `unsubscribe_omits_event` | 専用通知の単一件数を保持 | 検知 | 検知 |
| 37 | `update_user_profile_omits_event` | 専用通知の単一件数を保持 | 検知 | 検知 |
| 38 | `events_duplicated` | 専用通知の二重発行を拒否 | 検知 | 検知 |
| 39 | `unfollow_wrong_event_type` | 同じpayloadを持つ別の通知型を拒否 | 検知 | 検知 |
| 40 | `block_wrong_event_type` | 同じpayloadを持つ別の通知型を拒否 | 検知 | 検知 |
| 41 | `unblock_wrong_event_type` | 同じpayloadを持つ別の通知型を拒否 | 検知 | 検知 |
| 42 | `follow_wrong_actor` | 通知の実行者と対象の区別 | 検知 | 検知 |
| 43 | `unfollow_wrong_actor` | 通知の実行者と対象の区別 | 検知 | 検知 |
| 44 | `block_wrong_actor` | 通知の実行者と対象の区別 | 検知 | 検知 |
| 45 | `unblock_wrong_actor` | 通知の実行者と対象の区別 | 検知 | 検知 |
| 46 | `subscribe_wrong_actor` | 通知の実行者と対象の区別 | 検知 | 検知 |
| 47 | `unsubscribe_wrong_actor` | 通知の実行者と対象の区別 | 検知 | 検知 |
| 48 | `user_events_wrong_aggregate_type` | 元の通知aggregate_typeを保持 | 検知 | 検知 |
| 49 | `follow_clears_event_prefix` | 既存通知の順序付き先頭部分を保持 | 見逃し | 検知 |
| 50 | `unfollow_clears_event_prefix` | 既存通知の順序付き先頭部分を保持 | 見逃し | 検知 |
| 51 | `block_clears_event_prefix` | 既存通知の順序付き先頭部分を保持 | 見逃し | 検知 |
| 52 | `unblock_clears_event_prefix` | 既存通知の順序付き先頭部分を保持 | 見逃し | 検知 |
| 53 | `subscribe_clears_event_prefix` | 既存通知の順序付き先頭部分を保持 | 検知 | 検知 |
| 54 | `unsubscribe_clears_event_prefix` | 既存通知の順序付き先頭部分を保持 | 見逃し | 検知 |
| 55 | `update_user_profile_clears_event_prefix` | 既存通知の順序付き先頭部分を保持 | 検知 | 検知 |
| 56 | `new_uuid_reused` | 同じ整数の新規対象をUUIDで区別 | 検知 | 検知 |
| 57 | `restore_ignores_invalid_uuid` | 元4種の復元token拒否を保持 | 検知 | 検知 |
| 58 | `user_identity_mutates_then_rejects` | 属性代入拒否後も元tokenを保持 | 見逃し | 検知 |
| 59 | `content_identity_mutates_then_rejects` | 属性代入拒否後も元tokenを保持 | 見逃し | 検知 |
| 60 | `value_identity_mutates_then_rejects` | 値属性の拒否後も元valueを保持 | 見逃し | 検知 |
| 61 | `events_prepend_instead_of_append` | 蓄積する実通知の順序を逆転させない | 見逃し | 検知 |
| 62 | `profile_bio_requires_both_fields` | bioだけ指定した更新を落とさない | 見逃し | 検知 |
| 63 | `profile_name_requires_both_fields` | 表示名だけ指定した更新を落とさない | 見逃し | 検知 |
