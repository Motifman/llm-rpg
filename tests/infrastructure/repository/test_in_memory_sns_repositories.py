import pytest
from tests.infrastructure.repository.test_sns_user_repository_interface import _TestUserRepositoryInterface
from tests.infrastructure.repository.test_post_repository_interface import _TestPostRepositoryInterface
from tests.infrastructure.repository.test_reply_repository_interface import _TestReplyRepositoryInterface
from src.infrastructure.repository.in_memory_sns_user_repository import InMemorySnsUserRepository
from src.infrastructure.repository.in_memory_post_repository import InMemoryPostRepository
from src.infrastructure.repository.in_memory_reply_repository import InMemoryReplyRepository
from src.domain.sns.value_object import UserId, PostId, ReplyId


class TestInMemoryUserRepository(_TestUserRepositoryInterface):
    """InMemory実装のUserRepositoryテスト"""

    @pytest.fixture
    def repository(self):
        return InMemorySnsUserRepository()


class TestInMemoryUserRepositorySpecific:
    """InMemory実装特有のUserRepositoryテスト"""

    @pytest.fixture
    def repository(self):
        return InMemorySnsUserRepository()

    def test_save_and_find_new_user(self, repository):
        """新規ユーザー保存と検索テスト"""
        from src.domain.sns.entity.sns_user import SnsUser
        from src.domain.sns.value_object.user_profile import UserProfile
        from src.domain.sns.aggregate.user_aggregate import UserAggregate

        # 新しいユーザーを作成
        new_profile = UserProfile("test_user", "テストユーザー", "テスト用のユーザーです")
        new_sns_user = SnsUser(UserId(7), new_profile)
        new_user = UserAggregate(UserId(7), new_sns_user, [], [], [])

        # 保存
        repository.save(new_user)

        # 検索確認
        found_user = repository.find_by_id(UserId(7))
        assert found_user is not None
        assert found_user.user_id.value == 7
        assert found_user.get_user_profile_info()["user_name"] == "test_user"

    def test_update_profile(self, repository):
        """プロフィール更新テスト"""
        updated_user = repository.update_profile(UserId(1), "新しい自己紹介", "新勇者")
        assert updated_user is not None
        profile_info = updated_user.get_user_profile_info()
        assert profile_info["bio"] == "新しい自己紹介"
        assert profile_info["display_name"] == "新勇者"

    def test_bulk_update_relationships(self, repository):
        """一括関係性更新テスト"""
        relationships = [
            (UserId(3), UserId(2), "follow"),    # 戦士 -> 魔法使いをフォロー
            (UserId(4), UserId(2), "follow"),    # 盗賊 -> 魔法使いをフォロー
        ]

        updated_count = repository.bulk_update_relationships(relationships)
        assert updated_count == 2

        # 結果の検証
        assert repository.is_following(UserId(3), UserId(2)) == True
        assert repository.is_following(UserId(4), UserId(2)) == True

    def test_cleanup_broken_relationships(self, repository):
        """無効な関係性クリーンアップテスト"""
        cleaned_count = repository.cleanup_broken_relationships()
        assert cleaned_count >= 0

    def test_clear_method(self, repository):
        """クリアメソッドテスト（InMemory特有）"""
        initial_count = repository.count()
        assert initial_count > 0

        repository.clear()
        assert repository.count() == 0
        assert len(repository._username_to_user_id) == 0


class TestInMemoryPostRepository(_TestPostRepositoryInterface):
    """InMemory実装のPostRepositoryテスト"""

    @pytest.fixture
    def repository(self):
        return InMemoryPostRepository()


