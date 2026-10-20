# SNS投稿側の値契約49宣言の監査

対象はPostContent、Like、Mention、NotificationTypeの4試験。数値IDの監査（親PR #1774）、SNS集約、ユーザー側の値契約、配送権限を再度数えない。製品コードと共有補助の変更はない。

## 基準と件数

- 変更前は親commit [`595065d2d35f3bcb8f6a93ecc5259a5c7252599e`](https://github.com/Motifman/llm-rpg/commit/595065d2d35f3bcb8f6a93ecc5259a5c7252599e)。完全tree `6cebbad5e2aee251cb404735668c477b2414e300` の全3459 leafのmodeとGit blobを照合して実行した
- 元49宣言はR24（保持）/F9（検査修理）/C10（条件を先に移管して統合）/D6（重複等を削除）。元のassert/raisesは114観測点。不変性3宣言は構築だけで観測点がなかった
- 変更前49件成功。旧C/D宣言を残した保持先の先行受入は68件成功。最終は33宣言・52実行条件が成功
- 関連試験は変更前886件、変更後889件が成功。各件数は対象49/52件を含む。変更していない関連837件も成功し、別々の実行結果を足して水増ししない
- 試験は544行から444行へ100行減（149行追加、249行削除）。この監査文書の追加行は試験削減に含めない
- 制御変異39種、旧新対照78実行。修理10種は旧側が見逃し、新側で検知。保持27種は双方で検知。合法なhash衝突と生成repr変更の2対照は旧側だけが失敗
- 各変異の旧52件/新55件は、元の対象49件/保持側52件に既存ID拒否の保持先3件を加えた数。これを原母集団に追加しない
- Python 3.10.22、既存固定依存、外部接続を遮断した安全実行器を使用。対象作業木のsrcを読み、出力名・一時領域・キャッシュを分離した
- 各変異後に変更製品のbytesを復元・照合し、最後に全製品1587ファイルの一致も確認。ruff 0.16.8の変更4試験検査とgit diff --checkは成功

最終関連範囲は`tests/domain/sns`、`tests/application/social`、`tests/infrastructure/repository/test_public_sns_snapshot_codec.py`、`test_sqlite_sns_repositories.py`、`test_sqlite_sns_notification_repository.py`。全リポジトリの試験と、公開された正確なcommitのCIは、このローカル検証とは別の確認事項である。

## 所有する契約と呼出元

- PostContentは公開`PublicSnsCommandService.publish`、旧投稿/返信サービス、SQLiteの投稿/返信復元から使われる。値型の空本文受容と公開publishの空本文拒否、直接構築とcreateの既定値を混同しない
- Likeは`BaseSnsContentAggregate.like/is_liked_by_user`で新しい同値を作って既存集合を検索・除去する。作成時刻を等価性/hashに含めない。SQLiteは明示時刻を復元する
- MentionはPost/Reply両集約の集合とSQLite復元で使われる。表示名と型付き対象IDを区別し、追加/除去できる必要がある。通知の宛先解決規則を値型へ押し込まない
- NotificationTypeはSQLite、公開SNSのJSON復元、通知dispatcherが`NotificationType(value)`を使う。6保存文字列、独自str変換、復元、現在の6種集合は独立した契約として保持する

Like/Mentionの生成repr断片には、履歴・現在の呼出元から独立した表示形式の約束・消費経路を確認できなかった。保存処理はフィールドを直接読むが、保存試験が同じreprを代替すると主張して削除したわけではない。小さいgetterや生成コードであることだけを削除理由にしない。

## 履歴を踏まえた判断

- [`d25af32`](https://github.com/Motifman/llm-rpg/commit/d25af3295dd67160d1a68105558ff902a5386b4c): 値型の包括的試験を追加し、PostContentのタグ注釈/既定をtupleへ変更。空の不変性試験もここから存在していた
- [`822a5b6`](https://github.com/Motifman/llm-rpg/commit/822a5b69418a37537a93702f4cfdbfc262568cd3): 型付きIDへ移行。旧Like/Mention自体の無効整数試験は、値型へ到達しないID構築だけの試験に変わった。Likeの異時刻比較は非等価から等価へ、Mention(None)は拒否から受容へ明示変更された
- [`65fabcb`](https://github.com/Motifman/llm-rpg/commit/65fabcb14f2e94fb4f87f8d56ac362024b259cc7): PostContent.createの4条件とNotificationTypeの6宣言を追加。直接構築とfactoryの契約を一律にまとめない
- [`ee357d0`](https://github.com/Motifman/llm-rpg/commit/ee357d06f09bfaf63f982d1490c33a0c6bdd089e): MentionのPostId/ReplyId受容を型へ明示。型付き対象を整数だけに潰す比較へ戻さない

## 元49宣言の全台帳

元宣言のリンクは上記親commitに固定した。保持先はこの変更後の試験を示す。M番号は後述の旧新対照。各行の対応番号は統合・修理後の保持先が検知した証拠を含み、元宣言自身が検知したことを一律に示すものではない。変異なしと記したRは対象/関連試験を実行したが、その宣言専用の追加変異までは行っていない。

### PostContent（元14宣言）

- **R** [`test_create_post_content_success`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_post_content.py#L17-L27): 明示した本文・タグ・公開範囲を保持する。現行のlist入力の受容も含む。構築時の本文消失、タグ無視、指定公開範囲の上書き。
  - 保持先・処理: tests/domain/sns/test_post_content.py::TestPostContent::test_create_post_content_success。現契約を保持する
  - 変異: M28
- **R** [`test_create_post_content_with_defaults`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_post_content.py#L29-L37): 本文だけの直接構築は空tupleのタグとPUBLICを既定値にする。直接構築の既定公開範囲やタグ型の変更。
  - 保持先・処理: tests/domain/sns/test_post_content.py::TestPostContent::test_create_post_content_with_defaults。現契約を保持する
  - 変異: この宣言専用の追加変異なし。対象と関連範囲の成功を確認
- **R** [`test_content_too_long_raises_error`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_post_content.py#L39-L44): 281文字をContentLengthValidationExceptionと上限を含む説明で拒む。最大長の撤去・281への境界ずれ・別例外への置換。
  - 保持先・処理: tests/domain/sns/test_post_content.py::TestPostContent::test_content_too_long_raises_error。現契約を保持する
  - 変異: この宣言専用の追加変異なし。対象と関連範囲の成功を確認
- **R** [`test_hashtags_too_many_raises_error`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_post_content.py#L46-L51): 11タグをHashtagCountValidationExceptionで拒む。タグ上限の撤去・境界ずれ。
  - 保持先・処理: tests/domain/sns/test_post_content.py::TestPostContent::test_hashtags_too_many_raises_error。現契約を保持する
  - 変異: 当該検証専用の追加変異なし。M28の別例外による失敗はlist入力互換性だけを確認し、タグ上限・可視性ガードそのものの保存証拠には数えない
- **R** [`test_invalid_visibility_raises_error`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_post_content.py#L53-L56): PostVisibilityでない指定をVisibilityValidationExceptionで拒む。任意文字列を可視性として受容する。
  - 保持先・処理: tests/domain/sns/test_post_content.py::TestPostContent::test_invalid_visibility_raises_error。現契約を保持する
  - 変異: 当該検証専用の追加変異なし。M28の別例外による失敗はlist入力互換性だけを確認し、タグ上限・可視性ガードそのものの保存証拠には数えない
- **F** [`test_immutability_after_creation`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_post_content.py#L58-L61): 構築後に公開属性を再代入できない。現行は構築だけで不変性を観測しない。frozen解除を見逃す。
  - 保持先・処理: tests/domain/sns/test_post_content.py::TestPostContent::test_immutability_after_creation。tuple入力でcontent/hashtags/visibilityへの通常代入拒否と元値維持を観測する。listの深い不変性は別の製品候補SV114-P1とし無断変更しない
  - 変異: M01
- **R** [`test_equality_comparison`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_post_content.py#L66-L77): 同じ本文・タグ・公開範囲は別個体でも等しく同じhash。同値を個体同一性で比較、同値のhash不一致。
  - 保持先・処理: tests/domain/sns/test_post_content.py::TestPostContent::test_equality_comparison。現契約を保持する
  - 変異: M17
- **F** [`test_inequality_comparison`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_post_content.py#L79-L85): 本文・タグ・公開範囲が等価性を構成する。現行は3項目同時変更なので1項目を比較から落としても通る。異値hash不等は過剰制約。
  - 保持先・処理: tests/domain/sns/test_post_content.py::TestPostContent::test_inequality_comparison。各項目だけを変更する条件へ分け、非等価と集合で共存することを確認。hash不等要求は外す
  - 変異: M04, M05, M06
- **R** [`test_boundary_content_length`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_post_content.py#L87-L96): 空文字と280文字を値型では受容する。最小長を勝手に1へ変更、280を拒否。公開publishの空拒否とは別。
  - 保持先・処理: tests/domain/sns/test_post_content.py::TestPostContent::test_boundary_content_length。現契約を保持する
  - 変異: この宣言専用の追加変異なし。対象と関連範囲の成功を確認
- **R** [`test_boundary_hashtags_count`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_post_content.py#L98-L107): タグ0個と10個を受容する。タグ必須化・最大10個の拒否。
  - 保持先・処理: tests/domain/sns/test_post_content.py::TestPostContent::test_boundary_hashtags_count。現契約を保持する
  - 変異: この宣言専用の追加変異なし。対象と関連範囲の成功を確認
- **R** [`test_create_method_with_hashtag_extraction`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_post_content.py#L109-L118): 公開createが本文順のタグを抽出し本文と指定公開範囲を保持。抽出停止・順序変更・先頭#混入。
  - 保持先・処理: tests/domain/sns/test_post_content.py::TestPostContent::test_create_method_with_hashtag_extraction。現契約を保持する
  - 変異: この宣言専用の追加変異なし。対象と関連範囲の成功を確認
- **R** [`test_create_method_no_hashtags`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_post_content.py#L120-L129): タグなしcreateは空tupleで指定FOLLOWERS_ONLYを保持。空タグ生成・公開範囲をPUBLICへ固定。
  - 保持先・処理: tests/domain/sns/test_post_content.py::TestPostContent::test_create_method_no_hashtags。現契約を保持する
  - 変異: この宣言専用の追加変異なし。対象と関連範囲の成功を確認
- **R** [`test_create_method_special_hashtag_patterns`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_post_content.py#L131-L141): ハイフン/ドットで切り、underscore/数字を許し重複も順序通り残す。抽出を分割/重複除去して既存のタグ表現が変わる。
  - 保持先・処理: tests/domain/sns/test_post_content.py::TestPostContent::test_create_method_special_hashtag_patterns。現契約を保持する
  - 変異: M29
- **R** [`test_create_method_with_default_visibility`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_post_content.py#L143-L151): createの省略公開範囲はPUBLIC、タグ抽出も行う。直接構築とは別のfactory既定引数の変更。
  - 保持先・処理: tests/domain/sns/test_post_content.py::TestPostContent::test_create_method_with_default_visibility。現契約を保持する
  - 変異: M30

### Like（元15宣言）

- **R** [`test_create_like_success`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_like.py#L11-L19): 実行者と型付き対象を保持しcreated_atを省略時に生成。対象と実行者入替・日時なし。
  - 保持先・処理: tests/domain/sns/test_like.py::TestLike::test_create_like_success。現契約を保持する
  - 変異: M20, M21, M35, M36, M37, M38
- **R** [`test_create_like_with_explicit_datetime`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_like.py#L21-L30): 明示時刻を含め3入力を保持。保存復元時の時刻を現在時刻で上書き。
  - 保持先・処理: tests/domain/sns/test_like.py::TestLike::test_create_like_with_explicit_datetime。現契約を保持する
  - 変異: この宣言専用の追加変異なし。対象と関連範囲の成功を確認
- **D** [`test_invalid_user_id_raises_error`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_like.py#L32-L35): user IDの0拒否だけを実行しLikeに到達しない。ID型のガードだけを検知する重複。
  - 保持先・処理: tests/domain/sns/test_user_id.py::TestUserId::test_invalid_user_id_zero_raises_error。狭いドメイン例外を検査するID所有者の保持を確認し削除。SNS54には変更を加えない
  - 変異: M31
- **D** [`test_invalid_post_id_raises_error`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_like.py#L37-L40): post IDの0拒否だけを実行しLikeに到達しない。ID型のガードだけを検知する重複。
  - 保持先・処理: tests/domain/sns/test_post_id.py::TestPostId::test_invalid_post_id_zero_raises_error。狭いドメイン例外を検査するID所有者の保持を確認し削除。SNS54には変更を加えない
  - 変異: M32
- **C** [`test_boundary_id_values`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_like.py#L42-L56): 最小/大きい実行者IDと対象IDを保持。残す所有者に同じ条件がなければ喪失するため、先に移植を確認する。
  - 保持先・処理: tests/domain/sns/test_like.py::TestLike::test_create_like_success。1/999999の構築値を表に吸収し、入力保持を残す
  - 変異: M20, M21, M35, M36, M37, M38
- **F** [`test_hash_functionality`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_like.py#L58-L80): 同値の等価/hash一致と実行者/対象ごとの区別。片方のIDを比較から落とす退行。異値hash不等は合法な衝突まで拒む。
  - 保持先・処理: tests/domain/sns/test_like.py::TestLike::test_hash_functionality。等価・非等価の条件を残し、集合への重複排除/異値共存を観測。対象はPostId/ReplyId両方と同整数の別型を含める
  - 変異: M08, M11, M12, M18
- **R** [`test_hash_with_different_creation_times`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_like.py#L82-L94): 作成時刻が異なっても同じ実行者・対象のLikeは等しく同じhash。時刻をeq/hashへ戻し、後のいいね解除が失敗する。
  - 保持先・処理: tests/domain/sns/test_like.py::TestLike::test_hash_with_different_creation_times。現契約を保持する
  - 変異: M13, M14, M18
- **C** [`test_hash_with_same_creation_time`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_like.py#L96-L107): 同じ実行者・対象・明示時刻の別個体は等しく、hashも一致する。同値比較や同値hashの不一致を検知する。保持先に同じ条件が既にある。
  - 保持先・処理: tests/domain/sns/test_like.py::TestLike::test_hash_functionality。保持先の独立した条件へ先に対応付ける。異なる時刻の契約は別のR宣言を保持
  - 変異: M08, M11, M12, M18
- **F** [`test_immutability`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_like.py#L109-L113): 実行者・対象・時刻を構築後に再代入できない。空試験はfrozen解除を見逃し、集合内キー変更を許す。
  - 保持先・処理: tests/domain/sns/test_like.py::TestLike::test_immutability。各公開属性への通常代入拒否と元値維持を観測する
  - 変異: M02
- **C** [`test_equality_with_different_instances`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_like.py#L117-L126): 同じ実行者・対象・明示時刻の別個体は等しい。個体同一性だけの比較を検知する。元のこの宣言にはhash確認はない。
  - 保持先・処理: tests/domain/sns/test_like.py::TestLike::test_hash_functionality。保持先の独立した条件へ先に対応付ける。異なる時刻の契約は別のR宣言を保持
  - 変異: M08, M11, M12, M18
- **C** [`test_inequality_with_different_user_ids`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_like.py#L128-L136): 対象IDを保ったまま実行者IDだけが違うLikeは非等価。実行者を等価性から落とす退行を検知する。作成時刻は既定生成で固定していない。
  - 保持先・処理: tests/domain/sns/test_like.py::TestLike::test_hash_functionality。保持先の独立した条件へ先に対応付ける。異なる時刻の契約は別のR宣言を保持
  - 変異: M08, M11, M12, M18
- **C** [`test_inequality_with_different_post_ids`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_like.py#L138-L146): 実行者IDを保ったまま対象IDだけが違うLikeは非等価。対象を等価性から落とす退行を検知する。作成時刻は既定生成で固定していない。
  - 保持先・処理: tests/domain/sns/test_like.py::TestLike::test_hash_functionality。保持先の独立した条件へ先に対応付ける。異なる時刻の契約は別のR宣言を保持
  - 変異: M08, M11, M12, M18
- **D** [`test_string_representation`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_like.py#L148-L157): 生成reprのクラス名とIDの部分文字列。実装依存の生成reprだけを固定する。
  - 保持先・処理: 生成reprの独立契約・消費経路が見つからないため保持先不要。構築値/保存は別契約。公開属性/保存項目を残す。現行callersはLikeのreprを配送・保存に使わない
  - 変異: M39
- **F** [`test_created_at_auto_generation`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_like.py#L159-L168): 省略時刻は構築時に生成される。現在値から1秒未満という実行速度依存検査は負荷で誤失敗し得る。
  - 保持先・処理: tests/domain/sns/test_like.py::TestLike::test_created_at_auto_generation。構築直前/直後の時刻で挟む。import時の固定時刻や明示時刻無視を別条件で区別し、時刻注入用の製品入口は増やさない
  - 変異: M07
- **C** [`test_id_string_conversion`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_like.py#L170-L179): 実行者123と対象456の型付きID保持。残す所有者に同じ条件がなければ喪失するため、先に移植を確認する。
  - 保持先・処理: tests/domain/sns/test_like.py::TestLike::test_create_like_success。構築保持先のUserId(123)/PostId(456)行へ型付き保持と元str/int4観測を移管。期待値123/456と文字列123/456を独立に記述。ID所有者は編集しない
  - 変異: M20, M21, M35, M36, M37, M38

### Mention（元14宣言）

- **R** [`test_create_mention_success`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_mention.py#L10-L18): 表示名と型付きコンテンツIDを保持する。値の消失・対象IDの取り違え。
  - 保持先・処理: tests/domain/sns/test_mention.py::TestMention::test_create_mention_success。現契約を保持する
  - 変異: M22, M23
- **D** [`test_invalid_post_id_raises_error`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_mention.py#L20-L26): PostIdの0/-1拒否だけを実行しMentionに到達しない。PostId検証の退行を検知するが同じ入力を本来の所有者でより狭い例外型で検査済み。
  - 保持先・処理: tests/domain/sns/test_post_id.py::TestPostId::test_invalid_post_id_zero_raises_error / tests/domain/sns/test_post_id.py::TestPostId::test_error_message_contains_value。Mentionの固有検証と誤認しない。PostId試験の保持を確認して重複だけ削除
  - 変異: M32, M33
- **R** [`test_none_mentioned_user_name_handling`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_mention.py#L28-L33): 現行APIはNone名を受容してそのまま保持する。未合意のNone拒否導入。822a5b6で拒否から受容へ明示変更されている。
  - 保持先・処理: tests/domain/sns/test_mention.py::TestMention::test_none_mentioned_user_name_handling。現契約を保持する
  - 変異: M26
- **R** [`test_empty_mentioned_user_name_raises_error`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_mention.py#L35-L38): 空名をMentionValidationExceptionで拒む。空名ガード撤去・例外の退行。
  - 保持先・処理: tests/domain/sns/test_mention.py::TestMention::test_empty_mentioned_user_name_raises_error。現契約を保持する
  - 変異: M27
- **C** [`test_boundary_post_id_values`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_mention.py#L40-L50): 小さい/大きいPostIdをそのまま保持。残す所有者に同じ条件がなければ喪失するため、先に移植を確認する。
  - 保持先・処理: tests/domain/sns/test_mention.py::TestMention::test_create_mention_success。1/999999の入力保持条件を構築試験へ移す。正数範囲の検証はPostId所有者
  - 変異: M22, M23
- **R** [`test_various_mentioned_user_names`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_mention.py#L52-L68): 通常・50文字・underscore/ハイフン入りの名を無加工で受容。UserProfileと同じ長さ制限や文字制限を誤適用。
  - 保持先・処理: tests/domain/sns/test_mention.py::TestMention::test_various_mentioned_user_names。現契約を保持する
  - 変異: この宣言専用の追加変異なし。対象と関連範囲の成功を確認
- **R** [`test_equality_comparison`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_mention.py#L70-L80): 同じ表示名と型付き対象IDは別個体でも等しく同じhash。個体同一性の比較・同値hash不一致。
  - 保持先・処理: tests/domain/sns/test_mention.py::TestMention::test_equality_comparison。現契約を保持する
  - 変異: M19
- **F** [`test_inequality_with_different_mentioned_user_names`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_mention.py#L82-L89): 表示名だけ異なるMentionを区別する。表示名を等価性から落とす退行は検知するが異値hash不等は不要な制約。
  - 保持先・処理: tests/domain/sns/test_mention.py::TestMention::test_inequality_with_different_mentioned_user_names。非等価を保持し、異値hash不等を集合共存へ置換する。PostId/ReplyIdの同数値も別物として追加検討
  - 変異: M15
- **F** [`test_inequality_with_different_post_ids`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_mention.py#L91-L101): 対象IDだけ異なるMentionを区別する。対象IDを等価性から落とす退行は検知するが異値hash不等は不要な制約。
  - 保持先・処理: tests/domain/sns/test_mention.py::TestMention::test_inequality_with_different_post_ids。非等価を保持し、異値hash不等を集合共存へ置換する。PostId/ReplyIdの同数値も別物として追加検討
  - 変異: M09, M16
- **F** [`test_immutability`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_mention.py#L103-L107): 表示名と対象IDを構築後に再代入できない。現行は構築だけでfrozen解除を検知できない。
  - 保持先・処理: tests/domain/sns/test_mention.py::TestMention::test_immutability。両公開属性への通常代入拒否と元値維持を観測する
  - 変異: M03
- **C** [`test_hash_functionality`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_mention.py#L111-L127): 同値hash一致と、異なる名前/対象のhash不等を要求している。後者は保証外。元のこの宣言は等価性本体を直接比較していないため、同値hashだけ保持し、名前/対象の区別は各非等価所有者へ移す。
  - 保持先・処理: tests/domain/sns/test_mention.py::TestMention::test_equality_comparison。同値hash一致は既存保持先へ、異値は2つの非等価試験へ集約。集合の追加/検索/除去を保持しhash不等は要求しない
  - 変異: M09, M15, M16, M19
- **D** [`test_string_representation`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_mention.py#L129-L137): dataclass生成のクラス名と値の部分文字列だけを検査。生成reprの書式変更を検知するが保存/画面の形式契約ではない。
  - 保持先・処理: 生成reprの独立契約・消費経路が見つからないため保持先不要。構築値/保存は別契約。構築フィールド保持と実際の保存表現を残す。str(Mention)消費者・reprの約束はsource/docs調査で未発見
  - 変異: M39
- **R** [`test_edge_cases_for_mentioned_user_name`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_mention.py#L139-L153): 空白・数字のみ・@入りの非空名も値として無加工で受容する。抽出器/宛先解決側の規則を値型へ誤適用。
  - 保持先・処理: tests/domain/sns/test_mention.py::TestMention::test_edge_cases_for_mentioned_user_name。現契約を保持する
  - 変異: この宣言専用の追加変異なし。対象と関連範囲の成功を確認
- **C** [`test_post_id_string_conversion`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_mention.py#L155-L161): 保持されたPostIdのstr/int変換と値保持。残す所有者に同じ条件がなければ喪失するため、先に移植を確認する。
  - 保持先・処理: tests/domain/sns/test_mention.py::TestMention::test_create_mention_success。PostId(123)の型付き保持を構築条件へ。str/int自体の定義はPostId::test_string_representationに委ねる
  - 変異: M22, M23

### NotificationType（元6宣言）

- **R** [`test_notification_type_values`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_notification_type.py#L9-L16): 保存/復元に使う6種の文字列follow/mention/like/reply/subscribe/postを固定。種別文字列の変更で既存SQLite/JSONを復元不能にする。
  - 保持先・処理: tests/domain/sns/test_notification_type.py::TestNotificationType::test_notification_type_values。現契約を保持する
  - 変異: M24
- **R** [`test_notification_type_string_conversion`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_notification_type.py#L18-L25): 公開str変換が保存値文字列を返す。Enum既定のNotificationType.FOLLOW表現へ戻る。
  - 保持先・処理: tests/domain/sns/test_notification_type.py::TestNotificationType::test_notification_type_string_conversion。現契約を保持する
  - 変異: M24
- **D** [`test_notification_type_enum_properties`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_notification_type.py#L27-L33): 列挙メンバーがEnumインスタンスでname/valueを持つことだけ。Python Enum自体の性質を再検査する。
  - 保持先・処理: tests/domain/sns/test_notification_type.py::TestNotificationType::test_notification_type_values / test_notification_type_string_conversion / test_notification_type_membership / test_notification_type_iteration。独立した種別文字列・str変換・復元・6種集合の検査を残す
  - 変異: M24
- **C** [`test_notification_type_uniqueness`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_notification_type.py#L35-L38): 6種の保存値が衝突しない。残す所有者に同じ条件がなければ喪失するため、先に移植を確認する。
  - 保持先・処理: tests/domain/sns/test_notification_type.py::TestNotificationType::test_notification_type_values。既存のメンバー別期待値は全て異なり一意性も検知する。Enum反復はaliasを除くため現検査単独は空振り
  - 変異: M24
- **F** [`test_notification_type_membership`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_notification_type.py#L40-L45): 既知文字列の復元と未知文字列の拒否を保証したい。現行は列挙走査だけなのでNotificationType(value)の復元/拒否経路を通らない。
  - 保持先・処理: tests/domain/sns/test_notification_type.py::TestNotificationType::test_notification_type_membership。6保存値を実際にNotificationType(value)で復元し、未知値をValueErrorで拒む条件へ。保存codecの呼出契約を所有する
  - 変異: M10, M24, M25
- **R** [`test_notification_type_iteration`](https://github.com/Motifman/llm-rpg/blob/595065d2d35f3bcb8f6a93ecc5259a5c7252599e/tests/domain/sns/test_notification_type.py#L47-L53): 現在の6種が反復可能でFOLLOW/MENTION/POSTを含む。余分な種別追加・既存種別の欠落/alias化。6種の現行保存APIとして残し変更時に意図を再審査。
  - 保持先・処理: tests/domain/sns/test_notification_type.py::TestNotificationType::test_notification_type_iteration。現契約を保持する
  - 変異: M25

### 統合・修理時の補足

- Likeの(1,1)/(999999,999999)/(123,456)を構築試験へ移管し、(123,456)行には元の`str(user_id)=="123"`、`str(post_id)=="456"`、`int(user_id)==123`、`int(post_id)==456`の4観測を残した。M35〜M38が各観測を個別に破壊して旧新双方で検知した
- MentionのPostId(1)/(999999)/(123)保持は構築試験へ移管。123のstr/intは同じ入力を使う`TestPostId.test_string_representation`が保持する。異値名testuser1/testuser2に加え、統合元のtestuser/otheruserも非等価試験へ残した
- PostId(-1)の保持先は親の`TestPostId.test_error_message_contains_value`。削除済みの旧negative宣言を参照しない。UserId(0)/PostId(0)も同入力を狭いドメイン例外型で確認する既存ID試験が保持する
- PostContentの元の全3項目差分の行を残した上で、本文のみ/タグのみ/公開範囲のみを変える行を追加した。同値hash一致は残し、非等価な値のhash不一致という保証外の要求は除いた
- 不変性は通常の属性再代入でAttributeErrorとなり、全元値が維持されることを各属性で観測。frozenフラグの静的確認や構築成功で代用しない
- NotificationTypeのFOLLOW列挙所属はiteration試験へ保持し、既知6文字列の復元とnonexistent拒否は実際の構築経路へ移した。Enum反復はaliasを省くため、元の一意性検査は各メンバーの異なる固定値検査へ統合した

## 39種の旧新対照

全てcall段階の意図した検査失敗であり、収集・設定エラーを検知成功として数えていない。新側はC/Dを除いた33宣言の保持先を選択し、旧側は元49宣言を選択した。両側にID拒否保持先3件を加えている。変異に使った保持先と最終33宣言の関数ASTも全一致している。

| 番号 | 変異 | 分類 | 旧側 | 新側 |
|---|---|---|---|---|
| M01 | `post-content-mutable` | 修理確認 | 52成功 / 0失敗 | 52成功 / 3失敗 |
| M02 | `like-mutable` | 修理確認 | 52成功 / 0失敗 | 52成功 / 3失敗 |
| M03 | `mention-mutable` | 修理確認 | 52成功 / 0失敗 | 53成功 / 2失敗 |
| M04 | `post-content-omit-content-equality` | 修理確認 | 52成功 / 0失敗 | 54成功 / 1失敗 |
| M05 | `post-content-omit-tags-equality` | 修理確認 | 52成功 / 0失敗 | 54成功 / 1失敗 |
| M06 | `post-content-omit-visibility-equality` | 修理確認 | 52成功 / 0失敗 | 54成功 / 1失敗 |
| M07 | `like-import-time-created-at` | 修理確認 | 52成功 / 0失敗 | 54成功 / 1失敗 |
| M08 | `like-collapse-target-kind` | 修理確認 | 52成功 / 0失敗 | 53成功 / 2失敗 |
| M09 | `mention-collapse-target-kind` | 修理確認 | 52成功 / 0失敗 | 54成功 / 1失敗 |
| M10 | `notification-accept-unknown` | 修理確認 | 52成功 / 0失敗 | 54成功 / 1失敗 |
| M11 | `like-omit-user-equality` | 保持確認 | 50成功 / 2失敗 | 53成功 / 2失敗 |
| M12 | `like-omit-target-equality` | 保持確認 | 50成功 / 2失敗 | 53成功 / 2失敗 |
| M13 | `like-include-time-equality` | 保持確認 | 51成功 / 1失敗 | 54成功 / 1失敗 |
| M14 | `like-include-time-hash` | 保持確認 | 51成功 / 1失敗 | 54成功 / 1失敗 |
| M15 | `mention-omit-mentioned_user_name-equality` | 保持確認 | 50成功 / 2失敗 | 53成功 / 2失敗 |
| M16 | `mention-omit-post_id-equality` | 保持確認 | 50成功 / 2失敗 | 52成功 / 3失敗 |
| M17 | `post-content-unequal-hash-for-equals` | 保持確認 | 51成功 / 1失敗 | 54成功 / 1失敗 |
| M18 | `like-unequal-hash-for-equals` | 保持確認 | 49成功 / 3失敗 | 52成功 / 3失敗 |
| M19 | `mention-unequal-hash-for-equals` | 保持確認 | 50成功 / 2失敗 | 53成功 / 2失敗 |
| M20 | `like-corrupt-user_id-999999` | 保持確認 | 51成功 / 1失敗 | 54成功 / 1失敗 |
| M21 | `like-corrupt-post_id-456` | 保持確認 | 51成功 / 1失敗 | 53成功 / 2失敗 |
| M22 | `mention-corrupt-target-999999` | 保持確認 | 51成功 / 1失敗 | 54成功 / 1失敗 |
| M23 | `mention-corrupt-target-123` | 保持確認 | 51成功 / 1失敗 | 54成功 / 1失敗 |
| M24 | `notification-change-follow-wire-value` | 保持確認 | 49成功 / 3失敗 | 52成功 / 3失敗 |
| M25 | `notification-add-extra-member` | 保持確認 | 51成功 / 1失敗 | 54成功 / 1失敗 |
| M26 | `mention-reject-none` | 保持確認 | 51成功 / 1失敗 | 54成功 / 1失敗 |
| M27 | `mention-allow-empty` | 保持確認 | 51成功 / 1失敗 | 54成功 / 1失敗 |
| M28 | `post-content-reject-list` | 保持確認 | 49成功 / 3失敗 | 52成功 / 3失敗 |
| M29 | `post-content-deduplicate-hashtags` | 保持確認 | 51成功 / 1失敗 | 54成功 / 1失敗 |
| M30 | `post-content-change-factory-default` | 保持確認 | 51成功 / 1失敗 | 54成功 / 1失敗 |
| M31 | `id-user-accept-zero` | 保持確認 | 50成功 / 2失敗 | 54成功 / 1失敗 |
| M32 | `id-post-accept-zero` | 保持確認 | 49成功 / 3失敗 | 54成功 / 1失敗 |
| M33 | `id-post-accept-negative` | 保持確認 | 50成功 / 2失敗 | 54成功 / 1失敗 |
| M34 | `legal-constant-hashes` | 合法衝突対照 | 47成功 / 5失敗 | 55成功 / 0失敗 |
| M35 | `id-user-str-123-drift` | 保持確認 | 51成功 / 1失敗 | 54成功 / 1失敗 |
| M36 | `id-user-int-123-drift` | 保持確認 | 51成功 / 1失敗 | 54成功 / 1失敗 |
| M37 | `id-post-str-456-drift` | 保持確認 | 51成功 / 1失敗 | 54成功 / 1失敗 |
| M38 | `id-post-int-456-drift` | 保持確認 | 51成功 / 1失敗 | 54成功 / 1失敗 |
| M39 | `legal-opaque-repr` | 合法repr対照 | 50成功 / 2失敗 | 55成功 / 0失敗 |

## 保持する偽陽性と未解決事項

- PostContentの本文0/280/281、タグ0/10/11、公開範囲の型検証と日本語診断、直接構築/createの既定、タグ抽出順序・重複・区切りは全保持
- Likeの明示日時保持と異時刻同値は別々に保持。MentionのNone、50文字、underscore/ハイフン、空白/数字/@を含む名前の受容も保持し、未合意の入力制限を導入しない
- PostContentの既存list入力は保持する。list内のタグを後から変更できる可能性は別の製品検討事項であり、この監査でtuple正規化・list拒否・深い不変性修理を行ったとは主張しない
- 公開値型、factory、getter、Enum、数値ID、集約、通知配送に製品変更はない。引退ファイル・削除した製品入口・削除した共有補助は0
- #1456の集合集約コピー、#1457の参照寿命、#1458の投稿詳細の範囲/順序、#1462のPRIVATE配送は別契約。これらの確認を今回の49宣言の改善へ二重計上しない
- この文書追加は試験済み4ファイルの内容を変えていない。独立した第二読・保持審査の指摘を反映し、Likeの4変換観測とrepr削除理由を訂正してから確定した
