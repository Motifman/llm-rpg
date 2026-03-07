"""
相互作用コマンド関連の例外定義
"""

from typing import Optional

from ai_rpg_world.application.world.exceptions.base_exception import WorldApplicationException


class InteractionCommandException(WorldApplicationException):
    """相互作用コマンド関連の例外"""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        player_id: Optional[int] = None,
        target_world_object_id: Optional[int] = None,
        **context,
    ):
        all_context = context.copy()
        if player_id is not None:
            all_context["player_id"] = player_id
        if target_world_object_id is not None:
            all_context["target_world_object_id"] = target_world_object_id
        super().__init__(message, error_code, **all_context)


class InteractionPlayerNotFoundException(InteractionCommandException):
    def __init__(self, player_id: int):
        super().__init__(
            f"プレイヤーが見つかりません: {player_id}",
            "PLAYER_NOT_FOUND",
            player_id=player_id,
        )


class InteractionTargetNotFoundException(InteractionCommandException):
    def __init__(self, target_world_object_id: int):
        super().__init__(
            f"対象オブジェクトが見つかりません: {target_world_object_id}",
            "INTERACTION_TARGET_NOT_FOUND",
            target_world_object_id=target_world_object_id,
        )


class InteractionInvalidException(InteractionCommandException):
    def __init__(self, message: str, player_id: int, **context):
        super().__init__(
            message,
            "INTERACTION_INVALID",
            player_id=player_id,
            **context,
        )
