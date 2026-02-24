"""会話コマンド関連の例外"""
from typing import Optional

from ai_rpg_world.application.conversation.exceptions.base_exception import (
    ConversationApplicationException,
)


class ConversationCommandException(ConversationApplicationException):
    """会話コマンド関連の例外"""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        player_id: Optional[int] = None,
        npc_id_value: Optional[int] = None,
        **context,
    ):
        all_context = dict(context)
        if player_id is not None:
            all_context["player_id"] = player_id
        if npc_id_value is not None:
            all_context["npc_id_value"] = npc_id_value
        super().__init__(message, error_code, **all_context)


class ConversationNotFoundForCommandException(ConversationCommandException):
    """コマンド実行時に会話セッションが見つからない場合の例外"""

    def __init__(self, player_id: int, npc_id_value: int, command_name: str):
        message = (
            f"コマンド '{command_name}' の実行時に会話セッションが見つかりません: "
            f"player_id={player_id}, npc_id_value={npc_id_value}"
        )
        super().__init__(
            message,
            "CONVERSATION_NOT_FOUND_FOR_COMMAND",
            player_id=player_id,
            npc_id_value=npc_id_value,
        )


class DialogueTreeNotFoundException(ConversationCommandException):
    """ダイアログツリーが見つからない場合の例外"""

    def __init__(self, dialogue_tree_id: int):
        message = f"ダイアログツリーが見つかりません: dialogue_tree_id={dialogue_tree_id}"
        super().__init__(message, "DIALOGUE_TREE_NOT_FOUND")


class DialogueNodeNotFoundException(ConversationCommandException):
    """ダイアログノードが見つからない場合の例外"""

    def __init__(self, tree_id: int, node_id: int):
        message = f"ダイアログノードが見つかりません: tree_id={tree_id}, node_id={node_id}"
        super().__init__(message, "DIALOGUE_NODE_NOT_FOUND")


class NoActiveSessionException(ConversationCommandException):
    """アクティブな会話セッションがない場合の例外"""

    def __init__(self, player_id: int, npc_id_value: int):
        message = (
            f"アクティブな会話セッションがありません: "
            f"player_id={player_id}, npc_id_value={npc_id_value}"
        )
        super().__init__(
            message,
            "NO_ACTIVE_CONVERSATION_SESSION",
            player_id=player_id,
            npc_id_value=npc_id_value,
        )
