"""
SNSユーザー検索関連例外のテスト
"""
import pytest
from src.application.sns.exceptions.query.user_query_exception import (
    UserQueryException,
    ProfileNotFoundException,
    UserNotFoundException,
    InvalidUserIdException,
    ProfileQueryException,
    RelationshipQueryException,
)


class TestUserQueryException:
    """UserQueryExceptionのテスト"""

    def test_create_basic_query_exception(self):
        """基本的なクエリ例外の作成テスト"""
        exception = UserQueryException("クエリエラー")

        assert str(exception) == "クエリエラー"
        assert exception.error_code == "USERQUERYEXCEPTION"
        assert exception.message == "クエリエラー"
        assert exception.context == {}

    def test_create_query_exception_with_context(self):
        """コンテキスト付きのクエリ例外作成テスト"""
        exception = UserQueryException(
            "クエリエラー",
            user_id=1,
            target_user_id=2
        )

        assert str(exception) == "クエリエラー"
        assert exception.error_code == "USERQUERYEXCEPTION"
        assert exception.context["user_id"] == 1
        assert exception.context["target_user_id"] == 2
        assert exception.user_id == 1
        assert exception.target_user_id == 2


class TestProfileNotFoundException:
    """ProfileNotFoundExceptionのテスト"""

    def test_create_profile_not_found_exception(self):
        """プロフィールが見つからない例外の作成テスト"""
        exception = ProfileNotFoundException(1)

        assert str(exception) == "ユーザープロフィールが見つかりません: 1"
        assert exception.error_code == "PROFILE_NOT_FOUND"
        assert exception.context["user_id"] == 1
        assert exception.user_id == 1

    def test_profile_not_found_inheritance(self):
        """ProfileNotFoundExceptionの継承関係テスト"""
        exception = ProfileNotFoundException(1)
        assert isinstance(exception, UserQueryException)
        assert isinstance(exception, Exception)


class TestUserNotFoundException:
    """UserNotFoundExceptionのテスト"""

    def test_create_user_not_found_exception(self):
        """ユーザーが見つからない例外の作成テスト"""
        exception = UserNotFoundException(1)

        assert str(exception) == "ユーザーが見つかりません: 1"
        assert exception.error_code == "USER_NOT_FOUND"
        assert exception.context["user_id"] == 1
        assert exception.user_id == 1

    def test_user_not_found_inheritance(self):
        """UserNotFoundExceptionの継承関係テスト"""
        exception = UserNotFoundException(1)
        assert isinstance(exception, UserQueryException)
        assert isinstance(exception, Exception)


class TestInvalidUserIdException:
    """InvalidUserIdExceptionのテスト"""

    def test_create_invalid_user_id_exception(self):
        """無効なユーザーID例外の作成テスト"""
        exception = InvalidUserIdException(0)

        assert str(exception) == "無効なユーザーIDです: 0"
        assert exception.error_code == "INVALID_USER_ID"
        assert exception.context["user_id"] == 0
        assert exception.user_id == 0

    def test_invalid_user_id_inheritance(self):
        """InvalidUserIdExceptionの継承関係テスト"""
        exception = InvalidUserIdException(0)
        assert isinstance(exception, UserQueryException)
        assert isinstance(exception, Exception)


class TestProfileQueryException:
    """ProfileQueryExceptionのテスト"""

    def test_create_profile_query_exception(self):
        """プロフィールクエリ例外の作成テスト"""
        exception = ProfileQueryException("プロフィールクエリエラー")

        assert str(exception) == "プロフィールクエリエラー"
        assert exception.error_code == "PROFILE_QUERY_ERROR"
        assert exception.context == {}

    def test_create_profile_query_exception_with_context(self):
        """コンテキスト付きのプロフィールクエリ例外作成テスト"""
        exception = ProfileQueryException(
            "プロフィールクエリエラー",
            user_id=1,
            target_user_id=2
        )

        assert str(exception) == "プロフィールクエリエラー"
        assert exception.error_code == "PROFILE_QUERY_ERROR"
        assert exception.context["user_id"] == 1
        assert exception.context["target_user_id"] == 2
        assert exception.user_id == 1
        assert exception.target_user_id == 2

    def test_profile_query_inheritance(self):
        """ProfileQueryExceptionの継承関係テスト"""
        exception = ProfileQueryException("テスト")
        assert isinstance(exception, UserQueryException)
        assert isinstance(exception, Exception)


class TestRelationshipQueryException:
    """RelationshipQueryExceptionのテスト"""

    def test_create_relationship_query_exception(self):
        """関係性クエリ例外の作成テスト"""
        exception = RelationshipQueryException(
            "関係性クエリエラー",
            "follow",
            1
        )

        assert str(exception) == "関係性クエリエラー"
        assert exception.error_code == "RELATIONSHIP_QUERY_ERROR"
        assert exception.context["user_id"] == 1
        assert exception.relationship_type == "follow"
        assert exception.user_id == 1

    def test_relationship_query_inheritance(self):
        """RelationshipQueryExceptionの継承関係テスト"""
        exception = RelationshipQueryException("テスト", "follow", 1)
        assert isinstance(exception, UserQueryException)
        assert isinstance(exception, Exception)
