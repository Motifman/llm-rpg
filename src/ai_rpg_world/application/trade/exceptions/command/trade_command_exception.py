"""
取引コマンド関連の例外定義
"""

from typing import Optional
from ai_rpg_world.application.trade.exceptions.base_exception import TradeApplicationException


class TradeCommandException(TradeApplicationException):
    """取引コマンド関連の例外"""

    def __init__(self, message: str, error_code: str = None, user_id: Optional[int] = None, trade_id: Optional[int] = None, **context):
        all_context = context.copy()
        if user_id is not None:
            all_context['user_id'] = user_id
        if trade_id is not None:
            all_context['trade_id'] = trade_id
        super().__init__(message, error_code, **all_context)


class TradeCreationException(TradeCommandException):
    """取引作成関連の例外"""

    def __init__(self, message: str, user_id: int):
        super().__init__(message, "TRADE_CREATION_ERROR", user_id=user_id)


class TradeNotFoundForCommandException(TradeCommandException):
    """コマンド実行時に取引が見つからない場合の例外"""

    def __init__(self, trade_id: int, command_name: str):
        message = f"コマンド '{command_name}' の実行時に取引が見つかりません: {trade_id}"
        super().__init__(message, "TRADE_NOT_FOUND_FOR_COMMAND", trade_id=trade_id)


class TradeAccessDeniedException(TradeCommandException):
    """取引アクセス権限がない場合の例外"""

    def __init__(self, trade_id: int, user_id: int, action: str):
        message = f"取引 {trade_id} に対するアクション '{action}' の実行権限がありません: ユーザー {user_id}"
        super().__init__(message, "TRADE_ACCESS_DENIED", trade_id=trade_id, user_id=user_id)
