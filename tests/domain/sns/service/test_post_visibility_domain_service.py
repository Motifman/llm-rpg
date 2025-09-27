"""
PostVisibilityDomainServiceのテスト
"""

import pytest
from src.domain.sns.service.post_visibility_domain_service import PostVisibilityDomainService
from src.domain.sns.aggregate.post_aggregate import PostAggregate
from src.domain.sns.aggregate.user_aggregate import UserAggregate
from src.domain.sns.value_object.post_content import PostContent
from src.domain.sns.value_object.post_id import PostId
from src.domain.sns.value_object.user_id import UserId
from src.domain.sns.enum.sns_enum import PostVisibility
from src.infrastructure.repository.in_memory_sns_user_repository import InMemorySnsUserRepository


class TestPostVisibilityDomainService:
    """PostVisibilityDomainServiceのテストクラス"""

    @pytest.fixture
    def user_repository(self):
        """ユーザーリポジトリのフィクスチャ"""
        return InMemorySnsUserRepository()

    @pytest.fixture
    def hero_user(self, user_repository):
        """勇者ユーザーのフィクスチャ"""
        return user_repository.find_by_user_name("hero_user")

    @pytest.fixture
    def mage_user(self, user_repository):
        """魔法使いユーザーのフィクスチャ"""
        return user_repository.find_by_user_name("mage_user")

    @pytest.fixture
    def warrior_user(self, user_repository):
        """戦士ユーザーのフィクスチャ"""
        return user_repository.find_by_user_name("warrior_user")

    @pytest.fixture
    def thief_user(self, user_repository):
        """盗賊ユーザーのフィクスチャ"""
        return user_repository.find_by_user_name("thief_user")

    @pytest.fixture
    def merchant_user(self, user_repository):
        """商人ユーザーのフィクスチャ"""
        return user_repository.find_by_user_name("merchant_user")

    def _create_post(self, post_id: int, author_user_id: int, visibility: PostVisibility, deleted: bool = False) -> PostAggregate:
        """テスト用のポストを作成するヘルパー関数"""
        post_content = PostContent(
            content=f"Test post content {post_id}",
            hashtags=("test",),
            visibility=visibility
        )
        likes = set()
        mentions = set()

        reply_ids = set()  # テスト用の空のreply_ids

        return PostAggregate.create_from_db(
            post_id=PostId(post_id),
            author_user_id=UserId(author_user_id),
            post_content=post_content,
            likes=likes,
            mentions=mentions,
            reply_ids=reply_ids,
            deleted=deleted
        )

    def test_can_view_own_post(self, hero_user):
        """自分のポストは常に閲覧可能"""
        # Given
        post = self._create_post(1, 1, PostVisibility.PRIVATE)  # PRIVATE設定の自分のポスト

        # When
        result = PostVisibilityDomainService.can_view_post(post, hero_user, hero_user)

        # Then
        assert result is True

    def test_cannot_view_private_post_from_other(self, hero_user, mage_user):
        """PRIVATE設定の他人のポストは閲覧不可"""
        # Given
        post = self._create_post(1, 1, PostVisibility.PRIVATE)  # 勇者のPRIVATEポスト

        # When
        result = PostVisibilityDomainService.can_view_post(post, mage_user, hero_user)

        # Then
        assert result is False

    def test_can_view_public_post_from_other(self, hero_user, mage_user):
        """PUBLIC設定の他人のポストは閲覧可能"""
        # Given
        post = self._create_post(1, 1, PostVisibility.PUBLIC)  # 勇者のPUBLICポスト

        # When
        result = PostVisibilityDomainService.can_view_post(post, mage_user, hero_user)

        # Then
        assert result is True

    def test_can_view_followers_only_post_from_follower(self, mage_user, hero_user):
        """FOLLOWERS_ONLY設定のポストは、閲覧者が投稿者をフォローしていれば閲覧可能"""
        # Given: 勇者は魔法使いをフォローしている
        post = self._create_post(1, 2, PostVisibility.FOLLOWERS_ONLY)  # 魔法使いのFOLLOWERS_ONLYポスト

        # When: 勇者が魔法使いのポストを見ようとする
        result = PostVisibilityDomainService.can_view_post(post, hero_user, mage_user)

        # Then: 勇者は魔法使いをフォローしているので閲覧可能
        assert result is True

    def test_cannot_view_followers_only_post_from_non_follower(self, mage_user, warrior_user):
        """FOLLOWERS_ONLY設定のポストは、閲覧者が投稿者をフォローしていなければ閲覧不可"""
        # Given: 戦士は魔法使いをフォローしていない
        post = self._create_post(1, 2, PostVisibility.FOLLOWERS_ONLY)  # 魔法使いのFOLLOWERS_ONLYポスト

        # When: 戦士が魔法使いのポストを見ようとする
        result = PostVisibilityDomainService.can_view_post(post, warrior_user, mage_user)

        # Then: 戦士は魔法使いをフォローしていないので閲覧不可
        assert result is False

    def test_cannot_view_post_when_blocked_by_viewer(self, hero_user, merchant_user):
        """閲覧者が投稿者をブロックしている場合は閲覧不可"""
        # Given: 商人は勇者をブロックしている
        post = self._create_post(1, 1, PostVisibility.PUBLIC)  # 勇者のPUBLICポスト

        # When: 商人が勇者のポストを見ようとする
        result = PostVisibilityDomainService.can_view_post(post, merchant_user, hero_user)

        # Then: ブロックされているので閲覧不可
        assert result is False

    def test_cannot_view_post_when_blocked_by_author(self, mage_user, thief_user):
        """投稿者が閲覧者をブロックしている場合は閲覧不可"""
        # Given: 魔法使いは盗賊をブロックしている
        post = self._create_post(1, 2, PostVisibility.PUBLIC)  # 魔法使いのPUBLICポスト

        # When: 盗賊が魔法使いのポストを見ようとする
        result = PostVisibilityDomainService.can_view_post(post, thief_user, mage_user)

        # Then: ブロックされているので閲覧不可
        assert result is False

    def test_cannot_view_deleted_post(self, hero_user, mage_user):
        """削除されたポストは閲覧不可"""
        # Given
        post = self._create_post(1, 1, PostVisibility.PUBLIC, deleted=True)  # 削除された勇者のポスト

        # When
        result = PostVisibilityDomainService.can_view_post(post, mage_user, hero_user)

        # Then
        assert result is False

    def test_cannot_view_deleted_own_post(self, hero_user):
        """削除された自分のポストも閲覧不可（現在の仕様では削除されたポストは誰にも見えない）"""
        # Given
        post = self._create_post(1, 1, PostVisibility.PUBLIC, deleted=True)  # 削除された自分のポスト

        # When
        result = PostVisibilityDomainService.can_view_post(post, hero_user, hero_user)

        # Then: 現在の仕様では削除されたポストは誰にも見えない
        assert result is False
