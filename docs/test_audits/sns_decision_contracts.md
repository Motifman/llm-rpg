# SNSドメイン判断27宣言の保持と検査修理

## なぜ見直したか

順位の試験が、返された数だけを条件付きで比較していたため、空または先頭1件だけの結果でも成功していた。また「ハッシュタグのない投稿」の補助が2つのタグを自動で補い、名前が示す空タグ入力を試していなかった。

関係と閲覧の21宣言も一つずつ読み、別の入口へ移せるか検討した。購読の相手側ブロック、通常閲覧と削除スレッドの違い、例外の人物IDは独立した契約なので維持する。宣言数を減らすための削除はしない。

## 範囲と結果

- 元版: [PR #1779](https://github.com/Motifman/llm-rpg/pull/1779) の `6b5c7c4c1174a870f631e16026ce10c1d689b2e0`
- 元27宣言: 関係6、閲覧15、順位6。判断はR（保持）23、F（契約を維持して検査修理）4、C（統合）0、D（削除）0
- 最終も27宣言。無タグの実条件を1行追加したため実行条件は27から28
- 対象試験は577行から599行。実変更は順位試験1ファイルの39行追加・17行削除。関係・閲覧の2ファイルはバイト単位で不変
- 製品・共通補助の変更は0。試験専用の製品入口を追加しない
- 編集前27件・関連873件、編集後28件・関連874件が成功。関連件数は対象を含む
- 35種の制御変異を旧新の対象試験で対照、計70実行。修理6種は旧側成功・新側失敗、保持29種は両側失敗

## 所有者と保持先

### 関係の許可と拒否

[RelationshipDomainService](../../src/ai_rpg_world/domain/sns/service/relationship_domain_service.py) を [UserCommandService](../../src/ai_rpg_world/application/social/services/user_command_service.py) が実際に呼ぶ。集約単体は相手の集約を受け取らず、相手から自分へのブロックを判断できない。

成功2宣言は「例外を投げず許可する」契約で、assert文がないことを削除理由にしない。拒否4宣言は例外型と関係する人物IDを観測する。購読のブロック拒否では、フォロー済みの前提を満たして後段へ到達する。

外側の `test_subscribe_user_blocked_user_raises_exception` は、実際には `FollowUserCommand` を `follow_user` へ渡す。購読ガードの保持先ではない。自己購読の宣言は未フォロー状態で `SelfSubscribeException` を要求し、前提の確認順序も検知する。

### 通常閲覧と削除スレッド

[PostVisibilityDomainService](../../src/ai_rpg_world/domain/sns/service/post_visibility_domain_service.py) は [PostQueryService](../../src/ai_rpg_world/application/social/services/post_query_service.py) と [ReplyQueryService](../../src/ai_rpg_world/application/social/services/reply_query_service.py) に呼ばれる。通常閲覧9宣言と削除スレッド6宣言を維持した。

通常は本人のPRIVATE投稿を許可するが、削除済みなら本人にも拒否する。削除スレッド用の別入口は、本人と非ブロックの他者に削除表示用の墓標を許可する。[PublicSnsAccessPolicy](../../src/ai_rpg_world/application/social/public_sns/access_policy.py) は本人の非公開も除き全祖先を確認する別規則であり、この15宣言の代わりにはしない。

サンプルデータのフォローは1→2/3、2→1/3、3→1、4→1、5→1/2。ブロックは2→4、6→1。FOLLOWERS_ONLYの肯定行は1と2が相互フォローしており、単独では方向反転を検知しない。否定行の閲覧者3→作者2は未フォローだが逆方向は成立しているため、そちらが方向反転を検知する。削除墓標の拒否2行は閲覧者2→作者1の追加ブロックを検査する。作者側も同じ行で検査したとは扱わない。

### 順位と得点

[TrendingDomainService](../../src/ai_rpg_world/domain/sns/service/trending_domain_service.py) がタグごとの得点と順位を所有する。外側の `PostQueryService.get_trending_hashtags` は得点を捨て、タグだけを返すため、数値の保持先にできない。

- basicは元の3投稿・4タグ・全引数と型、件数、正値、降順の検査を維持し、タグと独立な数値得点を加えた
- hybridは元入力の4タグ全体を無条件で比較し、空・短縮結果を許さなくした
- growthは元の先頭確認を維持し、古いタグの存在と得点0、新しいタグの数値得点を追加した
- no_hashtagsは、元補助が入れていた `("test", "hashtag")` を明示行に残し、本当の空tupleを別行で追加した。元の2包含検査を、順序を問わない全タグ比較へ強めた

数値期待値は同じ処理の戻り値から生成しない。元入力で頻度・直近割合・時間減衰を手計算すると、人気4.078195683600、トレンド0.627185505177、話題0.659341993658、おすすめ0.693147180560となる。丸め誤差を許す近似比較で検査する。同点タグの順位、公開範囲による選別、時間窓直後の追加規則は導入していない。

## 元27宣言の全台帳

各項目は元の固定版へのリンク、実入力と観測、検知する退行、保持先を記載する。Rは元関数を維持し、Fだけ検査を修理した。
### 01. R: `test_can_follow_success`

- 元宣言: [tests/domain/sns/service/test_relationship_domain_service.py:43](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_relationship_domain_service.py#L43-L51)
- 元入力と観測: UserId(1)とUserId(2)、両者blockなし。例外なしを観測
- 契約と退行: 相手から未ブロックならフォロー検査を通す。過剰な常時拒否を検知する
- 保持先: 同じファイルの `test_can_follow_success`。対照: `follow-allow`

### 02. R: `test_can_follow_blocked_user_raises_exception`

- 元宣言: [tests/domain/sns/service/test_relationship_domain_service.py:53](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_relationship_domain_service.py#L53-L67)
- 元入力と観測: UserId(1)がUserId(2)へfollow申請。2→1のみblock。CannotFollowBlockedUserExceptionとID属性1/2
- 契約と退行: 相手→自分のブロックでフォロー拒否、両ID付き例外。ブロック方向反転/ガード欠落を検知する
- 保持先: 同じファイルの `test_can_follow_blocked_user_raises_exception`。対照: `follow-block`, `follow-ids`

### 03. R: `test_can_subscribe_success`

- 元宣言: [tests/domain/sns/service/test_relationship_domain_service.py:69](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_relationship_domain_service.py#L69-L80)
- 元入力と観測: 1→2 followあり、両者blockなし。購読検査の例外なし
- 契約と退行: フォロー済み・未ブロックなら購読検査を通す。正常な購読の過剰拒否を検知する
- 保持先: 同じファイルの `test_can_subscribe_success`。対照: `subscribe-allow`

### 04. R: `test_can_subscribe_not_followed_raises_exception`

- 元宣言: [tests/domain/sns/service/test_relationship_domain_service.py:82](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_relationship_domain_service.py#L82-L93)
- 元入力と観測: 1→2 followなし、自己ではなくblockもなし。CannotSubscribeNotFollowedUserExceptionとID属性1/2
- 契約と退行: 未フォロー購読を専用例外で拒否。フォロー前提のガード欠落を検知する
- 保持先: 同じファイルの `test_can_subscribe_not_followed_raises_exception`。対照: `subscribe-follow`, `subscribe-follow-ids`

### 05. R: `test_can_subscribe_self_subscribe_raises_exception`

- 元宣言: [tests/domain/sns/service/test_relationship_domain_service.py:95](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_relationship_domain_service.py#L95-L104)
- 元入力と観測: 同一UserId(1)、followなし。SelfSubscribeExceptionが未follow例外より先、user_id=1
- 契約と退行: 自己購読を他の前提より先に専用例外で拒否。自己判定の欠落によって未フォロー例外になる退行を検知する
- 保持先: 同じファイルの `test_can_subscribe_self_subscribe_raises_exception`。対照: `subscribe-self`, `subscribe-self-id`

### 06. R: `test_can_subscribe_blocked_user_raises_exception`

- 元宣言: [tests/domain/sns/service/test_relationship_domain_service.py:106](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_relationship_domain_service.py#L106-L123)
- 元入力と観測: 1→2 followあり、2→1 blockあり。前段を通過してCannotSubscribeBlockedUserExceptionとID属性1/2
- 契約と退行: フォロー成立済みで相手のブロックを専用例外で拒否。後段ブロックガード削除/逆方向検査を検知する
- 保持先: 同じファイルの `test_can_subscribe_blocked_user_raises_exception`。対照: `subscribe-block`, `subscribe-block-ids`

### 07. R: `test_can_view_own_post`

- 元宣言: [tests/domain/sns/service/test_post_visibility_domain_service.py:72](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_post_visibility_domain_service.py#L72-L81)
- 元入力と観測: PostId(1)、作者1、viewer1、PRIVATE、deleted=False → True
- 契約と退行: 本人はPRIVATE投稿を閲覧可能。本人のPRIVATEに対する誤拒否を検知する
- 保持先: 同じファイルの `test_can_view_own_post`。対照: `post-own-private`

### 08. R: `test_cannot_view_private_post_from_other`

- 元宣言: [tests/domain/sns/service/test_post_visibility_domain_service.py:83](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_post_visibility_domain_service.py#L83-L92)
- 元入力と観測: PostId(1)、作者1、viewer2、PRIVATE、deleted=False、双方向blockなし → False
- 契約と退行: 他者PRIVATEを拒否。PRIVATEガード欠落を検知する
- 保持先: 同じファイルの `test_cannot_view_private_post_from_other`。対照: `post-private-other`

### 09. R: `test_can_view_public_post_from_other`

- 元宣言: [tests/domain/sns/service/test_post_visibility_domain_service.py:94](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_post_visibility_domain_service.py#L94-L103)
- 元入力と観測: PostId(1)、作者1、viewer2、PUBLIC、deleted=False、双方向blockなし → True
- 契約と退行: 非ブロック他者PUBLICを許可。PUBLICの過剰拒否を検知する
- 保持先: 同じファイルの `test_can_view_public_post_from_other`。対照: `post-public-other`

### 10. R: `test_can_view_followers_only_post_from_follower`

- 元宣言: [tests/domain/sns/service/test_post_visibility_domain_service.py:105](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_post_visibility_domain_service.py#L105-L114)
- 元入力と観測: PostId(1)、作者2、viewer1、FOLLOWERS_ONLY、1→2および2→1 followあり → True。単独では方向反転を検知しない
- 契約と退行: 閲覧者→作者のfollow成立を許可。常時拒否を検知する。方向反転はこの宣言単独では検知しない
- 保持先: 同じファイルの `test_can_view_followers_only_post_from_follower`。対照: `post-followers-allow`

### 11. R: `test_cannot_view_followers_only_post_from_non_follower`

- 元宣言: [tests/domain/sns/service/test_post_visibility_domain_service.py:116](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_post_visibility_domain_service.py#L116-L125)
- 元入力と観測: PostId(1)、作者2、viewer3、FOLLOWERS_ONLY、3→2 followなし、2→3 followあり → False。向き反転も検知
- 契約と退行: 閲覧者が作者をfollowしなければ拒否。FOLLOWERS_ONLYの常時許可または閲覧者と作者のfollow方向反転を検知する
- 保持先: 同じファイルの `test_cannot_view_followers_only_post_from_non_follower`。対照: `post-follow-direction`

### 12. R: `test_cannot_view_post_when_blocked_by_viewer`

- 元宣言: [tests/domain/sns/service/test_post_visibility_domain_service.py:127](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_post_visibility_domain_service.py#L127-L136)
- 元入力と観測: PostId(1)、作者1、viewer6、PUBLIC、6→1 blockあり、1→6なし → False
- 契約と退行: 閲覧者→作者blockを拒否。閲覧者側のブロック検査の欠落を検知する
- 保持先: 同じファイルの `test_cannot_view_post_when_blocked_by_viewer`。対照: `post-viewer-block`

### 13. R: `test_cannot_view_post_when_blocked_by_author`

- 元宣言: [tests/domain/sns/service/test_post_visibility_domain_service.py:138](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_post_visibility_domain_service.py#L138-L147)
- 元入力と観測: PostId(1)、作者2、viewer4、PUBLIC、2→4 blockあり、4→2なし → False
- 契約と退行: 作者→閲覧者blockを拒否。作者側のブロック検査の欠落を検知する
- 保持先: 同じファイルの `test_cannot_view_post_when_blocked_by_author`。対照: `post-author-block`

### 14. R: `test_cannot_view_deleted_post`

- 元宣言: [tests/domain/sns/service/test_post_visibility_domain_service.py:149](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_post_visibility_domain_service.py#L149-L158)
- 元入力と観測: PostId(1)、作者1、viewer2、PUBLIC、deleted=True、blockなし → False
- 契約と退行: 削除投稿を他者へ返さない。deletedガード欠落を検知する
- 保持先: 同じファイルの `test_cannot_view_deleted_post`。対照: `post-deleted-other`

### 15. R: `test_cannot_view_deleted_own_post`

- 元宣言: [tests/domain/sns/service/test_post_visibility_domain_service.py:160](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_post_visibility_domain_service.py#L160-L169)
- 元入力と観測: PostId(1)、作者1、viewer1、PUBLIC、deleted=True → False。削除拒否を本人許可より先に適用
- 契約と退行: 本人であっても削除投稿は通常閲覧不可。本人許可が削除拒否より優先される退行を検知する
- 保持先: 同じファイルの `test_cannot_view_deleted_own_post`。対照: `post-deleted-own`

### 16. R: `test_can_view_deleted_post_for_reply_thread_by_owner`

- 元宣言: [tests/domain/sns/service/test_post_visibility_domain_service.py:171](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_post_visibility_domain_service.py#L171-L180)
- 元入力と観測: PostId(1)、作者1、viewer1、PUBLIC、deleted=True、削除投稿用入口 → True
- 契約と退行: 本人の削除投稿をスレッド墓標として許可。通常閲覧の拒否を墓標にも誤適用する退行を検知する
- 保持先: 同じファイルの `test_can_view_deleted_post_for_reply_thread_by_owner`。対照: `post-tombstone-own`

### 17. R: `test_can_view_deleted_post_for_reply_thread_by_other`

- 元宣言: [tests/domain/sns/service/test_post_visibility_domain_service.py:182](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_post_visibility_domain_service.py#L182-L191)
- 元入力と観測: PostId(1)、作者1、viewer2、PUBLIC、deleted=True、blockなし、削除投稿用入口 → True
- 契約と退行: 非ブロック他者の削除投稿をスレッド墓標として許可。削除を理由とした墓標の常時拒否を検知する
- 保持先: 同じファイルの `test_can_view_deleted_post_for_reply_thread_by_other`。対照: `post-tombstone-other`

### 18. R: `test_cannot_view_deleted_post_for_reply_thread_when_blocked`

- 元宣言: [tests/domain/sns/service/test_post_visibility_domain_service.py:193](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_post_visibility_domain_service.py#L193-L205)
- 元入力と観測: PostId(1)、作者1、viewer2、PUBLIC、deleted=True、追加block2→1、削除投稿用入口 → False
- 契約と退行: block時は削除投稿墓標も拒否。墓標経路のblockガード欠落を検知する
- 保持先: 同じファイルの `test_cannot_view_deleted_post_for_reply_thread_when_blocked`。対照: `post-tombstone-viewer-block`

### 19. R: `test_can_view_deleted_reply_for_thread_by_owner`

- 元宣言: [tests/domain/sns/service/test_post_visibility_domain_service.py:207](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_post_visibility_domain_service.py#L207-L228)
- 元入力と観測: ReplyId(1)、親PostId(1)、親ReplyId=None、親作者1、作者1、viewer1、本文テストリプライ、タグ()、PUBLIC、delete(1,reply)後、削除返信用入口 → True
- 契約と退行: 本人の削除返信をスレッド墓標として許可。返信墓標の常時拒否を検知する
- 保持先: 同じファイルの `test_can_view_deleted_reply_for_thread_by_owner`。対照: `reply-tombstone-own`

### 20. R: `test_can_view_deleted_reply_for_thread_by_other`

- 元宣言: [tests/domain/sns/service/test_post_visibility_domain_service.py:230](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_post_visibility_domain_service.py#L230-L251)
- 元入力と観測: ReplyId(1)、親PostId(1)、親ReplyId=None、親作者1、作者1、viewer2、本文テストリプライ、タグ()、PUBLIC、delete(1,reply)後、blockなし → True
- 契約と退行: 非ブロック他者の削除返信墓標を許可。非作者に対する墓標の誤拒否を検知する
- 保持先: 同じファイルの `test_can_view_deleted_reply_for_thread_by_other`。対照: `reply-tombstone-other`

### 21. R: `test_cannot_view_deleted_reply_for_thread_when_blocked`

- 元宣言: [tests/domain/sns/service/test_post_visibility_domain_service.py:253](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_post_visibility_domain_service.py#L253-L277)
- 元入力と観測: ReplyId(1)、親PostId(1)、親ReplyId=None、親作者1、作者1、viewer2、本文テストリプライ、タグ()、PUBLIC、delete(1,reply)後、追加block2→1 → False
- 契約と退行: block時は削除返信墓標も拒否。返信墓標経路のblockガード欠落を検知する
- 保持先: 同じファイルの `test_cannot_view_deleted_reply_for_thread_when_blocked`。対照: `reply-tombstone-viewer-block`

### 22. F: `test_calculate_trending_hashtags_basic`

- 元宣言: [tests/domain/sns/service/test_trending_domain_service.py:36](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_trending_domain_service.py#L36-L67)
- 元入力と観測: 投稿ID1/2/3、全作者1。本文#人気 #トレンド(1時間前)、#人気 #話題(0.5時間前)、#おすすめ(現在)。lambda0.1/window1/max10。list、長さ4、str/float、全正値、降順
- 契約と退行: タグ4種、正float、降順と加算を保持。元の検査が見逃していた、別タグへの置換や得点の寄与の欠落を検知する
- 修理: 元3投稿・全型/件数/正値/降順assertを残し、4タグ集合と独立な数値得点をpytest.approxで追加
- 保持先: 同じファイルの `test_calculate_trending_hashtags_basic`。対照: `trend-constant-scores`, `trend-renamed-tags`

### 23. F: `test_calculate_trending_hashtags_hybrid_score`

- 元宣言: [tests/domain/sns/service/test_trending_domain_service.py:69](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_trending_domain_service.py#L69-L94)
- 元入力と観測: 投稿ID1/2/3、全作者1。本文#トレンド #人気(1時間前)、#トレンド #話題(0.5時間前)、#人気 #おすすめ(現在)。lambda0.1/window1/max10。元条件付き順位人気/トレンド/おすすめ/話題
- 契約と退行: 頻度・成長率・減衰による全4タグの順位。元の条件付きassertが見逃していた、空または先頭1件だけの結果を検知する
- 修理: 元入力をそのまま使用し、条件付き順位assertを4要素全体の無条件比較へ変更
- 保持先: 同じファイルの `test_calculate_trending_hashtags_hybrid_score`。対照: `trend-empty-ranking`, `trend-short-ranking`

### 24. F: `test_calculate_trending_hashtags_growth_rate`

- 元宣言: [tests/domain/sns/service/test_trending_domain_service.py:96](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_trending_domain_service.py#L96-L122)
- 元入力と観測: 投稿ID1/2/3、全作者1。#古いトレンドが2時間前に2投稿、#新しいトレンドが0.5時間前に1投稿。lambda0.1/window1/max10。新しいタグが先頭
- 契約と退行: 古い2投稿より新しい1投稿を優先し古いタグも保持。古いタグや得点0のタグの消失を検知する
- 修理: 元先頭assertを残し、2タグ集合と古いタグ得点0/新しいタグ独立数値得点を追加
- 保持先: 同じファイルの `test_calculate_trending_hashtags_growth_rate`。対照: `trend-drop-zero`

### 25. R: `test_calculate_trending_hashtags_empty_posts`

- 元宣言: [tests/domain/sns/service/test_trending_domain_service.py:124](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_trending_domain_service.py#L124-L136)
- 元入力と観測: posts=[]、nowあり、lambda0.1/window1/max10 → []
- 契約と退行: 投稿空集合は結果空。固定タグの返却や空入力での例外を検知する
- 保持先: 同じファイルの `test_calculate_trending_hashtags_empty_posts`。対照: `trend-empty-posts`

### 26. F: `test_calculate_trending_hashtags_no_hashtags`

- 元宣言: [tests/domain/sns/service/test_trending_domain_service.py:138](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_trending_domain_service.py#L138-L157)
- 元入力と観測: 投稿ID1、作者1、本文ハッシュタグのないポスト、作成時刻now。ただし元補助がhashtags=(test,hashtag)を注入。両タグの存在だけを観測
- 契約と退行: 本当にタグが無い非空投稿は空結果。補助がタグを補い、本当の空タグ入力を試していなかった問題を修理する
- 修理: 元本文・時刻・投稿/作者IDを保持。元の明示2タグ行と本当にタグ()行へパラメータ化。補助から勝手な2タグ注入を除き、元2つの包含assertは集合一致で包含する。名前も実条件へ合わせる
- 保持先: 同じファイルの `test_calculate_trending_hashtags_uses_explicit_tags`。対照: `trend-invent-tags`, `trend-preserve-test`, `trend-preserve-hashtag`

### 27. R: `test_calculate_trending_hashtags_max_results`

- 元宣言: [tests/domain/sns/service/test_trending_domain_service.py:159](https://github.com/Motifman/llm-rpg/blob/6b5c7c4c1174a870f631e16026ce10c1d689b2e0/tests/domain/sns/service/test_trending_domain_service.py#L159-L177)
- 元入力と観測: 投稿ID1、作者1、本文#tag0 #tag1 #tag2 #tag3 #tag4、時刻now。lambda0.1/window1/max3 → 長さ3。同点順位を要求しない
- 契約と退行: 非空5タグをmax_results3へ制限。件数制限の欠落や上限の1件ずれを検知する
- 保持先: 同じファイルの `test_calculate_trending_hashtags_max_results`。対照: `trend-limit`

## 制御変異の全結果

「成功→失敗」は元の穴を新試験が検知したこと、「失敗→失敗」は元の観測を保持したことを示す。各変異はその契約に対応する対象宣言だけを旧新で実行し、広い試験群の別の失敗を根拠にしない。

| 変異 | 対象 | 旧→新 | 観測した違反 |
|---|---|---|---|
| `follow-allow` | `can_follow_success` | 失敗→失敗 | 正常なフォローを過剰拒否 |
| `follow-block` | `can_follow_blocked_user_raises_exception` | 失敗→失敗 | 相手のブロック拒否を削除 |
| `subscribe-allow` | `can_subscribe_success` | 失敗→失敗 | 正常な購読を未フォロー扱いで拒否 |
| `subscribe-follow` | `can_subscribe_not_followed_raises_exception` | 失敗→失敗 | 未フォローの前提検査を削除 |
| `subscribe-self` | `can_subscribe_self_subscribe_raises_exception` | 失敗→失敗 | 自己購読を未フォロー例外へすり替え |
| `subscribe-block` | `can_subscribe_blocked_user_raises_exception` | 失敗→失敗 | フォロー済みでも相手のブロックを無視 |
| `follow-ids` | `can_follow_blocked_user_raises_exception` | 失敗→失敗 | フォロー例外の2人物IDを逆転 |
| `subscribe-follow-ids` | `can_subscribe_not_followed_raises_exception` | 失敗→失敗 | 未フォロー例外の2人物IDを逆転 |
| `subscribe-self-id` | `can_subscribe_self_subscribe_raises_exception` | 失敗→失敗 | 自己購読例外の人物IDを変更 |
| `subscribe-block-ids` | `can_subscribe_blocked_user_raises_exception` | 失敗→失敗 | 購読ブロック例外の2人物IDを逆転 |
| `post-own-private` | `can_view_own_post` | 失敗→失敗 | 本人のPRIVATE許可を落とす |
| `post-private-other` | `cannot_view_private_post_from_other` | 失敗→失敗 | 他者のPRIVATEを許可 |
| `post-public-other` | `can_view_public_post_from_other` | 失敗→失敗 | 非ブロックPUBLICを拒否 |
| `post-followers-allow` | `can_view_followers_only_post_from_follower` | 失敗→失敗 | フォロワーを常時拒否 |
| `post-follow-direction` | `cannot_view_followers_only_post_from_non_follower` | 失敗→失敗 | 作者と閲覧者のフォロー方向を反転 |
| `post-viewer-block` | `cannot_view_post_when_blocked_by_viewer` | 失敗→失敗 | 閲覧者のブロック検査を削除 |
| `post-author-block` | `cannot_view_post_when_blocked_by_author` | 失敗→失敗 | 作者のブロック検査を削除 |
| `post-deleted-other` | `cannot_view_deleted_post` | 失敗→失敗 | 削除された他者投稿を許可 |
| `post-deleted-own` | `cannot_view_deleted_own_post` | 失敗→失敗 | 本人なら削除判定を回避 |
| `post-tombstone-own` | `can_view_deleted_post_for_reply_thread_by_owner` | 失敗→失敗 | 削除投稿墓標を本人に拒否 |
| `post-tombstone-other` | `can_view_deleted_post_for_reply_thread_by_other` | 失敗→失敗 | 削除投稿墓標を他者に拒否 |
| `post-tombstone-viewer-block` | `cannot_view_deleted_post_for_reply_thread_when_blocked` | 失敗→失敗 | 削除投稿墓標で閲覧者ブロックを無視 |
| `reply-tombstone-own` | `can_view_deleted_reply_for_thread_by_owner` | 失敗→失敗 | 削除返信墓標を本人に拒否 |
| `reply-tombstone-other` | `can_view_deleted_reply_for_thread_by_other` | 失敗→失敗 | 削除返信墓標を他者に拒否 |
| `reply-tombstone-viewer-block` | `cannot_view_deleted_reply_for_thread_when_blocked` | 失敗→失敗 | 削除返信墓標で閲覧者ブロックを無視 |
| `trend-constant-scores` | `calculate_trending_hashtags_basic` | 成功→失敗 | 全得点を1.0へ変更 |
| `trend-renamed-tags` | `calculate_trending_hashtags_basic` | 成功→失敗 | 全タグを別名へ変更 |
| `trend-empty-ranking` | `calculate_trending_hashtags_hybrid_score` | 成功→失敗 | 順位結果を空へ変更 |
| `trend-short-ranking` | `calculate_trending_hashtags_hybrid_score` | 成功→失敗 | 順位結果を先頭1件へ短縮 |
| `trend-drop-zero` | `calculate_trending_hashtags_growth_rate` | 成功→失敗 | 得点0の古いタグを除去 |
| `trend-invent-tags` | `calculate_trending_hashtags_no_hashtags` | 成功→失敗 | 空タグの非空投稿にダミータグを補填 |
| `trend-empty-posts` | `calculate_trending_hashtags_empty_posts` | 失敗→失敗 | 空投稿から固定タグを返す |
| `trend-limit` | `calculate_trending_hashtags_max_results` | 失敗→失敗 | max_resultsの切り出しを無視 |
| `trend-preserve-test` | `calculate_trending_hashtags_no_hashtags` | 失敗→失敗 | 元のtestタグだけ除去 |
| `trend-preserve-hashtag` | `calculate_trending_hashtags_no_hashtags` | 失敗→失敗 | 元のhashtagタグだけ除去 |

空タグ補填の変異では、新しい `no-tags` 行だけが失敗し、元入力の `explicit-tags` 行は成功した。元2タグをそれぞれ除く変異では逆に `explicit-tags` だけが失敗し、`no-tags` は成功した。入力のすり替えによる見せかけの修理ではない。

各変異後に製品の元のバイト列を復元して照合し、最後に全製品1587ファイルが元版と一致することも確認した。最終の製品差分は0。

## 実行した検証

Python3.10.22、pytest8.4.1、固定依存の既存実行環境を使い、対象作業ツリーのsrc読込を確認した。外部接続は遮断し、実LLM・有償APIは呼んでいない。

- 基準: 対象27件、関連873件成功
- 候補と最終: 対象28件成功
- 最終関連: 874件成功。同じ収集集合に真の空タグ1条件のみ追加
- 旧新対照: 35種、70実行。想定以外の収集エラーや実行エラーはなし
- ruff0.16.8の変更試験ファイル検査、`git diff --check` 成功
- 独立第二読で元27宣言の対応、入力、数値期待値、ガード順序、保持先を確認後に編集

通常の所有者試験コマンド:

```sh
uv run --frozen pytest   tests/domain/sns/service/test_relationship_domain_service.py   tests/domain/sns/service/test_post_visibility_domain_service.py   tests/domain/sns/service/test_trending_domain_service.py -q
```

関連試験の範囲:

```sh
uv run --frozen pytest tests/domain/sns tests/application/social   tests/application/observation/services/test_sns_recipient_strategy.py   tests/application/observation/formatters/test_sns_formatter.py   tests/infrastructure/repository/test_public_sns_notification_metadata.py   tests/infrastructure/repository/test_sqlite_sns_notification_repository.py   tests/infrastructure/repository/test_public_sns_snapshot_codec.py   tests/infrastructure/repository/test_sns_identity_persistence.py -q
```

全リポジトリ試験はローカルでは実行していない。公開commitのCIは別に確認する。

## 履歴と並行変更

対象の関係試験は `822a5b69418a37537a93702f4cfdbfc262568cd3`、閲覧試験は `c36064f48632034096221c50a3713348c362d738` と `65fabcb14f2e94fb4f87f8d56ac362024b259cc7`、順位試験は後者のSNS試験整備に由来する。その後の主な対象変更はsrc配置・import・型注釈の整備であり、古いという理由で業務規則を削除しない。

監査時のmain `7c7dc63c5f4be701832a3f1443e27682fe9869d1` と対象・所有者・呼出元・利用集約・サンプル/リポジトリの計15blobを照合し、一致を確認した。並行中の [#1456](https://github.com/Motifman/llm-rpg/pull/1456)、[#1457](https://github.com/Motifman/llm-rpg/pull/1457)、[#1458](https://github.com/Motifman/llm-rpg/pull/1458)、[#1462](https://github.com/Motifman/llm-rpg/pull/1462) は対象試験と直接所有者を変えていない。集合所有権、参照寿命、ページ分割、非公開配送はそれぞれの修理に委ねる。

## 限界と別の確認事項

- 通常の `can_view_reply` の直接行を、この元15宣言が含んでいるとは扱わない
- 外側の返信閲覧試験には、作成ID2004/2005に対して1004/1005の不存在を検査する行がある。後者はブロックにも止められる。この変更では修理せず、別のapplication試験監査候補とする
- 外側の順位試験にも条件付き比較が残るが、今回の保持先にせず、別のapplication試験監査で扱う
- 新旧SNS入口の公開範囲・削除表示・配送を、この試験修理で統一したとは扱わない
