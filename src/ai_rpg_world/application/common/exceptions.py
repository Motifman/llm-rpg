"""
アプリケーション層の共通例外定義

全サービス共通の基底例外クラスを定義します。
各サービスはこれを継承してサービス固有の例外クラスを作成します。
"""

from typing import Optional, Any
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
