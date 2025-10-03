"""
SNSユーザーコマンド関連例外のテスト
"""
import pytest
from src.application.sns.exceptions.command.user_command_exception import (
    UserCommandException,
    UserCreationException,
    UserProfileUpdateException,
)


class TestUserCommandException:
    """UserCommandExceptionのテスト"""

    def test_create_basic_command_exception(self):
        """基本的なコマンド例外の作成テスト"""
        exception = UserCommandException("コマンドエラー")

        assert str(exception) == "コマンドエラー"
        assert exception.error_code == "USERCOMMANDEXCEPTION"
        assert exception.message == "コマンドエラー"
        assert exception.context == {}

    def test_create_command_exception_with_context(self):
        """コンテキスト付きのコマンド例外作成テスト"""
        exception = UserCommandException(
            "コマンドエラー",
            user_id=1,
            target_user_id=2
        )

        assert str(exception) == "コマンドエラー"
        assert exception.error_code == "USERCOMMANDEXCEPTION"
        assert exception.context["user_id"] == 1
        assert exception.context["target_user_id"] == 2
        assert exception.user_id == 1
        assert exception.target_user_id == 2


class TestUserCreationException:
    """UserCreationExceptionのテスト"""

    def test_create_user_creation_exception(self):
        """ユーザー作成例外の作成テスト"""
        exception = UserCreationException("ユーザー作成エラー", "test_user")

        assert str(exception) == "ユーザー作成エラー"
        assert exception.error_code == "USER_CREATION_ERROR"
        assert exception.context["user_name"] == "test_user"
        assert exception.user_name == "test_user"

    def test_user_creation_inheritance(self):
        """UserCreationExceptionの継承関係テスト"""
        exception = UserCreationException("テスト", "test_user")
        assert isinstance(exception, UserCommandException)
        assert isinstance(exception, Exception)


class TestUserProfileUpdateException:
    """UserProfileUpdateExceptionのテスト"""

    def test_create_user_profile_update_exception(self):
        """ユーザープロフィール更新例外の作成テスト"""
        exception = UserProfileUpdateException("プロフィール更新エラー", 1)

        assert str(exception) == "プロフィール更新エラー"
        assert exception.error_code == "USER_PROFILE_UPDATE_ERROR"
        assert exception.context["user_id"] == 1
        assert exception.user_id == 1

    def test_user_profile_update_inheritance(self):
        """UserProfileUpdateExceptionの継承関係テスト"""
        exception = UserProfileUpdateException("テスト", 1)
        assert isinstance(exception, UserCommandException)
        assert isinstance(exception, Exception)
