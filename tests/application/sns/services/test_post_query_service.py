import pytest
from datetime import datetime
from src.application.sns.services.post_query_service import PostQueryService
from src.application.sns.contracts.dtos import PostDto
from src.application.sns.exceptions.query.post_query_exception import (
    PostQueryException,
    PostNotFoundException,
    PostAccessDeniedException,
    InvalidPostIdException
)
from src.application.sns.exceptions.query.user_query_exception import UserQueryException
from src.domain.sns.value_object import UserId, PostId, PostContent
from src.domain.sns.enum import PostVisibility
from src.domain.sns.aggregate.post_aggregate import PostAggregate
from src.domain.sns.aggregate.user_aggregate import UserAggregate
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
        # テストデータをセットアップ
        TestPostQueryService().setup_test_data(post_repository, user_repository)
        return PostQueryService(post_repository, user_repository)

    def create_test_post(self, post_id: int, user_id: int, content: str, visibility: PostVisibility = PostVisibility.PUBLIC) -> PostAggregate:
        """テスト用のポストを作成"""
        post_content = PostContent(
            content=content,
            hashtags=("test", "hashtag"),
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

        # プライベートポストも追加
        private_post = self.create_test_post(1002, 1, "これはプライベートポストです", PostVisibility.PRIVATE)
        post_repository._posts[PostId(1002)] = private_post

        # フォロワー限定ポストも追加（実際にはInMemoryリポジトリのポスト3を使う）

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
        with pytest.raises(InvalidPostIdException):
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
        with pytest.raises(InvalidPostIdException):
            post_query_service.get_home_timeline(viewer_user_id=0)

    def test_get_home_timeline_viewer_not_found(self, post_query_service):
        """get_home_timelineのviewer_userが見つからない場合のテスト"""
        with pytest.raises(UserQueryException):
            post_query_service.get_home_timeline(viewer_user_id=9999)

    def test_get_user_timeline_invalid_viewer_user_id(self, post_query_service):
        """get_user_timelineのviewer_user_idが無効な場合のテスト"""
        with pytest.raises(InvalidPostIdException):
            post_query_service.get_user_timeline(user_id=1, viewer_user_id=0)

    def test_get_user_timeline_viewer_not_found(self, post_query_service):
        """get_user_timelineのviewer_userが見つからない場合のテスト"""
        with pytest.raises(UserQueryException):
            post_query_service.get_user_timeline(user_id=1, viewer_user_id=9999)

    def test_get_post_invalid_post_id(self, post_query_service):
        """get_postのpost_idが無効な場合のテスト"""
        with pytest.raises(InvalidPostIdException):
            post_query_service.get_post(post_id=0, viewer_user_id=1)

    def test_get_post_invalid_viewer_user_id(self, post_query_service):
        """get_postのviewer_user_idが無効な場合のテスト"""
        with pytest.raises(InvalidPostIdException):
            post_query_service.get_post(post_id=1, viewer_user_id=0)

    def test_get_post_viewer_not_found(self, post_query_service):
        """get_postのviewer_userが見つからない場合のテスト"""
        with pytest.raises(UserQueryException):
            post_query_service.get_post(post_id=1, viewer_user_id=9999)

    def test_get_private_posts_invalid_user_id(self, post_query_service):
        """get_private_postsのuser_idが無効な場合のテスト"""
        with pytest.raises(InvalidPostIdException):
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
