"""
SNS例外ファクトリのテスト
"""
import pytest
from unittest.mock import Mock
from ai_rpg_world.application.social.exceptions.exception_factory import ApplicationExceptionFactory
from ai_rpg_world.application.social.exceptions.base_exception import ApplicationException
from ai_rpg_world.application.social.exceptions.query.user_query_exception import (
    UserQueryException,
    UserNotFoundException,
    InvalidUserIdException,
    ProfileNotFoundException,
)
from ai_rpg_world.application.social.exceptions.command.user_command_exception import (
    UserCommandException,
)


class TestApplicationExceptionFactory:
    """ApplicationExceptionFactoryのテスト"""

    def test_create_from_domain_exception_mapped(self):
        """マッピングされたドメイン例外からの変換テスト"""
        # Mockドメイン例外
        class MockUserNotFoundException(Exception):
            def __init__(self):
                super().__init__("User not found")

        domain_exception = MockUserNotFoundException()
        app_exception = ApplicationExceptionFactory.create_from_domain_exception(domain_exception)

        # マッピングでUserQueryExceptionに変換されるはず
        assert isinstance(app_exception, UserQueryException)
        assert str(app_exception) == "User not found"
        assert app_exception.error_code == "MOCKUSERNOTFOUNDEXCEPTION"
        assert app_exception.__cause__ is domain_exception

    def test_create_from_domain_exception_not_mapped(self):
        """マッピングされていないドメイン例外からの変換テスト"""
        # Mockドメイン例外（マッピングに存在しない）
        class MockUnknownException(Exception):
            def __init__(self):
                super().__init__("Unknown error")

        domain_exception = MockUnknownException()
        app_exception = ApplicationExceptionFactory.create_from_domain_exception(domain_exception)

        # デフォルトでUserQueryExceptionに変換されるはず
        assert isinstance(app_exception, UserQueryException)
        assert str(app_exception) == "Unknown error"
        assert app_exception.error_code == "MOCKUNKNOWNEXCEPTION"

    def test_create_from_domain_exception_with_context(self):
        """コンテキスト付きのドメイン例外からの変換テスト"""
        # Mockドメイン例外
        class MockDomainExceptionWithUserId(Exception):
            def __init__(self, user_id):
                self.user_id = user_id
                super().__init__(f"Error for user {user_id}")

        domain_exception = MockDomainExceptionWithUserId(123)
        app_exception = ApplicationExceptionFactory.create_from_domain_exception(
            domain_exception,
            user_id=456,
            target_user_id=789
        )

        assert isinstance(app_exception, UserQueryException)
        assert app_exception.context["user_id"] == 123  # ドメイン例外から
        assert app_exception.context["target_user_id"] == 789
        # ドメイン例外のuser_idが優先される

    def test_create_from_domain_exception_with_relationship_type(self):
        """関係性タイプ付きのドメイン例外からの変換テスト"""
        # Mockドメイン例外
        class MockRelationshipException(Exception):
            def __init__(self, relationship_type):
                self.relationship_type = relationship_type
                super().__init__(f"Relationship error: {relationship_type}")

        domain_exception = MockRelationshipException("follow")
        app_exception = ApplicationExceptionFactory.create_from_domain_exception(domain_exception)

        assert isinstance(app_exception, UserQueryException)
        assert app_exception.context["relationship_type"] == "follow"

    def test_create_from_domain_exception_constructor_fallback(self):
        """コンストラクタが失敗した場合のフォールバックテスト"""
        # 特殊なコンストラクタを持つMockドメイン例外
        class MockSpecialException(Exception):
            def __init__(self):
                super().__init__("Special error")

        domain_exception = MockSpecialException()
        app_exception = ApplicationExceptionFactory.create_from_domain_exception(domain_exception)

        # フォールバックで基本コンストラクタが使用されるはず
        assert isinstance(app_exception, UserQueryException)
        assert str(app_exception) == "Special error"

    def test_create_user_not_found_exception(self):
        """UserNotFoundException作成のテスト"""
        exception = ApplicationExceptionFactory.create_user_not_found_exception(123)

        assert isinstance(exception, UserNotFoundException)
        assert str(exception) == "ユーザーが見つかりません: 123"
        assert exception.user_id == 123

    def test_create_invalid_user_id_exception(self):
        """InvalidUserIdException作成のテスト"""
        exception = ApplicationExceptionFactory.create_invalid_user_id_exception(0)

        assert isinstance(exception, InvalidUserIdException)
        assert str(exception) == "無効なユーザーIDです: 0"
        assert exception.user_id == 0

    def test_create_profile_not_found_exception(self):
        """ProfileNotFoundException作成のテスト"""
        exception = ApplicationExceptionFactory.create_profile_not_found_exception(123)

        assert isinstance(exception, ProfileNotFoundException)
        assert str(exception) == "ユーザープロフィールが見つかりません: 123"
        assert exception.user_id == 123

    def test_exception_mapping_coverage(self):
        """例外マッピングのカバレッジテスト"""
        # 主要なマッピング項目が含まれていることを確認
        mapping = ApplicationExceptionFactory.EXCEPTION_MAPPING

        # 主要なマッピングが含まれていることを確認
        assert "UserNotFoundException" in mapping
        assert "UserIdValidationException" in mapping
        assert "FollowException" in mapping
        assert "BlockException" in mapping
        assert "SubscribeException" in mapping

        # マッピング値が正しいことを確認
        assert mapping["UserNotFoundException"] == UserQueryException
        assert mapping["UserIdValidationException"] == UserQueryException

    def test_exception_mapping_completeness(self):
        """例外マッピングの完全性テスト"""
        mapping = ApplicationExceptionFactory.EXCEPTION_MAPPING

        # 少なくとも主要な例外タイプがマッピングされていることを確認
        user_exceptions = [k for k in mapping.keys() if "User" in k]
        relationship_exceptions = [k for k in mapping.keys() if "Relationship" in k or "Follow" in k or "Block" in k or "Subscribe" in k]

        assert len(user_exceptions) > 0, "ユーザー関連の例外マッピングが存在しない"
        assert len(relationship_exceptions) > 0, "関係性関連の例外マッピングが存在しない"
