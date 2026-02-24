"""
クエストアプリケーション層の基底例外定義
"""

from typing import Optional, Any


class QuestApplicationException(Exception):
    """クエストアプリケーション層の基底例外"""

    def __init__(self, message: str, error_code: Optional[str] = None, **context):
        self.message = message
        self.error_code = error_code or self.__class__.__name__.upper()
        self.context = context
        super().__init__(message)
        self.user_id = context.get("user_id")
        self.quest_id = context.get("quest_id")


class QuestSystemErrorException(QuestApplicationException):
    """クエストシステムエラーの場合の例外"""

    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        context = {}
        if original_exception:
            context["original_exception"] = original_exception
        super().__init__(message, error_code="QUEST_SYSTEM_ERROR", **context)
        self.original_exception = original_exception


class QuestRewardGrantException(QuestApplicationException):
    """クエスト報酬付与に失敗した場合の例外（イベント再配送・リトライ対象）"""

    def __init__(
        self,
        message: str,
        quest_id: Optional[int] = None,
        acceptor_player_id: Optional[int] = None,
        **context,
    ):
        ctx = dict(context)
        if quest_id is not None:
            ctx["quest_id"] = quest_id
        if acceptor_player_id is not None:
            ctx["acceptor_player_id"] = acceptor_player_id
        super().__init__(
            message,
            error_code="QUEST_REWARD_GRANT_ERROR",
            **ctx,
        )
        self.quest_id = quest_id
        self.acceptor_player_id = acceptor_player_id
