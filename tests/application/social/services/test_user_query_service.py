"""
UserQueryServiceのテスト
"""
import pytest
from unittest.mock import Mock, patch
from src.application.social.services.user_query_service import UserQueryService
from src.infrastructure.repository.in_memory_sns_user_repository import InMemorySnsUserRepository
from src.application.social.contracts.commands import GetUserProfilesCommand
from src.application.social.contracts.dtos import UserProfileDto, ErrorResponseDto
from src.domain.sns.enum.sns_enum import UserRelationshipType
from src.application.social.exceptions.query.user_query_exception import (
    UserQueryException,
)


class TestUserQueryService:
    """UserQueryServiceのテストクラス"""

    def setup_method(self):
        """各テストメソッドの前に実行"""
        self.repository = InMemorySnsUserRepository()
        self.service = UserQueryService(self.repository)

    def teardown_method(self):
        """各テストメソッドの後に実行"""
        pass

    def test_show_my_profile_success(self):
        """自分のプロフィール表示 - 正常系"""
        # Given
        viewer_user_id = 1

        # When
        result = self.service.show_my_profile(viewer_user_id)

        # Then
        assert isinstance(result, UserProfileDto)
        assert result.user_id == 1
        assert result.user_name == "hero_user"
        assert result.display_name == "勇者"
        assert result.bio == "世界を救う勇者です"
        assert result.followee_count == 2  # 魔法使いと戦士
        assert result.follower_count == 4  # 4人のフォロワー
        assert result.is_following is None  # 自分のプロフィールなのでNone
        assert result.is_followed_by is None
        assert result.is_blocked is None
        assert result.is_blocked_by is None
        assert result.is_subscribed is None

    def test_show_my_profile_invalid_user_id(self):
        """自分のプロフィール表示 - 無効なユーザーID"""
        # Given
        viewer_user_id = 0  # 無効なID

        # When & Then
        with pytest.raises(UserQueryException):
            self.service.show_my_profile(viewer_user_id)

    def test_show_my_profile_user_not_found(self):
        """自分のプロフィール表示 - 存在しないユーザー"""
        # Given
        viewer_user_id = 999  # 存在しないID

        # When & Then
        with pytest.raises(UserQueryException):
            self.service.show_my_profile(viewer_user_id)

    def test_show_other_user_profile_success(self):
        """他のユーザーのプロフィール表示 - 正常系"""
        # Given
        other_user_id = 2  # 魔法使い
        viewer_user_id = 1  # 勇者

        # When
        result = self.service.show_other_user_profile(other_user_id, viewer_user_id)

        # Then
        assert isinstance(result, UserProfileDto)
        assert result.user_id == 2
        assert result.user_name == "mage_user"
        assert result.display_name == "魔法使い"
        assert result.followee_count == 2  # 勇者と戦士
        assert result.follower_count == 2  # 勇者と僧侶
        assert result.is_following is True   # 勇者は魔法使いをフォローしている
        assert result.is_followed_by is True  # 魔法使いは勇者をフォローしている（相互フォロー）
        assert result.is_blocked is False    # 勇者は魔法使いをブロックしていない
        assert result.is_blocked_by is False # 魔法使いは勇者をブロックしていない
        assert result.is_subscribed is True  # 勇者は魔法使いを購読している

    def test_show_other_user_profile_self_reference(self):
        """他のユーザーのプロフィール表示 - 自分自身を指定"""
        # Given
        other_user_id = 1
        viewer_user_id = 1

        # When
        result = self.service.show_other_user_profile(other_user_id, viewer_user_id)

        # Then
        assert result.is_following is False  # 自分自身なのでFalse
        assert result.is_followed_by is False
        assert result.is_blocked is False
        assert result.is_blocked_by is False
        assert result.is_subscribed is False

    def test_show_other_user_profile_invalid_user_id(self):
        """他のユーザーのプロフィール表示 - 無効なユーザーID"""
        # Given
        other_user_id = 0
        viewer_user_id = 1

        # When & Then
        with pytest.raises(UserQueryException):
            self.service.show_other_user_profile(other_user_id, viewer_user_id)

    def test_show_followees_profile_success(self):
        """フォロー中ユーザーのプロフィール一覧 - 正常系"""
        # Given
        viewer_user_id = 1

        # When
        results = self.service.show_followees_profile(viewer_user_id)

        # Then
        assert len(results) == 2  # 勇者は2人をフォロー
        user_ids = [result.user_id for result in results]
        assert set(user_ids) == {2, 3}  # 魔法使いと戦士

        # 魔法使いのプロフィール確認
        mage_profile = next(result for result in results if result.user_id == 2)
        assert mage_profile.is_following is True   # 勇者は魔法使いをフォローしている
        assert mage_profile.is_followed_by is True  # 相互フォロー
        assert mage_profile.is_subscribed is True  # 勇者は魔法使いを購読している

    def test_show_followees_profile_empty(self):
        """フォロー中ユーザーのプロフィール一覧 - 空の場合"""
        # Given
        viewer_user_id = 6  # 商人は誰もフォローしていない

        # When
        results = self.service.show_followees_profile(viewer_user_id)

        # Then
        assert len(results) == 0

    def test_show_followers_profile_success(self):
        """フォロワーのプロフィール一覧 - 正常系"""
        # Given
        viewer_user_id = 1  # 勇者のフォロワー

        # When
        results = self.service.show_followers_profile(viewer_user_id)

        # Then
        assert len(results) == 4  # 勇者には4人のフォロワー
        user_ids = [result.user_id for result in results]
        assert set(user_ids) == {2, 3, 4, 5}  # 魔法使い、戦士、盗賊、僧侶

    def test_show_blocked_users_profile_success(self):
        """ブロック中ユーザーのプロフィール一覧 - 正常系"""
        # Given
        viewer_user_id = 2  # 魔法使いは盗賊をブロック

        # When
        results = self.service.show_blocked_users_profile(viewer_user_id)

        # Then
        assert len(results) == 1  # 1人をブロック
        assert results[0].user_id == 4  # 盗賊
        assert results[0].is_blocked is True  # 魔法使いが盗賊をブロックしている

    def test_show_blocked_users_profile_empty(self):
        """ブロック中ユーザーのプロフィール一覧 - 空の場合"""
        # Given
        viewer_user_id = 1  # 勇者は誰もブロックしていない

        # When
        results = self.service.show_blocked_users_profile(viewer_user_id)

        # Then
        assert len(results) == 0

    def test_show_blockers_profile_success(self):
        """ブロックしているユーザーのプロフィール一覧 - 正常系"""
        # Given
        viewer_user_id = 4  # 盗賊は魔法使いにブロックされている

        # When
        results = self.service.show_blockers_profile(viewer_user_id)

        # Then
        assert len(results) == 1  # 1人にブロックされている
        assert results[0].user_id == 2  # 魔法使い
        assert results[0].is_blocked_by is True  # 魔法使いが盗賊をブロックしている

    def test_show_subscriptions_profile_success(self):
        """購読中ユーザーのプロフィール一覧 - 正常系"""
        # Given
        viewer_user_id = 1  # 勇者は魔法使いを購読

        # When
        results = self.service.show_subscriptions_users_profile(viewer_user_id)

        # Then
        assert len(results) == 1  # 1人を購読
        assert results[0].user_id == 2  # 魔法使い
        assert results[0].is_subscribed is True  # 購読されている

    def test_show_subscribers_profile_success(self):
        """購読者のプロフィール一覧 - 正常系"""
        # Given
        viewer_user_id = 1  # 勇者は魔法使いと僧侶に購読されている

        # When
        results = self.service.show_subscribers_users_profile(viewer_user_id)

        # Then
        assert len(results) == 2  # 2人に購読されている
        user_ids = [result.user_id for result in results]
        assert set(user_ids) == {2, 5}  # 魔法使いと僧侶
