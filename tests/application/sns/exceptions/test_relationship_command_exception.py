"""
SNS関係性コマンド関連例外のテスト
"""
import pytest
from src.application.sns.exceptions.command.relationship_command_exception import (
    UserFollowException,
    UserBlockException,
    UserSubscribeException,
)


class TestUserFollowException:
    """UserFollowExceptionのテスト"""

    def test_create_user_follow_exception(self):
        """ユーザーフォロー例外の作成テスト"""
        exception = UserFollowException("フォローエラー", 1, 2)

        assert str(exception) == "フォローエラー"
        assert exception.error_code == "USER_FOLLOW_ERROR"
        assert exception.context["user_id"] == 1
        assert exception.context["target_user_id"] == 2
        assert exception.follower_user_id == 1
        assert exception.followee_user_id == 2
        assert exception.user_id == 1
        assert exception.target_user_id == 2

    def test_user_follow_inheritance(self):
        """UserFollowExceptionの継承関係テスト"""
        exception = UserFollowException("テスト", 1, 2)
        assert isinstance(exception, Exception)


class TestUserBlockException:
    """UserBlockExceptionのテスト"""

    def test_create_user_block_exception(self):
        """ユーザーブロック例外の作成テスト"""
        exception = UserBlockException("ブロックエラー", 1, 2)

        assert str(exception) == "ブロックエラー"
        assert exception.error_code == "USER_BLOCK_ERROR"
        assert exception.context["user_id"] == 1
        assert exception.context["target_user_id"] == 2
        assert exception.blocker_user_id == 1
        assert exception.blocked_user_id == 2
        assert exception.user_id == 1
        assert exception.target_user_id == 2

    def test_user_block_inheritance(self):
        """UserBlockExceptionの継承関係テスト"""
        exception = UserBlockException("テスト", 1, 2)
        assert isinstance(exception, Exception)


class TestUserSubscribeException:
    """UserSubscribeExceptionのテスト"""

    def test_create_user_subscribe_exception(self):
        """ユーザー購読例外の作成テスト"""
        exception = UserSubscribeException("購読エラー", 1, 2)

        assert str(exception) == "購読エラー"
        assert exception.error_code == "USER_SUBSCRIBE_ERROR"
        assert exception.context["user_id"] == 1
        assert exception.context["target_user_id"] == 2
        assert exception.subscriber_user_id == 1
        assert exception.subscribed_user_id == 2
        assert exception.user_id == 1
        assert exception.target_user_id == 2

    def test_user_subscribe_inheritance(self):
        """UserSubscribeExceptionの継承関係テスト"""
        exception = UserSubscribeException("テスト", 1, 2)
        assert isinstance(exception, Exception)
