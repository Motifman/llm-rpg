"""
SNSアプリケーション層の基底例外テスト
"""
import pytest
from ai_rpg_world.application.social.exceptions.base_exception import ApplicationException, SystemErrorException


class TestApplicationException:
    """ApplicationExceptionのテスト"""

    def test_create_basic_exception(self):
        """基本的な例外の作成テスト"""
        exception = ApplicationException("テストメッセージ")

        assert str(exception) == "テストメッセージ"
        assert exception.error_code == "APPLICATIONEXCEPTION"
        assert exception.message == "テストメッセージ"
        assert exception.context == {}

    def test_create_exception_with_error_code(self):
        """エラーコード付きの例外作成テスト"""
        exception = ApplicationException("テストメッセージ", error_code="TEST_ERROR")

        assert str(exception) == "テストメッセージ"
        assert exception.error_code == "TEST_ERROR"
        assert exception.message == "テストメッセージ"

    def test_create_exception_with_context(self):
        """コンテキスト付きの例外作成テスト"""
        context = {"user_id": 1, "target_user_id": 2, "additional": "data"}
        exception = ApplicationException("テストメッセージ", **context)

        assert exception.context == context
        assert exception.user_id == 1
        assert exception.target_user_id == 2

    def test_create_exception_with_all_parameters(self):
        """全パラメータ付きの例外作成テスト"""
        context = {"user_id": 1, "target_user_id": 2}
        exception = ApplicationException(
            "テストメッセージ",
            error_code="CUSTOM_ERROR",
            **context
        )

        assert str(exception) == "テストメッセージ"
        assert exception.error_code == "CUSTOM_ERROR"
        assert exception.message == "テストメッセージ"
        assert exception.context == context
        assert exception.user_id == 1
        assert exception.target_user_id == 2


class TestSystemErrorException:
    """SystemErrorExceptionのテスト"""

    def test_create_basic_system_exception(self):
        """基本的なシステムエラーの作成テスト"""
        exception = SystemErrorException("システムエラー")

        assert str(exception) == "システムエラー"
        assert exception.error_code == "SYSTEM_ERROR"
        assert exception.message == "システムエラー"
        assert exception.context == {}
        assert exception.original_exception is None

    def test_create_system_exception_with_original(self):
        """元の例外付きのシステムエラー作成テスト"""
        original = ValueError("元のエラー")
        exception = SystemErrorException("システムエラー", original_exception=original)

        assert str(exception) == "システムエラー"
        assert exception.error_code == "SYSTEM_ERROR"
        assert exception.message == "システムエラー"
        assert exception.context["original_exception"] is original

    def test_system_exception_inheritance(self):
        """SystemErrorExceptionの継承関係テスト"""
        exception = SystemErrorException("テスト")
        assert isinstance(exception, ApplicationException)
        assert isinstance(exception, Exception)
