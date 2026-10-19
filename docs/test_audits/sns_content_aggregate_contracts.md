# SNS内容集約95の監査

## なぜ

基底用・投稿用・返信用の3ファイルが、同じPost/Replyの公開操作を繰り返していた。元の入力と途中状態を保持先へ集め、返信イベントの種類、拒否後の非空状態、保存時刻や識別子の受け渡しを独立に観測する。製品の挙動は変更しない。

## 範囲と結果

- 固定親は [#1779](https://github.com/Motifman/llm-rpg/pull/1779) の `6b5c7c4c1174a870f631e16026ce10c1d689b2e0`、tree `890bc48b4a5695b296a29adf6f3426e18187f3ca`
- 元はBase38・Post29・Reply28の95宣言、1557行、assert/raisesの観測記録310件
- 独立審査後の分類はR13・F17・C59・D6。Cは削減目標ではなく、保持先の先行受入と旧新対照を条件に確定
- 最終は集約22宣言66条件と、値型へ移した2宣言4条件。計24宣言70条件
- 集約587行、PostContentへの追加15行。元1557行に対し955行減。製品・共有補助の変更0
- 利用者21・公開同一性5は監査信用に加えない。親PostContentの既存全宣言/assert/入力は追加以外AST不変

## 境界ごとの判断

`test_base_sns_aggregate.py`も実際にはPost/Replyを作っているため、独立した基底用の証明ではない。共通操作を`test_content_aggregate_contracts.py`へ集めた。投稿の親禁止・公開範囲・作成時刻ソート・表示・子返信管理はPost側、返信の直接構築時の親禁止はReply側へ置く。

値型を作るだけで先に失敗するID、Mention、本文/タグ拒否は値型の保持先へ移す。一方、ASCII/日本語280文字と10タグの成功は元と同じ集約createまで通す。値型の成功だけでは、集約が本文を切る・タグを捨てる退行を捕まえられないためである。

## 元95宣言の判断

Rは独立契約の保持（移動を含む）、Fは観測の修理、Cは保持先への統合、Dは独立した既存証明がある重複の削除。下表は元宣言を全て含む。元宣言へのリンクは変更しない固定mainに結び、保持先はこの変更後のファイルを指す。

|元宣言|判定|保持先|保持する入力・判断理由|
|---|---|---|---|
|[B01 test_post_aggregate_creation_success](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L25-L40)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|メンションなし投稿の全8期待値を保持先の独立行へ移す|
|[B02 test_reply_aggregate_creation_success](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L42-L58)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|投稿親・空集合・未削除を返信生成の行へ移す|
|[B03 test_post_aggregate_properties](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L60-L82)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)<br>[test_content_aggregate_contracts.py::test_collection_getters_do_not_expose_owned_state](../../tests/domain/sns/test_content_aggregate_contracts.py#L229)|post_id/post_content別名とdummy追加によるcopy観測の両方を保持する|
|[B04 test_post_aggregate_is_private](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L84-L104)|R|[test_post_aggregate.py::test_is_private](../../tests/domain/sns/test_post_aggregate.py#L73)|移動のみ。配送可否の試験ではない|
|[B05 test_post_aggregate_get_sort_key_by_created_at](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L106-L116)|F|[test_post_aggregate.py::test_created_at_sort_key](../../tests/domain/sns/test_post_aggregate.py#L85)|isinstance(datetime)とcreated_at一致を保持。復元に明示した固定時刻を加え、現在時刻を返す誤実装と分離する|
|[B06 test_reply_aggregate_properties](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L118-L134)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|reply_id別名を含む元9期待値を保持する|
|[B07 test_like_functionality_success](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L136-L153)|C|[test_content_aggregate_contracts.py::test_like_toggle_preserves_actor_state_and_event_prefix](../../tests/domain/sns/test_content_aggregate_contracts.py#L240)|元のユーザー2を2回操作しTrue→False、1→0を保存する|
|[B08 test_like_functionality_multiple_users](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L155-L179)|C|[test_content_aggregate_contracts.py::test_like_toggle_preserves_other_users](../../tests/domain/sns/test_content_aggregate_contracts.py#L262)|元の2/3/4を追加、3だけ解除し件数3→2。残存2/4も明示する|
|[B09 test_like_invalid_content_type_raises_error](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L181-L191)|F|[test_content_aggregate_contracts.py::test_rejected_content_operation_preserves_state_and_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L332)|invalid_typeと専用例外・日本語診断を保持。非空likes/mentionsと既存イベントの不変を追加|
|[B10 test_like_content_type_mismatch_post_aggregate](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L193-L206)|R|[test_content_aggregate_contracts.py::test_direct_like_keeps_legacy_cross_kind_behavior](../../tests/domain/sns/test_content_aggregate_contracts.py#L357)|名前は不一致拒否を示すが実際は許可の正の試験。拒否へ逆転しない。製品呼出し0のみで消さない|
|[B11 test_like_content_type_mismatch_reply_aggregate](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L208-L220)|R|[test_content_aggregate_contracts.py::test_direct_like_keeps_legacy_cross_kind_behavior](../../tests/domain/sns/test_content_aggregate_contracts.py#L357)|ReplyIdにpost文字列を許可する元入力を保持。誤ラベルの配送影響は別調査|
|[B12 test_delete_functionality_success](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L222-L231)|C|[test_content_aggregate_contracts.py::test_delete_preserves_existing_state_and_event_prefix](../../tests/domain/sns/test_content_aggregate_contracts.py#L296)|投稿作者によるdeleted=Trueを共通削除保持先へ|
|[B13 test_delete_unauthorized_user_raises_error](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L233-L243)|C|[test_content_aggregate_contracts.py::test_rejected_content_operation_preserves_state_and_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L332)|非作者UserId(2)とOwnershipException診断を保持先へ。後状態/既存eventも追加|
|[B14 test_delete_invalid_content_type_raises_error](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L245-L253)|F|[test_content_aggregate_contracts.py::test_rejected_content_operation_preserves_state_and_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L332)|削除種別invalid_typeの診断を保持。作者一致かつ未削除の前提を明示|
|[B15 test_delete_reply_functionality_success](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L255-L265)|C|[test_content_aggregate_contracts.py::test_delete_preserves_existing_state_and_event_prefix](../../tests/domain/sns/test_content_aggregate_contracts.py#L296)|返信作者によるdeleted=Trueを共通削除保持先へ|
|[B16 test_delete_already_deleted_post_raises_error](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L267-L280)|F|[test_content_aggregate_contracts.py::test_rejected_content_operation_preserves_state_and_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L332)|作者による一回目成功と二回目ContentAlreadyDeletedException診断を保持。削除イベントを消さないことも確認|
|[B17 test_delete_already_deleted_reply_raises_error](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L282-L296)|F|[test_content_aggregate_contracts.py::test_rejected_content_operation_preserves_state_and_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L332)|返信の二重削除専用診断と最初の削除イベントを保持|
|[B18 test_get_content_type_post](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L298-L305)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|post文字列を生成行の明示期待へ移す|
|[B19 test_get_content_type_reply](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L307-L315)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|reply文字列を返信行の明示期待へ移す|
|[B20 test_get_parent_info_post](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L317-L326)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|投稿のget_parent_info==(None,None)を残す|
|[B21 test_get_parent_info_reply_with_post_parent](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L328-L338)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|投稿親IDと空返信親を保持|
|[B22 test_get_parent_info_reply_with_reply_parent](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L340-L350)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|返信親ReplyId(1)と内容ReplyId(2)の区別を保持|
|[B23 test_add_mention_functionality](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L352-L362)|C|[test_content_aggregate_contracts.py::test_public_mention_changes_preserve_other_entries](../../tests/domain/sns/test_content_aggregate_contracts.py#L377)|testuserの追加と集合membershipを、remove前の状態として保持|
|[B24 test_remove_mention_functionality](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L364-L376)|R|[test_content_aggregate_contracts.py::test_public_mention_changes_preserve_other_entries](../../tests/domain/sns/test_content_aggregate_contracts.py#L377)|公開removeの独立契約。追加→確認→削除を保持し他要素の維持も観測する|
|[B25 test_get_mentioned_users](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L378-L392)|C|[test_content_aggregate_contracts.py::test_public_mention_changes_preserve_other_entries](../../tests/domain/sns/test_content_aggregate_contracts.py#L377)|user1/user2を公開追加して得る集合の厳密一致を保持。生成抽出の試験で代替しない|
|[B26 test_create_mentions_from_content](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L394-L407)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|元本文@user1 @user2 こんにちは #testを保持|
|[B27 test_create_mentions_from_content_no_mentions](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L409-L420)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|元本文メンションなしの投稿 #testと件数0を保持|
|[B28 test_event_emission_on_like](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L422-L444)|C|[test_content_aggregate_contracts.py::test_like_toggle_preserves_actor_state_and_event_prefix](../../tests/domain/sns/test_content_aggregate_contracts.py#L240)|@testuserの既存2イベント→3を必ず保持。空イベント列だけの保持先では不可|
|[B29 test_event_emission_on_delete](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L446-L465)|C|[test_content_aggregate_contracts.py::test_delete_preserves_existing_state_and_event_prefix](../../tests/domain/sns/test_content_aggregate_contracts.py#L296)|元1イベントから1追加と最終種類を保持。非空prefix一致も追加|
|[B30 test_create_from_db_post_aggregate](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L467-L486)|C|[test_content_aggregate_contracts.py::test_restore_preserves_saved_state_without_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L193)|空集合からの復元行を維持。新規生成行と混同しない|
|[B31 test_create_from_db_reply_aggregate](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L488-L508)|C|[test_content_aggregate_contracts.py::test_restore_preserves_saved_state_without_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L193)|投稿親付き返信の空集合復元行を維持|
|[B32 test_boundary_values_likes_and_mentions](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L510-L530)|F|[test_content_aggregate_contracts.py::test_like_toggle_preserves_actor_state_and_event_prefix](../../tests/domain/sns/test_content_aggregate_contracts.py#L240)<br>[test_content_aggregate_contracts.py::test_public_mention_changes_preserve_other_entries](../../tests/domain/sns/test_content_aggregate_contracts.py#L377)|private集合直接注入を公開like_post/add_mentionへ修理。元の空→1、Like(UserId(2),PostId(1))とMention(testuser,PostId(1))のmembershipを対応観測へ分配する。入力aliasの変更試験は追加しない|
|[B33 test_content_validation_error_propagation](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L532-L545)|C|[test_post_content.py::TestPostContent::test_content_too_long_raises_error](../../tests/domain/sns/test_post_content.py#L37)<br>[test_post_content.py::TestPostContent::test_aggregate_origin_hashtag_rejections](../../tests/domain/sns/test_post_content.py#L181)|集約未到達。a*281、listの[#tag]*11をPostContent保持先へ先に移す|
|[B34 test_mention_validation_error_propagation](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L547-L553)|C|[test_mention.py::TestMention::test_empty_mentioned_user_name_raises_error](../../tests/domain/sns/test_mention.py#L25)|集約未到達。Mention空文字/PostId(1)/専用例外は既存値保持先と同一|
|[B35 test_like_with_deleted_content](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L555-L569)|R|[test_content_aggregate_contracts.py::test_deleted_post_still_accepts_like](../../tests/domain/sns/test_content_aggregate_contracts.py#L365)|削除後でも直接like可能という現在契約。認可層と混同して削除しない。製品仕様変更は別承認|
|[B36 test_delete_with_invalid_content_type_reply](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L571-L580)|C|[test_content_aggregate_contracts.py::test_rejected_content_operation_preserves_state_and_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L332)|返信deleteのinvalid_type行として投稿と別の元入力を保持|
|[B37 test_reply_creation_with_both_parents_raises_error](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L582-L591)|F|[test_content_aggregate_contracts.py::test_creation_rejects_invalid_reply_parents](../../tests/domain/sns/test_content_aggregate_contracts.py#L409)|pytest.raises(Exception)は無関係な例外も成功になる。元両親入力を保ちInvalidParentReferenceExceptionへ限定|
|[B38 test_reply_creation_without_parent_raises_error](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_base_sns_aggregate.py#L593-L600)|F|[test_content_aggregate_contracts.py::test_creation_rejects_invalid_reply_parents](../../tests/domain/sns/test_content_aggregate_contracts.py#L409)|pytest.raises(Exception)を専用例外へ限定。None,None,Noneの元入力を保持|
|[P01 test_constructor_success](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L23-L40)|C|[test_content_aggregate_contracts.py::test_constructor_preserves_supplied_state](../../tests/domain/sns/test_content_aggregate_contracts.py#L163)|直接コンストラクタとcreateは別入口。空likes/mentionsと両親Noneを維持|
|[P02 test_constructor_with_parent_references_raises_error](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L42-L50)|R|[test_post_aggregate.py::TestPostAggregate::test_constructor_with_parent_references_raises_error](../../tests/domain/sns/test_post_aggregate.py#L18)|PostId(2)親を持つ投稿の拒否・専用例外・診断を保持。親返信拒否の行は追加候補|
|[P03 test_create_method_success](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L52-L71)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|元本文@user1 @user2 テスト投稿と全プロパティを保持|
|[P04 test_create_from_db_method](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L73-L92)|F|[test_content_aggregate_contracts.py::test_restore_preserves_saved_state_without_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L193)|非空Like/Mentionを保持。deleted=True/明示時刻/UUID/作者束縛/無発行を別行で追加し復元引数脱落を検出|
|[P05 test_properties](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L94-L113)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|post_id/post_contentの別名と空初期集合を保持|
|[P06 test_get_content_type](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L115-L122)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|投稿種別を共有生成契約へ移す|
|[P07 test_get_parent_info](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L124-L133)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|投稿の親情報二つがNoneの厳密期待を移す|
|[P08 test_mentioned_users](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L135-L143)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|mentioned_users()公開別名の呼出しを消さず、共通抽出行でget_mentioned_usersと双方確認|
|[P09 test_like_post_functionality](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L145-L162)|C|[test_content_aggregate_contracts.py::test_like_toggle_preserves_actor_state_and_event_prefix](../../tests/domain/sns/test_content_aggregate_contracts.py#L240)|UserId(2)の二回切替と件数を共通保持先へ|
|[P10 test_like_post_multiple_users](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L164-L188)|C|[test_content_aggregate_contracts.py::test_like_toggle_preserves_other_users](../../tests/domain/sns/test_content_aggregate_contracts.py#L262)|2/3/4の非空集合と3だけ解除を共通保持先へ|
|[P11 test_delete_post_functionality](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L190-L199)|C|[test_content_aggregate_contracts.py::test_delete_preserves_existing_state_and_event_prefix](../../tests/domain/sns/test_content_aggregate_contracts.py#L296)|作者削除状態を共通保持先へ|
|[P12 test_delete_post_unauthorized_user_raises_error](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L201-L211)|C|[test_content_aggregate_contracts.py::test_rejected_content_operation_preserves_state_and_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L332)|OwnershipExceptionと元日本語診断を共通拒否保持先へ|
|[P13 test_create_mentions_from_content_static](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L213-L226)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|私有static直接呼出しを公開createへ。二つの名前だけでなく各Mention.post_id==PostId(1)も移す|
|[P14 test_create_mentions_from_content_static_no_mentions](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L228-L235)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|メンションなしの投稿 #hashtagを公開create行へ|
|[P15 test_create_mentions_from_content_static_edge_cases](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L237-L256)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|@@user1→@user1、@user1!→user1!、複数空白の3入力を一つも落とさず公開createへ|
|[P16 test_content_validation_error_propagation](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L258-L271)|C|[test_post_content.py::TestPostContent::test_content_too_long_raises_error](../../tests/domain/sns/test_post_content.py#L37)<br>[test_post_content.py::TestPostContent::test_aggregate_origin_hashtag_rejections](../../tests/domain/sns/test_post_content.py#L181)|集約未到達。a*281とtuple([#tag]*11)を値型の保持先へ移す|
|[P17 test_boundary_values_content_length](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L273-L286)|C|[test_content_aggregate_contracts.py::test_creation_preserves_boundary_content](../../tests/domain/sns/test_content_aggregate_contracts.py#L400)<br>[test_post_content.py::TestPostContent::test_content_too_long_raises_error](../../tests/domain/sns/test_post_content.py#L37)|a*280の受理/本文厳密一致とa*281専用拒否。生成への本文保持はcreate契約も残す。成功側は同じ入力を集約createまで通す別の境界行を保持し、値型だけへ退避しない|
|[P18 test_boundary_values_hashtags](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L288-L301)|C|[test_content_aggregate_contracts.py::test_creation_preserves_boundary_content](../../tests/domain/sns/test_content_aggregate_contracts.py#L400)<br>[test_post_content.py::TestPostContent::test_aggregate_origin_hashtag_rejections](../../tests/domain/sns/test_post_content.py#L181)|重複#tag10個を10のまま保持、11個拒否。既存の相異なるタグ10/11行だけでは代替不可。成功側は同じ入力を集約createまで通す別の境界行を保持し、値型だけへ退避しない|
|[P19 test_event_emission_on_creation](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L303-L321)|F|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|作成→メンションの2件と順序を残す。名前文字列照合を型/対象/作者/内容の観測へ強化|
|[P20 test_event_emission_on_like](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L323-L342)|C|[test_content_aggregate_contracts.py::test_like_toggle_preserves_actor_state_and_event_prefix](../../tests/domain/sns/test_content_aggregate_contracts.py#L240)|メンションなし投稿の既存1件から一件追加を共有保持先へ|
|[P21 test_event_emission_on_delete](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L344-L363)|C|[test_content_aggregate_contracts.py::test_delete_preserves_existing_state_and_event_prefix](../../tests/domain/sns/test_content_aggregate_contracts.py#L296)|メンションなし投稿の既存一件から削除一件追加を共有保持先へ|
|[P22 test_full_workflow](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L365-L394)|C|[test_content_aggregate_contracts.py::test_post_workflow_keeps_every_intermediate_state](../../tests/domain/sns/test_content_aggregate_contracts.py#L275)|2と3の追加→2解除→作者削除の複合順序と全途中状態を共有行へ。単純最終値だけへ縮めない|
|[P23 test_invalid_post_id_creation](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L396-L402)|D|[test_post_id.py::TestPostId::test_invalid_post_id_zero_raises_error](../../tests/domain/sns/test_post_id.py#L16)<br>[test_post_id.py::TestPostId::test_error_message_contains_value](../../tests/domain/sns/test_post_id.py#L97)|0と-1はtest_invalid_post_id_zero_raises_error/test_error_message_contains_valueが同じ例外・入力を保持。集約を呼ばない|
|[P24 test_invalid_user_id_creation](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L404-L410)|D|[test_user_id.py::TestUserId::test_invalid_user_id_zero_raises_error](../../tests/domain/sns/test_user_id.py#L16)<br>[test_user_id.py::TestUserId::test_error_message_contains_value](../../tests/domain/sns/test_user_id.py#L97)|0と-1はtest_invalid_user_id_zero_raises_error/test_error_message_contains_valueが同じ例外・入力を保持。集約を呼ばない|
|[P25 test_likes_and_mentions_immutability](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L412-L428)|R|[test_content_aggregate_contracts.py::test_collection_getters_do_not_expose_owned_state](../../tests/domain/sns/test_content_aggregate_contracts.py#L229)|取得setへのdummy追加と内部空集合維持。#1456の入力clearとは別契約、統合して消さない|
|[P26 test_delete_with_likes](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L430-L448)|R|[test_content_aggregate_contracts.py::test_delete_preserves_existing_state_and_event_prefix](../../tests/domain/sns/test_content_aggregate_contracts.py#L296)|非空いいねが削除後も残る独立契約。共通削除所有者へ移動可|
|[P27 test_reply_ids_management](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L450-L492)|R|[test_post_aggregate.py::TestPostAggregate::test_reply_ids_management](../../tests/domain/sns/test_post_aggregate.py#L28)|0→1→2、重複追加、1件除去、999不存在除去の全途中状態を保持|
|[P28 test_reply_ids_immutability](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L494-L508)|R|[test_content_aggregate_contracts.py::test_collection_getters_do_not_expose_owned_state](../../tests/domain/sns/test_content_aggregate_contracts.py#L229)|reply_ids取得結果へのReplyId(1)追加が内部へ漏れない独立契約|
|[P29 test_get_display_info](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_post_aggregate.py#L510-L537)|F|[test_post_aggregate.py::test_get_display_info_preserves_saved_fields](../../tests/domain/sns/test_post_aggregate.py#L94)|元11キー期待を維持。liked viewer/未liked viewer、削除後、created_at明示値を追加し固定False実装を区別|
|[R01 test_constructor_with_parent_post_success](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L24-L43)|C|[test_content_aggregate_contracts.py::test_constructor_preserves_supplied_state](../../tests/domain/sns/test_content_aggregate_contracts.py#L163)|投稿親と空返信親を持つ直接構築の全期待を保持|
|[R02 test_constructor_with_parent_reply_success](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L45-L64)|C|[test_content_aggregate_contracts.py::test_constructor_preserves_supplied_state](../../tests/domain/sns/test_content_aggregate_contracts.py#L163)|返信親ReplyId(2)を持つ直接構築の全期待を保持|
|[R03 test_constructor_without_parent_raises_error](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L66-L73)|R|[test_reply_aggregate.py::TestReplyAggregate::test_constructor_without_parent_raises_error](../../tests/domain/sns/test_reply_aggregate.py#L13)|親なし拒否専用例外と日本語診断はprimaryのまま保持|
|[R04 test_constructor_with_both_parents_raises_error](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L75-L84)|R|[test_reply_aggregate.py::TestReplyAggregate::test_constructor_with_both_parents_raises_error](../../tests/domain/sns/test_reply_aggregate.py#L22)|二重親拒否を保持。Factoryの元入力も同じ保持先へ追加|
|[R05 test_constructor_with_invalid_reply_id_raises_error](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L86-L89)|D|[test_reply_id.py::TestReplyId::test_invalid_reply_id_zero_raises_error](../../tests/domain/sns/test_reply_id.py#L16)|ReplyId(0)構築が先に失敗しReplyAggregateは呼ばれない。数値ID保持先の同入力が検出する|
|[R06 test_constructor_with_invalid_post_id_raises_error](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L91-L94)|D|[test_post_id.py::TestPostId::test_invalid_post_id_zero_raises_error](../../tests/domain/sns/test_post_id.py#L16)<br>[test_post_id.py::TestPostId::test_error_message_contains_value](../../tests/domain/sns/test_post_id.py#L97)|PostId(0)構築が先に失敗する。数値ID保持先の同入力が検出する|
|[R07 test_constructor_with_invalid_user_id_raises_error](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L96-L99)|D|[test_user_id.py::TestUserId::test_invalid_user_id_zero_raises_error](../../tests/domain/sns/test_user_id.py#L16)<br>[test_user_id.py::TestUserId::test_error_message_contains_value](../../tests/domain/sns/test_user_id.py#L97)|UserId(0)構築が先に失敗する。数値ID保持先の同入力が検出する|
|[R08 test_create_with_parent_post_success](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L101-L121)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|@user1 @user2 テスト返信・投稿親・作者を保持|
|[R09 test_create_with_parent_reply_success](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L123-L137)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|返信親と親作者UserId(2)を持つcreateの元全期待を保持|
|[R10 test_create_from_db_method](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L139-L160)|F|[test_content_aggregate_contracts.py::test_restore_preserves_saved_state_without_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L193)|元入力がLike/Mentionの対象PostId(1)で集約ReplyId(1)と型不整合。黙って直して元条件を消さず既存受入れ行として分離。正しいReplyId行を追加し時刻/UUID/親作者束縛も保持|
|[R11 test_reply_specific_properties](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L162-L174)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|reply_id/content_id、reply種別と投稿親tupleを共有保持先へ|
|[R12 test_get_parent_info_with_parent_reply](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L176-L184)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|返信親tupleの厳密一致を共有保持先へ|
|[R13 test_like_reply_functionality](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L186-L204)|C|[test_content_aggregate_contracts.py::test_like_toggle_preserves_actor_state_and_event_prefix](../../tests/domain/sns/test_content_aggregate_contracts.py#L240)|返信UserId(2)の二回切替と1→0を共通保持先へ|
|[R14 test_like_reply_multiple_users](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L206-L231)|C|[test_content_aggregate_contracts.py::test_like_toggle_preserves_other_users](../../tests/domain/sns/test_content_aggregate_contracts.py#L262)|返信の2/3/4追加→3解除と全途中状態を保持|
|[R15 test_delete_reply_by_owner](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L233-L242)|C|[test_content_aggregate_contracts.py::test_delete_preserves_existing_state_and_event_prefix](../../tests/domain/sns/test_content_aggregate_contracts.py#L296)|返信作者による削除成功を共有保持先へ|
|[R16 test_delete_reply_by_non_owner_raises_error](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L244-L255)|F|[test_content_aggregate_contracts.py::test_rejected_content_operation_preserves_state_and_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L332)|非作者UserId(2)専用例外を維持し非空状態と既存イベント保持を追加|
|[R17 test_mention_extraction_from_content](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L257-L269)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|元本文@user1 @user2 こんにちは！ #testを保持|
|[R18 test_mention_with_no_mentions](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L271-L281)|C|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|メンションなしの返信を保持|
|[R19 test_mention_with_special_characters](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L283-L296)|R|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|user_name/user-name/user.nameを全て保持する固有入力。公開createの表へ移動のみ可|
|[R20 test_content_validation_max_length](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L298-L310)|C|[test_content_aggregate_contracts.py::test_creation_preserves_boundary_content](../../tests/domain/sns/test_content_aggregate_contracts.py#L400)|日本語あ*280の受理と本文の厳密一致を保持。ASCII280だけで代替しない。成功側は同じ入力を集約createまで通す別の境界行を保持し、値型だけへ退避しない|
|[R21 test_content_validation_over_max_length](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L312-L322)|C|[test_post_content.py::TestPostContent::test_aggregate_origin_length_rejections](../../tests/domain/sns/test_post_content.py#L171)|日本語あ*281専用拒否を値型の表へ移す。集約は未到達|
|[R22 test_content_validation_max_hashtags](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L324-L335)|C|[test_content_aggregate_contracts.py::test_creation_preserves_boundary_content](../../tests/domain/sns/test_content_aggregate_contracts.py#L400)|接頭#なしtag0..tag9のtuple全保持を値型の表へ移す。成功側は同じ入力を集約createまで通す別の境界行を保持し、値型だけへ退避しない|
|[R23 test_content_validation_over_max_hashtags](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L337-L343)|C|[test_post_content.py::TestPostContent::test_aggregate_origin_hashtag_rejections](../../tests/domain/sns/test_post_content.py#L181)|接頭#なしtag0..tag10の11個拒否を保持。集約未到達|
|[R24 test_parent_info_with_both_none_should_never_happen](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L345-L356)|D|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|同じ投稿親生成入力でor存在だけを再確認。test_reply_specific_propertiesの厳密tuple==(PostId(1),None)が強い証明|
|[R25 test_event_emission_on_creation](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L358-L374)|F|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|len>=2では余剰発火を見逃す。正確な2件・順序・種類・親作者/親ID・内容を観測し元aggregate_id/typeも保持|
|[R26 test_like_event_emission](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L376-L390)|F|[test_content_aggregate_contracts.py::test_like_toggle_preserves_actor_state_and_event_prefix](../../tests/domain/sns/test_content_aggregate_contracts.py#L240)|content_type==replyだけで種類を同定しない。現fixture作成イベントにはその属性がないので常時通過ではないが、誤種類/重複には弱い。型と正確な追加一件と全payloadへ|
|[R27 test_delete_event_emission](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L392-L405)|F|[test_content_aggregate_contracts.py::test_delete_preserves_existing_state_and_event_prefix](../../tests/domain/sns/test_content_aggregate_contracts.py#L296)|現fixtureに既存replyラベルeventはないので完全な無検証ではない。誤種類・重複を識別する型/差分件数/対象/作者へ強化|
|[R28 test_mention_event_emission](https://github.com/Motifman/llm-rpg/blob/7c7dc63c5f4be701832a3f1443e27682fe9869d1/tests/domain/sns/test_reply_aggregate.py#L407-L420)|F|[test_content_aggregate_contracts.py::test_creation_preserves_fields_mentions_and_ordered_events](../../tests/domain/sns/test_content_aggregate_contracts.py#L110)|hasattrだけでなくSnsContentMentionedEvent型・単一件数・名前集合・対象・作者を観測|

## 保持した原入力と修理

- PostId/ReplyIdを分け、内容ReplyId(2)と親ReplyId(1)を含む全親組合せを保持する
- ASCII/日本語280文字、重複`#tag`10個、接頭`#`なし10タグは集約createで観測する。ASCII/日本語281、重複11個のlist/tuple、接頭辞なし11個tupleの専用例外も保持する
- `@@user1`、`@user1!`、複数空白、全ての元本文と各Mentionの型付き対象IDを公開createで観測する
- 2/3/4人目の追加と3だけ解除、2/3追加後2解除から作者削除までの全途中状態を残す
- 削除後like受理、Postで種別reply、Replyで種別postの直接like受理は元の正の契約を維持する
- 空集合復元と旧PostId混在返信を別行で残す。固定時刻と相互に異なる対象/作者/親/実行者UUIDの強化行で原入力を置き換えない
- 拒否前の集合は値へコピーし、イベント列は内部集合や出典と参照を共有しない独立コピーを作る。元の1件/2件からの正確な追加数・順序・実型・内容も観測する
- Post表示は元11キーを保持。製品辞書の12番目であるcreated_atと、いいねした閲覧者・削除後は追加強化として扱う

## 別保留の所有権契約

[#1456](https://github.com/Motifman/llm-rpg/pull/1456) の構築入力copy修正は移植しない。新所有権1宣言4条件は内容集約の元95外として別保留にする。利用者の新2宣言6条件も別群。入力のclearが集約へ漏れる現挙動を正しい期待値へ反転しない。既存getter copyの証明と構築入力copyの追加回帰は互いの代替ではない。

UUIDの保存、作者/親束縛、実サービスのイベント出典、配送と認可は、それぞれ既存の別所有者を不変に保持する。`test_sns_identity_persistence.py`、`test_sns_reference_bindings.py`、`test_existing_command_emitters_supply_identity_and_source_metadata`、`test_actual_domain_event_cannot_rebind_reused_identifiers`を集約試験で置換しない。

## 履歴の確認

[822a5b6](https://github.com/Motifman/llm-rpg/commit/822a5b69418a37537a93702f4cfdbfc262568cd3)で3集約試験が追加され、子返信や型の変化に追従していた。[ee357d0](https://github.com/Motifman/llm-rpg/commit/ee357d06f09bfaf63f982d1490c33a0c6bdd089e)では復元factoryの誤委譲を既存試験が検知しているため、直接構築・公開create・保存からの復元は異なる入口として残した。

## 実行した証拠

- 編集前: 元95件、既存値型保持先75件成功
- 旧95をbyte不変で残した先行受入: 180件成功。余分に追加したASCII281の重複は取り除き、親の既存同入力試験を保持先とした
- 106種の同じ製品退行を旧95条件と新77条件で対照、計212実行。双方が検知78種、旧が見逃し新が検知28種。新側77は最終対象に対応する70条件と、既存ASCII/ID/Mention保持先7条件を含む
- 元95全宣言それぞれに、同一退行を元宣言と名指した保持先が検知する対応がある。宣言単位の照合だけでなく元310観測と原入力も独立に審査した
- 各制御変異後に変更した製品bytesを復元。候補と変異用の両作業ツリーで全製品1587ファイルが親blobと一致
- 投稿固有3関数は先行受入後にPostファイルへ移した。うち2関数のASTは同一、作成時刻の関数は同じPostAggregate.create入力を補助呼出しから直接記述へ展開
- 関連基準1091件は、同じ固定親で利用者集約監査が実行した未編集の結果を再利用。12選択・nodeid・製品/試験/設定3157blobと元のJSON/XML/log/hashを照合した。今回の作業ツリーで再実行した基準ではない。初回の誤指定rc4結果は除外
- 最終対象70件、同じ関連12選択1066件成功。今回の作業ツリー自身のsrcで実行。関連の変更のない996nodeidは基準と最終で一致し全て成功
- 変更4試験ファイルのruff 0.16.8とgit diff --check成功

Python3.10.22・固定依存・実行作業ツリー自身のsrc・通信遮断・認証環境変数除去を使用。実LLM、有償API、SNS本番接続は行っていない。全リポジトリ試験をローカルで通したとは扱わず、公開した正確なheadのCIを別途確認する。

### 106種の旧新対照

数字は各退行で失敗した試験条件数。0はその側が退行を見逃したことを示す。制御変異のため、失敗は期待した検出結果である。

|番号|退行|旧95|新77|
|---|---|---:|---:|
|1|content-id-kind|16|28|
|2|content-id-value|17|29|
|3|author-id|28|43|
|4|content-field|21|34|
|5|post-parent-field|9|10|
|6|reply-parent-field|4|4|
|7|initial-deleted|28|33|
|8|restore-deleted|0|3|
|9|restore-likes|2|5|
|10|restore-mentions|13|18|
|11|restore-created-at|0|5|
|12|restore-token|0|5|
|13|restore-author-token|0|5|
|14|restore-parent-token|0|3|
|15|swap-author-parent-token|0|5|
|16|likes-getter-alias|2|1|
|17|mentions-getter-alias|1|1|
|18|replyids-getter-alias|1|1|
|19|post-id-alias|3|11|
|20|post-content-alias|4|12|
|21|reply-id-alias|2|8|
|22|post-content-type|2|17|
|23|reply-content-type|2|12|
|24|post-parent-projection|2|10|
|25|reply-parent-projection|4|8|
|26|mentioned-users-projection|12|14|
|27|post-extract-empty|8|9|
|28|reply-extract-empty|5|4|
|29|post-extract-double-at|1|1|
|30|post-extract-punctuation|1|1|
|31|post-extract-spaces|1|1|
|32|post-mention-target|1|7|
|33|reply-mention-target|0|4|
|34|mention-add-noop|3|8|
|35|mention-remove-noop|1|1|
|36|mention-remove-all|0|1|
|37|like-toggle-noop|7|8|
|38|like-toggle-clear-all|4|3|
|39|like-wrong-actor-state|11|11|
|40|like-event-missing|3|16|
|41|like-event-target|0|8|
|42|like-event-author|0|8|
|43|like-event-actor|0|8|
|44|like-event-double|2|14|
|45|like-event-prefix-overwritten|0|4|
|46|reply-like-event-wrong-kind|0|3|
|47|like-actor-identity-token|0|2|
|48|like-recipient-identity-token|0|2|
|49|like-target-identity-token|0|2|
|50|like-execution-provenance|0|2|
|51|like-swap-actor-recipient|0|2|
|52|like-unlike-event-state|0|5|
|53|like-display-name|0|2|
|54|like-invalid-kind|1|1|
|55|delete-invalid-kind|2|2|
|56|delete-nonowner|3|2|
|57|delete-already|2|2|
|58|delete-state|8|8|
|59|delete-likes|1|4|
|60|delete-event-missing|3|5|
|61|delete-event-double|2|5|
|62|delete-event-prefix-overwritten|0|3|
|63|delete-event-wrong-kind|0|1|
|64|refusal-clears-likes|0|2|
|65|refusal-clears-mentions|0|2|
|66|refusal-clears-reply_ids|0|2|
|67|refusal-clears-events|0|2|
|68|like-cross-kind-refused|2|2|
|69|deleted-like-refused|1|1|
|70|post-parent-allowed|1|1|
|71|reply-no-parent-allowed|2|2|
|72|reply-both-parent-allowed|2|2|
|73|reply-parent-generic-error|2|4|
|74|post-truncate280|1|1|
|75|reply-truncate280|1|1|
|76|post-deduplicate-tags|1|1|
|77|reply-drop-unprefixed-tags|1|1|
|78|private-always-false|1|1|
|79|private-followers-true|1|1|
|80|sort-current-time|1|1|
|81|reply-add-noop|2|6|
|82|reply-remove-all|1|1|
|83|reply-remove-missing-error|1|1|
|84|reply-count-wrong|2|2|
|85|display-content|1|1|
|86|display-hashtags|1|1|
|87|display-like_count|1|1|
|88|display-reply_count|1|1|
|89|display-is_deleted|1|1|
|90|display-viewer-false|0|1|
|91|display-created-current|0|1|
|92|ascii281-accepted|3|1|
|93|japanese281-accepted|1|1|
|94|duplicate-list11-accepted|1|1|
|95|duplicate-tuple11-accepted|2|1|
|96|unprefixed-tuple11-accepted|1|1|
|97|empty-mention-accepted|1|1|
|98|postid-zero-accepted|2|1|
|99|postid-negative-accepted|1|1|
|100|replyid-zero-accepted|1|1|
|101|userid-zero-accepted|2|1|
|102|userid-negative-accepted|1|1|
|103|likes-getter-drops-state|12|20|
|104|mentions-getter-drops-state|5|24|
|105|post-phantom-mention|9|13|
|106|reply-phantom-mention|3|9|
