"""
アプリケーション例外ファクトリ
ドメイン例外から適切なアプリケーション例外を生成する
"""

from typing import Optional, Dict, Type, Any, Tuple
from src.application.sns.exceptions.base_exception import ApplicationException
from src.application.sns.exceptions.query.user_query_exception import (
    UserQueryException,
    ProfileNotFoundException,
    UserNotFoundException,
    InvalidUserIdException,
    ProfileQueryException,
    RelationshipQueryException,
)
from src.application.sns.exceptions.command.user_command_exception import (
    UserCommandException,
    UserCreationException,
    UserProfileUpdateException,
)
from src.application.sns.exceptions.command.relationship_command_exception import (
    UserFollowException,
    UserBlockException,
    UserSubscribeException,
)


class ApplicationExceptionFactory:
    """アプリケーション例外のファクトリクラス"""

    # ドメイン例外からアプリケーション例外へのマッピング
    # 既存のマッピングを維持しつつ、統一されたインターフェースを提供
    EXCEPTION_MAPPING: Dict[str, Type[ApplicationException]] = {
        # ユーザー関連例外
        "UserNotFoundException": UserQueryException,
        "UserIdValidationException": UserQueryException,
        "UserNameValidationException": UserCommandException,
        "DisplayNameValidationException": UserCommandException,
        "BioValidationException": UserCommandException,
        "ProfileUpdateValidationException": UserCommandException,

        # 関係性関連例外
        "RelationshipQueryException": RelationshipQueryException,
        "FollowException": UserCommandException,
        "CannotFollowBlockedUserException": UserCommandException,
        "CannotUnfollowNotFollowedUserException": UserCommandException,
        "BlockException": UserCommandException,
        "CannotBlockAlreadyBlockedUserException": UserCommandException,
        "CannotUnblockNotBlockedUserException": UserCommandException,
        "SubscribeException": UserCommandException,
        "CannotSubscribeAlreadySubscribedUserException": UserCommandException,
        "CannotSubscribeBlockedUserException": UserCommandException,
        "CannotSubscribeNotFollowedUserException": UserCommandException,
        "CannotUnsubscribeNotSubscribedUserException": UserCommandException,

        # セルフ操作関連例外
        "SelfFollowException": UserCommandException,
        "SelfUnfollowException": UserCommandException,
        "SelfBlockException": UserCommandException,
        "SelfUnblockException": UserCommandException,
        "SelfSubscribeException": UserCommandException,
        "SelfUnsubscribeException": UserCommandException,
    }

    @classmethod
    def create_from_domain_exception(
        cls,
        domain_exception: Exception,
        user_id: Optional[int] = None,
        target_user_id: Optional[int] = None,
        **additional_context
    ) -> ApplicationException:
        """
        ドメイン例外から適切なアプリケーション例外を作成

        Args:
            domain_exception: ドメイン例外
            user_id: ユーザーID
            target_user_id: 対象ユーザーID
            **additional_context: 追加のコンテキスト情報

        Returns:
            適切なアプリケーション例外
        """
        # ドメイン例外から情報を抽出
        domain_class_name = domain_exception.__class__.__name__

        # マッピングから適切なアプリケーション例外クラスを取得
        app_exception_class = cls.EXCEPTION_MAPPING.get(domain_class_name)

        if app_exception_class is None:
            # デフォルトの汎用例外（マッピングにない場合）
            app_exception_class = UserQueryException

        # コンテキストを構築
        context = additional_context.copy()

        # user_id, target_user_idをコンテキストに追加
        if user_id is not None:
            context['user_id'] = user_id
        if target_user_id is not None:
            context['target_user_id'] = target_user_id

        # ドメイン例外から特定のフィールドを抽出してコンテキストに追加
        if hasattr(domain_exception, 'user_id'):
            context['user_id'] = domain_exception.user_id
        if hasattr(domain_exception, 'relationship_type'):
            context['relationship_type'] = domain_exception.relationship_type

        # ドメイン例外の他の属性もコンテキストに追加
        domain_attrs = ['error_detail', 'target_user_id', 'follower_id', 'followee_id']
        for attr in domain_attrs:
            if hasattr(domain_exception, attr) and attr not in context:
                context[attr] = getattr(domain_exception, attr)

        # アプリケーション例外を作成
        try:
            app_exception = app_exception_class(
                message=str(domain_exception),
                error_code=domain_class_name.upper(),
                **context
            )
        except TypeError:
            # コンストラクタが新しいシグネチャに対応していない場合のフォールバック
            app_exception = app_exception_class(
                message=str(domain_exception),
                **context
            )

        # 例外チェーニング
        app_exception.__cause__ = domain_exception

        return app_exception

    @classmethod
    def create_user_not_found_exception(cls, user_id: int) -> UserNotFoundException:
        """UserNotFoundExceptionを作成"""
        return UserNotFoundException(user_id)

    @classmethod
    def create_invalid_user_id_exception(cls, user_id: int) -> InvalidUserIdException:
        """InvalidUserIdExceptionを作成"""
        return InvalidUserIdException(user_id)

    @classmethod
    def create_profile_not_found_exception(cls, user_id: int) -> ProfileNotFoundException:
        """ProfileNotFoundExceptionを作成"""
        return ProfileNotFoundException(user_id)
