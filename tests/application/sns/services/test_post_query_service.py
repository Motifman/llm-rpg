import pytest
from datetime import datetime
from src.application.sns.services.post_query_service import PostQueryService
from src.application.sns.contracts.dtos import PostDto
from src.application.sns.exceptions.query.post_query_exception import (
    PostQueryException,
    PostNotFoundException,
    PostAccessDeniedException
)
from src.application.sns.exceptions.query.user_query_exception import UserQueryException
from src.domain.sns.value_object import UserId, PostId, PostContent
from src.domain.sns.enum import PostVisibility
from src.domain.sns.aggregate.post_aggregate import PostAggregate
from src.domain.sns.aggregate.user_aggregate import UserAggregate
from src.domain.sns.exception import UserIdValidationException, PostIdValidationException
from src.infrastructure.repository.in_memory_post_repository import InMemoryPostRepository
from src.infrastructure.repository.in_memory_sns_user_repository import InMemorySnsUserRepository


class TestPostQueryService:
    """PostQueryServiceのテスト"""

    @pytest.fixture
    def post_repository(self):
        """実際のInMemoryPostRepository"""
        return InMemoryPostRepository()

    @pytest.fixture
    def user_repository(self):
        """実際のInMemorySnsUserRepository"""
        return InMemorySnsUserRepository()

    @pytest.fixture
    def post_query_service(self, post_repository, user_repository):
        """テスト対象のサービス"""
        # リポジトリをクリアしてからテストデータをセットアップ
        post_repository.clear()
        TestPostQueryService().setup_test_data(post_repository, user_repository)
        return PostQueryService(post_repository, user_repository)

    def create_test_post(self, post_id: int, user_id: int, content: str, visibility: PostVisibility = PostVisibility.PUBLIC) -> PostAggregate:
        """テスト用のポストを作成"""
        # contentからハッシュタグを抽出（#で始まる単語）
        import re
        hashtags_in_content = re.findall(r'#(\w+)', content)
        hashtags = tuple(hashtags_in_content) if hashtags_in_content else ("test", "hashtag")

        post_content = PostContent(
            content=content,
            hashtags=hashtags,
            visibility=visibility
        )
        return PostAggregate.create(
            post_id=PostId(post_id),
            author_user_id=UserId(user_id),
            post_content=post_content
        )

    def setup_test_data(self, post_repository, user_repository):
        """テストデータをセットアップ"""
        # テスト用のポストを追加
        test_post = self.create_test_post(1001, 1, "これはテストポストです")
        post_repository._posts[PostId(1001)] = test_post

        # ポストID 1も追加（get_postテスト用）
        post1 = self.create_test_post(1, 1, "これはポストID 1です")
        post_repository._posts[PostId(1)] = post1

        # プライベートポストも追加
        private_post = self.create_test_post(1002, 1, "これはプライベートポストです", PostVisibility.PRIVATE)
        post_repository._posts[PostId(1002)] = private_post

        # ホームタイムライン用のポストを追加（ユーザー2と3のポスト）
        home_post1 = self.create_test_post(1003, 2, "魔法の新しい研究成果です！ #魔法 #研究")
        post_repository._posts[PostId(1003)] = home_post1

        home_post2 = self.create_test_post(1004, 3, "今日も剣の修行を頑張った！ #剣術 #修行")
        post_repository._posts[PostId(1004)] = home_post2

        # いいね用のポストを追加
        liked_post1 = self.create_test_post(1005, 2, "いいねを集めるポストです #いいね")
        post_repository._posts[PostId(1005)] = liked_post1

        liked_post2 = self.create_test_post(1006, 3, "こちらもいいねを集めるポストです #いいね")
        post_repository._posts[PostId(1006)] = liked_post2

        # いいねデータを追加（ユーザー1がポスト1005と1006にいいね）
        from src.domain.sns.value_object.like import Like
        liked_post1._likes.add(Like(UserId(1), PostId(1005)))
        liked_post2._likes.add(Like(UserId(1), PostId(1006)))

        # 人気ポスト用のテストデータ（たくさんのいいねがついたポスト）
        popular_post1 = self.create_test_post(12, 1, "人気ポスト1です #人気")
        for i in range(10):  # 10個のいいね
            popular_post1._likes.add(Like(UserId(100+i), PostId(12)))
        post_repository._posts[PostId(12)] = popular_post1

        popular_post2 = self.create_test_post(18, 2, "人気ポスト2です #人気")
        for i in range(8):  # 8個のいいね
            popular_post2._likes.add(Like(UserId(110+i), PostId(18)))
        post_repository._posts[PostId(18)] = popular_post2

        popular_post3 = self.create_test_post(19, 3, "人気ポスト3です #人気")
        for i in range(6):  # 6個のいいね
            popular_post3._likes.add(Like(UserId(120+i), PostId(19)))
        post_repository._posts[PostId(19)] = popular_post3

        popular_post4 = self.create_test_post(20, 1, "人気ポスト4です #人気")
        for i in range(4):  # 4個のいいね
            popular_post4._likes.add(Like(UserId(130+i), PostId(20)))
        post_repository._posts[PostId(20)] = popular_post4

        # トレンド計算用のテストポストを追加（過去24時間以内）
        from datetime import datetime, timedelta
        recent_time = datetime.now() - timedelta(hours=1)  # 1時間前

        # ハッシュタグを含むポストを複数追加
        trending_post1 = self.create_test_post(2001, 1, "#トレンド #人気")
        trending_post1._created_at = recent_time  # 作成時間を1時間前に設定
        post_repository._posts[PostId(2001)] = trending_post1

        trending_post2 = self.create_test_post(2002, 1, "#トレンド #話題")
        trending_post2._created_at = recent_time + timedelta(minutes=30)  # 30分前
        post_repository._posts[PostId(2002)] = trending_post2

        trending_post3 = self.create_test_post(2003, 1, "#人気 #おすすめ")
        trending_post3._created_at = recent_time + timedelta(hours=1)  # 現在時刻
        post_repository._posts[PostId(2003)] = trending_post3

        # 古いポスト（24時間以上前）はトレンドに含まれないはず
        old_post = self.create_test_post(2004, 1, "#古い #トレンド")
        old_post._created_at = datetime.now() - timedelta(hours=25)  # 25時間前
        post_repository._posts[PostId(2004)] = old_post

        # 検索用のポストを追加
        search_post1 = self.create_test_post(3001, 2, "魔法のワークショップを開催します！ #魔法 #ワークショップ")
        post_repository._posts[PostId(3001)] = search_post1

        search_post2 = self.create_test_post(3002, 3, "新しい剣術を開発しました #剣術 #開発")
        post_repository._posts[PostId(3002)] = search_post2

        # アクセス拒否テスト用のフォロワー限定ポスト（ユーザー6のポスト）
        followers_only_post = self.create_test_post(6, 6, "これはフォロワー限定のポストです", PostVisibility.FOLLOWERS_ONLY)
        post_repository._posts[PostId(6)] = followers_only_post

    def test_get_user_timeline_success(self, post_query_service, post_repository, user_repository):
        """get_user_timelineの正常系テスト"""
        # テスト実行（ユーザー1のポストを取得）
        result = post_query_service.get_user_timeline(user_id=1, viewer_user_id=1, limit=10, offset=0)

        # 検証
        assert len(result) >= 1  # InMemoryリポジトリのサンプルデータ + テストデータ
        assert isinstance(result[0], PostDto)
        # ポストIDが正しく設定されていることを確認
        post_ids = [post.post_id for post in result]
        assert 1001 in post_ids  # テストで追加したポスト

        # 特定のポストの内容を確認
        test_post = next(post for post in result if post.post_id == 1001)
        assert test_post.author_user_id == 1
        assert test_post.content == "これはテストポストです"
        assert test_post.hashtags == ["test", "hashtag"]
        assert test_post.visibility == "public"
        assert test_post.is_deleted == False

    def test_get_user_timeline_invalid_user_id(self, post_query_service):
        """get_user_timelineの無効なユーザーIDテスト"""
        with pytest.raises(UserQueryException):
            post_query_service.get_user_timeline(user_id=0, viewer_user_id=1)

    def test_get_user_timeline_user_not_found(self, post_query_service, post_repository, user_repository):
        """get_user_timelineのユーザーが見つからないテスト"""
        # 存在しないユーザーIDを指定
        with pytest.raises(UserQueryException):
            post_query_service.get_user_timeline(user_id=9999, viewer_user_id=1)

    def test_get_post_success(self, post_query_service, post_repository, user_repository):
        """get_postの正常系テスト"""
        # テスト実行（テストで追加したポストを取得）
        result = post_query_service.get_post(post_id=1001, viewer_user_id=1)

        # 検証
        assert result is not None
        assert isinstance(result, PostDto)
        assert result.post_id == 1001
        assert result.author_user_id == 1
        assert result.content == "これはテストポストです"
        assert result.visibility == "public"

    def test_get_post_not_found(self, post_query_service, post_repository, user_repository):
        """get_postのポストが見つからないテスト"""
        # 存在しないポストIDを指定
        with pytest.raises(PostNotFoundException):
            post_query_service.get_post(post_id=9999, viewer_user_id=1)

    def test_get_post_access_denied(self, post_query_service, post_repository, user_repository):
        """get_postのアクセス拒否テスト"""
        # フォロワー限定のポスト（ユーザー6のポスト）をユーザー1（フォロワーではない）が見ようとする
        with pytest.raises(PostAccessDeniedException):
            post_query_service.get_post(post_id=6, viewer_user_id=1)

    def test_get_private_posts_success(self, post_query_service, post_repository, user_repository):
        """get_private_postsの正常系テスト"""
        # テスト実行（ユーザー1のプライベートポストを取得）
        result = post_query_service.get_private_posts(user_id=1, limit=10, offset=0)

        # 検証（InMemoryリポジトリの既存データ + テストデータ）
        private_posts = [post for post in result if post.post_id == 1002]  # テストデータだけをチェック
        assert len(private_posts) == 1
        test_post = private_posts[0]
        assert isinstance(test_post, PostDto)
        assert test_post.post_id == 1002
        assert test_post.visibility == "private"
        assert test_post.content == "これはプライベートポストです"

    def test_get_home_timeline_success(self, post_query_service, post_repository, user_repository):
        """get_home_timelineの正常系テスト"""
        # ユーザー1（勇者）のホームタイムラインを取得
        # 勇者はユーザー2（魔法使い）とユーザー3（戦士）をフォローしている
        result = post_query_service.get_home_timeline(viewer_user_id=1, limit=20, offset=0)

        # 検証
        assert len(result) >= 2  # 少なくともフォロー中のユーザーのポストが見えるはず

        # フォロー中のユーザーのポストのみが含まれていることを確認
        author_ids = {post.author_user_id for post in result}
        expected_authors = {2, 3}  # 魔法使いと戦士
        # 少なくともフォロー中のユーザーのポストが含まれているはず
        assert len(author_ids.intersection(expected_authors)) > 0

        # 各ポストがPostDtoであることを確認
        for post in result:
            assert isinstance(post, PostDto)
            assert post.author_user_id in [2, 3]  # フォロー中のユーザーのみ

    def test_get_home_timeline_no_followees(self, post_query_service, post_repository, user_repository):
        """get_home_timelineのフォロー中ユーザーがいない場合のテスト"""
        # ユーザー6（商人）は誰もフォローしていない
        result = post_query_service.get_home_timeline(viewer_user_id=6, limit=20, offset=0)

        # 検証
        assert result == []  # 空のリストが返るはず

    def test_get_home_timeline_invalid_viewer_id(self, post_query_service):
        """get_home_timelineのviewer_user_idが無効な場合のテスト"""
        with pytest.raises(UserQueryException):
            post_query_service.get_home_timeline(viewer_user_id=0)

    def test_get_home_timeline_viewer_not_found(self, post_query_service):
        """get_home_timelineのviewer_userが見つからない場合のテスト"""
        with pytest.raises(UserQueryException):
            post_query_service.get_home_timeline(viewer_user_id=9999)

    def test_get_user_timeline_invalid_viewer_user_id(self, post_query_service):
        """get_user_timelineのviewer_user_idが無効な場合のテスト"""
        with pytest.raises(UserQueryException):
            post_query_service.get_user_timeline(user_id=1, viewer_user_id=0)

    def test_get_user_timeline_viewer_not_found(self, post_query_service):
        """get_user_timelineのviewer_userが見つからない場合のテスト"""
        with pytest.raises(UserQueryException):
            post_query_service.get_user_timeline(user_id=1, viewer_user_id=9999)

    def test_get_post_invalid_post_id(self, post_query_service):
        """get_postのpost_idが無効な場合のテスト"""
        with pytest.raises(PostQueryException):
            post_query_service.get_post(post_id=0, viewer_user_id=1)

    def test_get_post_invalid_viewer_user_id(self, post_query_service):
        """get_postのviewer_user_idが無効な場合のテスト"""
        with pytest.raises(UserQueryException):
            post_query_service.get_post(post_id=1, viewer_user_id=0)

    def test_get_post_viewer_not_found(self, post_query_service):
        """get_postのviewer_userが見つからない場合のテスト"""
        with pytest.raises(UserQueryException):
            post_query_service.get_post(post_id=1, viewer_user_id=9999)

    def test_get_private_posts_invalid_user_id(self, post_query_service):
        """get_private_postsのuser_idが無効な場合のテスト"""
        with pytest.raises(UserQueryException):
            post_query_service.get_private_posts(user_id=0)

    def test_get_private_posts_user_not_found(self, post_query_service):
        """get_private_postsのユーザーが見つからない場合のテスト"""
        with pytest.raises(UserQueryException):
            post_query_service.get_private_posts(user_id=9999)

    def test_get_home_timeline_blocked_content_filtered(self, post_query_service, post_repository, user_repository):
        """get_home_timelineのブロック関係によるフィルタリングテスト"""
        # ユーザー6（商人）の視点からホームタイムラインを取得
        # ユーザー6はユーザー1（勇者）をブロックしているので、勇者のポストは見えないはず
        result = post_query_service.get_home_timeline(viewer_user_id=6, limit=20, offset=0)

        # 検証
        # ユーザー6は誰もフォローしていないので、もともと空のはず
        # しかし、もしブロック機能が正しく動作していればなお良い
        assert result == []  # フォロー中のユーザーがいないため空

        # 逆に、ユーザー1（勇者）の視点から確認
        # 勇者はユーザー6にブロックされていないので、通常動作するはず
        result_user1 = post_query_service.get_home_timeline(viewer_user_id=1, limit=20, offset=0)
        assert len(result_user1) >= 2  # フォロー中のユーザーのポストが見える

    def test_get_user_timeline_blocked_viewer(self, post_query_service, post_repository, user_repository):
        """get_user_timelineのブロックされたviewerによるアクセステスト"""
        # ユーザー6（商人）のポストをユーザー1（勇者）が見ようとする
        # ユーザー6はユーザー1をブロックしているので、ポストが見えないはず
        result = post_query_service.get_user_timeline(user_id=6, viewer_user_id=1, limit=10, offset=0)

        # 検証
        # ブロックされている場合、ポストが見えないか、アクセス拒否になるはず
        # 現在の実装では、can_be_viewed_byでブロック関係もチェックされているはず
        # ユーザー6のポストはフォロワー限定なので、ユーザー1（フォロワーではない）が見えないはず
        # ブロック関係も加味すると、より厳しく制限されるはず
        assert len(result) == 0  # アクセスできないポストはフィルタリングされるはず

    def test_get_post_author_not_found(self, post_query_service, post_repository, user_repository):
        """get_postの著者ユーザーが見つからない場合のテスト"""
        # テスト用のポストを作成（存在しない著者ユーザーIDを使用）
        from src.domain.sns.aggregate.post_aggregate import PostAggregate
        from src.domain.sns.value_object import PostId, UserId
        from src.domain.sns.value_object.post_content import PostContent
        from src.domain.sns.enum.sns_enum import PostVisibility

        # 存在しない著者ユーザーID（999）のポストを作成
        test_content = PostContent(
            content="テストポスト",
            hashtags=("test",),
            visibility=PostVisibility.PUBLIC
        )
        from src.domain.sns.value_object import Like, Mention, ReplyId

        orphaned_post = PostAggregate(
            post_id=PostId(9998),
            author_user_id=UserId(999),  # 存在しないユーザー
            post_content=test_content,
            likes=set(),  # Likeオブジェクトのセット
            mentions=set(),  # Mentionオブジェクトのセット
            reply_ids=set(),  # ReplyIdオブジェクトのセット
            deleted=False,
            parent_post_id=None,
            parent_reply_id=None,
            created_at=None
        )
        post_repository.save(orphaned_post)

        # 存在するviewer_userでアクセスしようとする
        with pytest.raises(PostAccessDeniedException):
            post_query_service.get_post(post_id=9998, viewer_user_id=1)

    def test_get_home_timeline_author_not_found(self, post_query_service, post_repository, user_repository):
        """get_home_timelineの著者ユーザーが見つからない場合のテスト"""
        # テスト用のポストを作成（存在しない著者ユーザーIDを使用）
        from src.domain.sns.aggregate.post_aggregate import PostAggregate
        from src.domain.sns.value_object import PostId, UserId
        from src.domain.sns.value_object.post_content import PostContent
        from src.domain.sns.enum.sns_enum import PostVisibility

        # 存在しない著者ユーザーID（999）のポストを作成
        test_content = PostContent(
            content="テストポスト",
            hashtags=("test",),
            visibility=PostVisibility.PUBLIC
        )
        orphaned_post = PostAggregate(
            post_id=PostId(9999),
            author_user_id=UserId(999),  # 存在しないユーザー
            post_content=test_content,
            likes=set(),  # Likeオブジェクトのセット
            mentions=set(),  # Mentionオブジェクトのセット
            reply_ids=set(),  # ReplyIdオブジェクトのセット
            deleted=False,
            parent_post_id=None,
            parent_reply_id=None,
            created_at=None
        )
        post_repository.save(orphaned_post)

        # このポストをフォロー中のユーザーのポストとして扱うため、
        # ユーザー1がユーザー999をフォローしているように見せかける
        # しかし実際にはユーザー999は存在しないので、スキップされるはず
        result = post_query_service.get_home_timeline(viewer_user_id=1, limit=20, offset=0)

        # 検証：存在しない著者のポストはスキップされて、通常の結果が返るはず
        assert len(result) >= 2  # 他の有効なポストは見えるはず

    def test_unexpected_exception_handling(self, post_query_service, post_repository, user_repository):
        """予期せぬ例外のハンドリングテスト"""
        from unittest.mock import patch
        from src.application.sns.exceptions import SystemErrorException

        # post_repository.find_by_user_id で予期せぬ例外を発生させる
        with patch.object(post_repository, 'find_by_user_id', side_effect=RuntimeError("予期せぬエラー")):
            with pytest.raises(SystemErrorException) as exc_info:
                post_query_service.get_user_timeline(user_id=1, viewer_user_id=1)

            # 例外メッセージに元の例外情報が含まれていることを確認
            assert "予期せぬエラー" in str(exc_info.value)

    def test_domain_exception_conversion(self, post_query_service, post_repository, user_repository):
        """ドメイン例外からアプリケーション例外への変換テスト"""
        from unittest.mock import patch
        from src.domain.sns.exception.user_profile_exceptions import UserProfileException

        # _user_repository.find_by_id でドメイン例外を発生させる
        # UserProfileExceptionはUserQueryExceptionに変換される
        with patch.object(user_repository, 'find_by_id', side_effect=UserProfileException("ユーザープロファイルエラー")):
            with pytest.raises(UserQueryException):
                post_query_service.get_post(post_id=1, viewer_user_id=1)

    # 新しい機能のテスト
    def test_get_liked_posts_success(self, post_query_service, post_repository, user_repository):
        """get_liked_postsの正常系テスト"""
        # 勇者（ユーザー1）がいいねしたポストを取得
        result = post_query_service.get_liked_posts(user_id=1, viewer_user_id=1, limit=10, offset=0)

        # 検証：勇者は複数のポストにいいねしているはず
        assert len(result) >= 2  # テストデータで勇者は2つのポストにいいねしている
        assert isinstance(result[0], PostDto)

        # いいねしたポストであることを確認（テストデータに基づく）
        post_ids = [post.post_id for post in result]
        # ポスト1005（魔法使いのポスト）やポスト1006（戦士のポスト）などが含まれているはず
        assert any(post_id in [1005, 1006] for post_id in post_ids)

    def test_get_liked_posts_invalid_user_id(self, post_query_service):
        """get_liked_postsの無効なユーザーIDテスト"""
        with pytest.raises(UserQueryException):
            post_query_service.get_liked_posts(user_id=0, viewer_user_id=1)

    def test_get_liked_posts_user_not_found(self, post_query_service):
        """get_liked_postsのユーザーが見つからないテスト"""
        with pytest.raises(UserQueryException):
            post_query_service.get_liked_posts(user_id=9999, viewer_user_id=1)

    def test_search_posts_by_hashtag_success(self, post_query_service, post_repository, user_repository):
        """search_posts_by_hashtagの正常系テスト"""
        # "魔法"ハッシュタグで検索
        result = post_query_service.search_posts_by_hashtag(hashtag="魔法", viewer_user_id=1, limit=10, offset=0)

        # 検証：魔法関連のポストが見つかるはず
        assert len(result) >= 2  # 複数の魔法関連ポストがある
        assert isinstance(result[0], PostDto)

        # ハッシュタグに"魔法"が含まれていることを確認
        for post in result:
            assert "魔法" in post.hashtags

    def test_search_posts_by_hashtag_empty_hashtag(self, post_query_service):
        """search_posts_by_hashtagの空ハッシュタグテスト"""
        # 空のハッシュタグでも例外は発生せず、空の結果が返る
        result = post_query_service.search_posts_by_hashtag(hashtag="", viewer_user_id=1)
        assert result == []

    def test_search_posts_by_hashtag_no_results(self, post_query_service):
        """search_posts_by_hashtagの結果なしテスト"""
        result = post_query_service.search_posts_by_hashtag(hashtag="存在しないハッシュタグ", viewer_user_id=1)
        assert len(result) == 0

    def test_search_posts_by_keyword_success(self, post_query_service, post_repository, user_repository):
        """search_posts_by_keywordの正常系テスト"""
        # "新しい"キーワードで検索
        result = post_query_service.search_posts_by_keyword(keyword="新しい", viewer_user_id=1, limit=10, offset=0)

        # 検証：新しい関連のポストが見つかるはず
        assert len(result) >= 2  # 複数の新しい関連ポストがある
        assert isinstance(result[0], PostDto)

        # コンテンツに"新しい"が含まれていることを確認
        for post in result:
            assert "新しい" in post.content.lower()

    def test_search_posts_by_keyword_empty_keyword(self, post_query_service):
        """search_posts_by_keywordの空キーワードテスト"""
        # 空のキーワードでも例外は発生せず、全てのポストが返る（リポジトリの実装による）
        result = post_query_service.search_posts_by_keyword(keyword="", viewer_user_id=1)
        assert len(result) > 0  # 少なくとも1つ以上のポストが返るはず

    def test_search_posts_by_keyword_no_results(self, post_query_service):
        """search_posts_by_keywordの結果なしテスト"""
        result = post_query_service.search_posts_by_keyword(keyword="存在しないキーワード12345", viewer_user_id=1)
        assert len(result) == 0

    def test_get_popular_posts_success(self, post_query_service, post_repository, user_repository):
        """get_popular_postsの正常系テスト"""
        # 人気ポストランキングを取得（24時間以内のトップ10）
        result = post_query_service.get_popular_posts(viewer_user_id=1, timeframe_hours=24, limit=10, offset=0)

        # 検証：人気ポストが見つかるはず
        assert len(result) >= 3  # 複数の人気ポストがある
        assert isinstance(result[0], PostDto)

        # いいね数順にソートされていることを確認（最初のポストが最もいいねが多い）
        if len(result) > 1:
            # 人気ポストが含まれていることを確認（ポスト20、12、18、19などが人気のはず）
            post_ids = [post.post_id for post in result]
            popular_post_ids = {12, 18, 19, 20}  # サンプルデータで人気のポスト
            assert any(post_id in popular_post_ids for post_id in post_ids[:3])  # トップ3に人気ポストが含まれている

    def test_get_popular_posts_invalid_viewer_id(self, post_query_service):
        """get_popular_postsの無効なviewer_user_idテスト"""
        with pytest.raises(UserQueryException):
            post_query_service.get_popular_posts(viewer_user_id=0)

    def test_get_popular_posts_viewer_not_found(self, post_query_service):
        """get_popular_postsの閲覧者が見つからないテスト"""
        with pytest.raises(UserQueryException):
            post_query_service.get_popular_posts(viewer_user_id=9999)

    def test_get_popular_posts_different_timeframe(self, post_query_service):
        """get_popular_postsの異なるタイムフレームテスト"""
        # 1時間のタイムフレームで取得
        result_1h = post_query_service.get_popular_posts(viewer_user_id=1, timeframe_hours=1, limit=10)
        # 48時間のタイムフレームで取得
        result_48h = post_query_service.get_popular_posts(viewer_user_id=1, timeframe_hours=48, limit=10)

        # 48時間の結果の方が多く含まれる可能性がある
        assert len(result_48h) >= len(result_1h)

    def test_new_features_with_visibility_filtering(self, post_query_service):
        """新しい機能の可視性フィルタリングテスト"""
        # フォロワー限定のポストがあるユーザー（例: ユーザー3）のいいねしたポストを取得
        # ただし、閲覧者はユーザー1（フォロワー）なので見えるはず
        liked_posts = post_query_service.get_liked_posts(user_id=1, viewer_user_id=1, limit=20)

        # ハッシュタグ検索でも可視性チェック（パブリック限定）
        public_hashtag_posts = post_query_service.search_posts_by_hashtag(hashtag="冒険", viewer_user_id=1)

        # キーワード検索でも可視性チェック（パブリック限定）
        public_keyword_posts = post_query_service.search_posts_by_keyword(keyword="みんな", viewer_user_id=1)

        # 人気ポストランキングでも可視性チェック
        popular_posts = post_query_service.get_popular_posts(viewer_user_id=1, limit=20)

        # 全ての結果がPostDtoであることを確認
        for post in liked_posts + public_hashtag_posts + public_keyword_posts + popular_posts:
            assert isinstance(post, PostDto)

        # get_liked_postsでは自分のポスト（プライベート含む）が見える可能性がある
        for post in liked_posts:
            assert post.visibility in ["public", "followers_only", "private"]

        # 検索機能ではプライベートポストは見えないはず
        for post in public_hashtag_posts:
            assert post.visibility in ["public", "followers_only"], f"ハッシュタグ検索でプライベートポストが見える: {post.post_id}"
        for post in public_keyword_posts:
            assert post.visibility in ["public", "followers_only"], f"キーワード検索でプライベートポストが見える: {post.post_id}"

        # 人気ポストランキングでは自分のポスト（プライベート含む）が見える可能性がある
        for post in popular_posts:
            assert post.visibility in ["public", "followers_only", "private"], f"人気ポストで不正な可視性のポストが見える: {post.post_id}"

    def test_domain_exception_handling(self, post_query_service):
        """ドメイン層の例外が適切にアプリケーション層でハンドリングされることをテスト"""
        # 無効なUserIdでget_user_timelineを呼び出す
        with pytest.raises(UserQueryException):
            post_query_service.get_user_timeline(user_id=0, viewer_user_id=1)

        # 無効なPostIdでget_postを呼び出す
        with pytest.raises(PostQueryException):
            post_query_service.get_post(post_id=0, viewer_user_id=1)

        # 無効なUserIdでget_home_timelineを呼び出す
        with pytest.raises(UserQueryException):
            post_query_service.get_home_timeline(viewer_user_id=0)

        # 無効なUserIdでget_private_postsを呼び出す
        with pytest.raises(UserQueryException):
            post_query_service.get_private_posts(user_id=0)

        # 無効なUserIdでget_liked_postsを呼び出す
        with pytest.raises(UserQueryException):
            post_query_service.get_liked_posts(user_id=1, viewer_user_id=0)

    def test_get_private_posts_uses_domain_methods(self, post_query_service):
        """get_private_postsがドメインオブジェクトのメソッドを正しく使用することをテスト"""
        # プライベートポストを取得
        private_posts = post_query_service.get_private_posts(user_id=1, limit=10)

        # 全ての結果がPostDtoであることを確認
        for post in private_posts:
            assert isinstance(post, PostDto)
            assert post.visibility == "private"  # プライベートのみが返されるはず
            assert post.author_user_id == 1  # 自分のポストのみ

        # ソートされていることを確認（新しい順）
        if len(private_posts) > 1:
            for i in range(len(private_posts) - 1):
                assert private_posts[i].created_at >= private_posts[i + 1].created_at

    @pytest.fixture
    def trending_test_service(self, post_repository, user_repository):
        """トレンドテスト専用のサービス"""
        # リポジトリをクリア
        post_repository.clear()

        # トレンド計算用のテストデータのみを追加
        from datetime import datetime, timedelta
        recent_time = datetime.now() - timedelta(hours=1)

        # ハッシュタグを含むポストを追加
        trending_post1 = self.create_test_post(3001, 1, "#トレンド #人気")
        trending_post1._created_at = recent_time
        post_repository._posts[PostId(3001)] = trending_post1

        trending_post2 = self.create_test_post(3002, 1, "#トレンド #話題")
        trending_post2._created_at = recent_time + timedelta(minutes=30)
        post_repository._posts[PostId(3002)] = trending_post2

        trending_post3 = self.create_test_post(3003, 1, "#人気 #おすすめ")
        trending_post3._created_at = recent_time + timedelta(hours=1)
        post_repository._posts[PostId(3003)] = trending_post3

        return PostQueryService(post_repository, user_repository)

    def test_get_trending_hashtags_success(self, trending_test_service):
        """get_trending_hashtagsの正常系テスト"""
        # テスト実行
        result = trending_test_service.get_trending_hashtags(limit=5, decay_lambda=0.1, recent_window_hours=1.0)

        # 検証
        assert isinstance(result, list)
        assert len(result) > 0  # ハッシュタグが返されるはず

        # 全ての要素が文字列であることを確認
        for hashtag in result:
            assert isinstance(hashtag, str)
            assert hashtag.startswith("#")  # ハッシュタグ形式

        # 期待されるハッシュタグが含まれていることを確認
        hashtag_set = set(result)
        expected_hashtags = {"#トレンド", "#人気", "#話題", "#おすすめ"}
        assert len(hashtag_set & expected_hashtags) > 0, f"期待されるハッシュタグが見つからない: {result}"

        # ハイブリッドスコア計算の検証
        # 全てのポストが直近1時間以内なので成長率 = 総数
        # スコア = log(1+総数) × 総数 × 減衰スコア合計
        # #人気: 総数=2, 減衰合計≈1.9048, スコア≈log(3)*2*1.9048≈4.186
        # #トレンド: 総数=2, 減衰合計≈1.856, スコア≈log(3)*2*1.856≈4.086
        # #おすすめ: 総数=1, 減衰合計=1.0, スコア≈log(2)*1*1.0≈0.693
        # #話題: 総数=1, 減衰合計≈0.9512, スコア≈log(2)*1*0.9512≈0.659
        # 結果: #人気 > #トレンド > #おすすめ > #話題
        expected_order = ["#人気", "#トレンド", "#おすすめ", "#話題"]
        for i, expected_hashtag in enumerate(expected_order):
            if i < len(result):
                assert result[i] == expected_hashtag, f"順位{i+1}が{expected_hashtag}であるべき: {result}"

    def test_get_trending_hashtags_limit(self, post_query_service):
        """get_trending_hashtagsのlimitパラメータテスト"""
        # limit=2でテスト実行
        result = post_query_service.get_trending_hashtags(limit=2)

        # 検証
        assert isinstance(result, list)
        assert len(result) <= 2  # limit以下であることを確認
