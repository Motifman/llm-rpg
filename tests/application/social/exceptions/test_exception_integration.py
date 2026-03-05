"""
SNS例外の統合テスト（エンドツーエンドテスト）
DomainException のサブクラスのみ create_from_domain_exception に渡す設計を検証する。
"""
import pytest
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.sns.exception.user_profile_exceptions import (
    UserNotFoundException as DomainUserNotFoundException,
    UserIdValidationException,
)
from ai_rpg_world.domain.sns.exception.relationship_exceptions import (
    FollowException,
    BlockException,
)
from ai_rpg_world.application.social.exceptions.exception_factory import (
    ApplicationExceptionFactory,
)
from ai_rpg_world.application.social.exceptions.query.user_query_exception import (
    UserQueryException,
    UserNotFoundException,
    InvalidUserIdException,
)
from ai_rpg_world.application.social.exceptions.command.user_command_exception import (
    UserCommandException,
    UserCreationException,
)


class TestExceptionIntegration:
    """例外システムの統合テスト"""

    def test_domain_exception_to_application_exception_flow(self):
        """ドメイン例外からアプリケーション例外への変換フロー（正常系）"""
        # 1. ユーザー検索のドメイン例外（実ドメイン例外を使用）
        user_not_found = DomainUserNotFoundException(
            123, "User with id 123 not found"
        )
        app_exception = ApplicationExceptionFactory.create_from_domain_exception(
            user_not_found,
            user_id=456,
        )

        assert isinstance(app_exception, UserQueryException)
        assert app_exception.context["user_id"] == 123  # ドメイン例外から
        assert app_exception.user_id == 123  # 便利プロパティから
        assert str(app_exception) == "User with id 123 not found"

        # 2. 関係性のドメイン例外（実ドメイン例外を使用）
        follow_error = FollowException("Cannot follow user 2")
        follow_error.follower_id = 1
        follow_error.followee_id = 2
        follow_error.relationship_type = "follow"
        app_exception2 = ApplicationExceptionFactory.create_from_domain_exception(
            follow_error
        )

        assert isinstance(
            app_exception2, UserCommandException
        )  # マッピングで UserCommandException に変換
        assert app_exception2.context["relationship_type"] == "follow"
        assert str(app_exception2) == "Cannot follow user 2"

    def test_exception_factory_convenience_methods(self):
        """例外ファクトリの便利メソッドのテスト"""
        # UserNotFoundExceptionの作成
        user_not_found = ApplicationExceptionFactory.create_user_not_found_exception(123)
        assert isinstance(user_not_found, UserNotFoundException)
        assert user_not_found.user_id == 123
        assert str(user_not_found) == "ユーザーが見つかりません: 123"

        # InvalidUserIdExceptionの作成
        invalid_id = ApplicationExceptionFactory.create_invalid_user_id_exception(0)
        assert isinstance(invalid_id, InvalidUserIdException)
        assert invalid_id.user_id == 0
        assert str(invalid_id) == "無効なユーザーIDです: 0"

    def test_exception_context_propagation(self):
        """例外コンテキストの伝播テスト（正常系）"""
        domain_exc = BlockException("Complex domain error")
        domain_exc.user_id = 100
        domain_exc.relationship_type = "block"
        domain_exc.error_detail = "User is already blocked"

        app_exc = ApplicationExceptionFactory.create_from_domain_exception(
            domain_exc,
            user_id=200,
            target_user_id=300,
            additional_info="test",
        )

        assert app_exc.context["user_id"] == 100  # ドメイン例外から
        assert app_exc.context["target_user_id"] == 300  # パラメータから
        assert app_exc.context["relationship_type"] == "block"  # ドメイン例外から
        assert app_exc.context["additional_info"] == "test"  # パラメータから
        assert (
            app_exc.context["error_detail"] == "User is already blocked"
        )  # ドメイン例外から

    def test_exception_chain_preservation(self):
        """例外チェーンの保存テスト（正常系）"""
        domain_exception = DomainException("ドメインエラー")

        app_exception = ApplicationExceptionFactory.create_from_domain_exception(
            domain_exception
        )

        assert app_exception.__cause__ is domain_exception

    def test_non_domain_exception_raises_type_error(self):
        """DomainException 以外を渡すと TypeError（例外系）"""
        with pytest.raises(TypeError) as exc_info:
            ApplicationExceptionFactory.create_from_domain_exception(
                RuntimeError("ドメインエラー")
            )
        assert "domain_exception must be a DomainException" in str(exc_info.value)

    def test_exception_mapping_completeness(self):
        """例外マッピングの完全性テスト"""
        mapping = ApplicationExceptionFactory.EXCEPTION_MAPPING

        # 主要なカテゴリの例外がマッピングされていることを確認
        user_exceptions = [k for k in mapping.keys() if "User" in k]
        relationship_exceptions = [k for k in mapping.keys() if any(word in k for word in ["Follow", "Block", "Subscribe", "Relationship"])]

        # 各カテゴリに複数の例外がマッピングされていることを確認
        assert len(user_exceptions) >= 5, f"ユーザー関連例外が少ない: {user_exceptions}"
        assert len(relationship_exceptions) >= 10, f"関係性関連例外が少ない: {relationship_exceptions}"

        # 全てのマッピング値が適切な例外クラスであることを確認
        for exception_name, exception_class in mapping.items():
            assert issubclass(exception_class, Exception), f"{exception_name}のマッピングが不正: {exception_class}"

    def test_real_world_usage_scenario(self):
        """実世界での使用シナリオテスト（正常・例外系）"""
        # ドメイン層が DomainException を投げ、サービスがアプリ例外に変換する流れ

        class UserRepository:
            def find_by_id(self, user_id):
                if user_id <= 0:
                    raise UserIdValidationException(
                        user_id, f"Invalid user id: {user_id}"
                    )
                if user_id == 999:
                    raise DomainUserNotFoundException(
                        999, f"User {user_id} not found in database"
                    )
                return f"user_{user_id}"

        repo = UserRepository()

        def get_user_profile(user_id):
            try:
                user = repo.find_by_id(user_id)
                return f"Profile of {user}"
            except DomainException as e:
                app_exc = ApplicationExceptionFactory.create_from_domain_exception(
                    e,
                    user_id=user_id,
                )
                raise app_exc

        # 正常系
        profile = get_user_profile(1)
        assert profile == "Profile of user_1"

        # 無効なユーザーID（ドメイン例外 → アプリ例外）
        with pytest.raises(UserQueryException) as exc_info:
            get_user_profile(0)
        assert exc_info.value.context["user_id"] == 0
        assert "Invalid user id: 0" in str(exc_info.value)

        # 存在しないユーザー（ドメイン例外 → アプリ例外）
        with pytest.raises(UserQueryException) as exc_info:
            get_user_profile(999)
        assert exc_info.value.context["user_id"] == 999
        assert "User 999 not found in database" in str(exc_info.value)
