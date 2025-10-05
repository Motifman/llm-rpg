"""
アプリケーション層の基底例外定義
"""

from typing import Optional, Any, Dict


class ApplicationException(Exception):
    """アプリケーション層の基底例外"""

    def __init__(self, message: str, error_code: Optional[str] = None, **context):
        """
        統一されたアプリケーション例外コンストラクタ

        Args:
            message: エラーメッセージ
            error_code: エラーコード（指定されない場合はクラス名を大文字で使用）
            **context: 任意のコンテキスト情報（user_id, target_user_idなど）
        """
        self.message = message
        self.error_code = error_code or self.__class__.__name__.upper()
        self.context = context  # コンテキスト情報を保持
        super().__init__(message)

        # 便利なプロパティとしてコンテキストから主要な値を抽出
        self.user_id = context.get('user_id')
        self.target_user_id = context.get('target_user_id')


class SystemErrorException(ApplicationException):
    """システムエラーの場合の例外"""

    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        context = {}
        if original_exception:
            context['original_exception'] = original_exception
        super().__init__(message, error_code="SYSTEM_ERROR", **context)
        self.original_exception = original_exception