class TestInMemoryPostRepositorySpecific:
    """InMemory実装特有のPostRepositoryテスト"""

    @pytest.fixture
    def repository(self):
        return InMemoryPostRepository()

    def test_save_and_find_new_post(self, repository):
        """新規ポスト保存と検索テスト"""
        from src.domain.sns.aggregate import PostAggregate
        from src.domain.sns.value_object import PostContent
        from src.domain.sns.enum import PostVisibility
        from datetime import datetime

        # 新しいポストを作成
        content = PostContent(
            content="テストポスト",
            hashtags=("テスト",),
            visibility=PostVisibility.PUBLIC
        )
        new_post = PostAggregate(
            PostId(6), UserId(1), content, set(), set(), set(),
            False, None, None, datetime.now()
        )

        # 保存
        repository.save(new_post)

        # 検索確認
        found_post = repository.find_by_id(PostId(6))
        assert found_post is not None
        assert found_post.post_id == PostId(6)
        assert found_post.content.content == "テストポスト"

    def test_clear_method(self, repository):
        """クリアメソッドテスト（InMemory特有）"""
        initial_count = repository.count()
        assert initial_count > 0

        repository.clear()
        assert repository.count() == 0


class TestInMemoryReplyRepository(_TestReplyRepositoryInterface):
    """InMemory実装のReplyRepositoryテスト"""

    @pytest.fixture
    def repository(self):
        return InMemoryReplyRepository()


class TestInMemoryReplyRepositorySpecific:
    """InMemory実装特有のReplyRepositoryテスト"""

    @pytest.fixture
    def repository(self):
        return InMemoryReplyRepository()

    def test_save_and_find_new_reply(self, repository):
        """新規リプライ保存と検索テスト"""
        from src.domain.sns.aggregate import ReplyAggregate
        from src.domain.sns.value_object import PostContent
        from src.domain.sns.enum import PostVisibility
        from datetime import datetime

        # 新しいリプライを作成
        content = PostContent(
            content="テストリプライ",
            hashtags=("テスト",),
            visibility=PostVisibility.PUBLIC
        )
        new_reply = ReplyAggregate(
            ReplyId(8), UserId(1), content, set(), set(), set(),
            False, PostId(1), None, datetime.now()
        )

        # 保存
        repository.save(new_reply)

        # 検索確認
        found_reply = repository.find_by_id(ReplyId(8))
        assert found_reply is not None
        assert found_reply.reply_id == ReplyId(8)
        assert found_reply.content.content == "テストリプライ"

# 統合テスト：リポジトリ間の連携テスト
class TestSNSRepositoriesIntegration:
    """SNS関連リポジトリの統合テスト"""

    @pytest.fixture
    def user_repository(self):
        return InMemorySnsUserRepository()

    @pytest.fixture
    def post_repository(self):
        return InMemoryPostRepository()

    @pytest.fixture
    def reply_repository(self):
        return InMemoryReplyRepository()

    def test_user_post_reply_workflow(self, user_repository, post_repository, reply_repository):
        """ユーザー・ポスト・リプライのワークフロー統合テスト"""
        # ユーザーの存在確認
        user = user_repository.find_by_id(UserId(1))
        assert user is not None

        # ポストの存在確認
        post = post_repository.find_by_id(PostId(1))
        assert post is not None
        assert post.author_user_id == user.user_id

        # リプライの存在確認
        replies = reply_repository.find_by_post_id(PostId(1))
        assert len(replies) > 0

        # リプライのユーザーが存在することを確認
        for reply in replies:
            reply_user = user_repository.find_by_id(reply.author_user_id)
            assert reply_user is not None

    def test_follow_relationship_and_timeline(self, user_repository, post_repository):
        """フォロー関係とタイムラインの統合テスト"""
        # 勇者のフォロー中ユーザーを取得
        followees = user_repository.find_followees(UserId(1))
        assert len(followees) > 0

        # フォロー中ユーザーのポストを取得
        posts = post_repository.find_by_user_ids(followees, limit=10)
        assert isinstance(posts, list)

        # ポストのユーザーがフォロー中であることを確認
        for post in posts:
            assert post.author_user_id in followees

    def test_hashtag_search_across_repositories(self, post_repository, reply_repository):
        """ハッシュタグ検索のリポジトリ間統合テスト"""
        # ポストのハッシュタグ検索
        posts = post_repository.find_posts_by_hashtag("冒険")
        assert len(posts) > 0

        # 結果の内容が正しいことを確認
        for post in posts:
            assert "冒険" in post.content.hashtags

        # リプライのコンテンツ検索（ハッシュタグ検索の代わり）
        replies = reply_repository.search_replies_by_content("冒険")
        # リプライの結果はなくても良い（テストデータの都合）
