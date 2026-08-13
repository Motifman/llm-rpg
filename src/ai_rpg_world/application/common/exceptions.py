"""
アプリケーション層の共通例外定義

全サービス共通の基底例外クラスを定義します。
各サービスはこれを継承してサービス固有の例外クラスを作成します。
"""

from typing import Any, Optional

from ai_rpg_world.domain.common.exception import DomainException


class ApplicationException(Exception):
    """アプリケーション層の共通基底例外クラス

    全てのアプリケーション層例外はこのクラスを継承します。
    """

    def __init__(self, message: str, cause: Optional[Exception] = None, **context):
        """
        Args:
            message: エラーメッセージ
            cause: 原因となった例外（ドメイン例外など）
            **context: 追加のコンテキスト情報
        """
        self.message = message
        self.cause = cause
        self.context = context
        super().__init__(message)


class SystemErrorException(ApplicationException):
    """システムエラーの場合の例外

    予期しない例外が発生した場合に使用します。
    ログ出力と適切なエラーレスポンスを返します。
    """

    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        """
        Args:
            message: エラーメッセージ
            original_exception: 元の例外
        """
        super().__init__(
            message,
            cause=original_exception,
            original_exception=original_exception
        )
        self.original_exception = original_exception


class CommandScopeException(ApplicationException):
    """CommandScopeの開始・確定・終了に関する共通例外。"""


class CommandScopeStateException(CommandScopeException):
    """CommandScopeの許可されていない状態遷移を表す。"""

    def __init__(self, *, current_state: str, attempted_operation: str) -> None:
        self.current_state = current_state
        self.attempted_operation = attempted_operation
        super().__init__(
            "CommandScopeの状態遷移が不正です: "
            f"state={current_state}, operation={attempted_operation}",
            current_state=current_state,
            attempted_operation=attempted_operation,
        )


class NestedCommandScopeException(CommandScopeException):
    """有効なCommandScope内で別のscopeを暗黙に開始したことを表す。"""

    def __init__(self) -> None:
        super().__init__(
            "有効なCommandScope内で別のCommandScopeは開始できません。"
            "現在のCommandContextへ明示的に参加してください。"
        )


class CommandRollbackException(CommandScopeException):
    """commandの主例外に加えてrollbackにも失敗したことを表す。"""

    def __init__(
        self,
        *,
        primary_error: BaseException,
        rollback_error: BaseException,
    ) -> None:
        self.primary_error = primary_error
        self.rollback_error = rollback_error
        super().__init__(
            "CommandScopeの失敗をrollbackできませんでした。",
            primary_error=primary_error,
            rollback_error=rollback_error,
        )
