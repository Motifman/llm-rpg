"""追跡コマンド関連の例外定義"""

from typing import Optional

from ai_rpg_world.application.world.exceptions.base_exception import WorldApplicationException


class PursuitCommandException(WorldApplicationException):
    """追跡コマンド関連の例外。"""

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


class PursuitPlayerNotFoundException(PursuitCommandException):
    def __init__(self, player_id: int):
        super().__init__(
            f"プレイヤーが見つかりません: {player_id}",
            "PLAYER_NOT_FOUND",
            player_id=player_id,
        )


class PursuitActorNotPlacedException(PursuitCommandException):
    def __init__(self, player_id: int):
        super().__init__(
            "プレイヤーの現在地を取得できません。",
            "PLAYER_NOT_PLACED",
            player_id=player_id,
        )


class PursuitActorObjectNotFoundException(PursuitCommandException):
    def __init__(self, player_id: int):
        super().__init__(
            f"プレイヤーに対応するアクターがマップ上に存在しません: {player_id}",
            "PLAYER_ACTOR_NOT_FOUND",
            player_id=player_id,
        )


class PursuitTargetNotFoundException(PursuitCommandException):
    def __init__(self, player_id: int, target_world_object_id: int):
        super().__init__(
            f"追跡対象が見つかりません: {target_world_object_id}",
            "PURSUIT_TARGET_NOT_FOUND",
            player_id=player_id,
            target_world_object_id=target_world_object_id,
        )


class PursuitTargetNotVisibleException(PursuitCommandException):
    def __init__(self, player_id: int, target_world_object_id: int):
        super().__init__(
            f"現在見えていない対象は追跡開始できません: {target_world_object_id}",
            "PURSUIT_TARGET_NOT_VISIBLE",
            player_id=player_id,
            target_world_object_id=target_world_object_id,
        )


class PursuitInvalidTargetKindException(PursuitCommandException):
    def __init__(self, player_id: int, target_world_object_id: int, target_kind: str):
        super().__init__(
            f"追跡対象にできません: kind={target_kind}",
            "PURSUIT_INVALID_TARGET_KIND",
            player_id=player_id,
            target_world_object_id=target_world_object_id,
            target_kind=target_kind,
        )


class PursuitSelfTargetException(PursuitCommandException):
    def __init__(self, player_id: int):
        super().__init__(
            "自分自身は追跡できません。",
            "PURSUIT_SELF_TARGET",
            player_id=player_id,
            target_world_object_id=player_id,
        )


class PursuitActorBusyException(PursuitCommandException):
    def __init__(self, player_id: int, busy_until_tick: int):
        super().__init__(
            f"現在行動中のため追跡開始できません (完了まで残り: {busy_until_tick} ticks)",
            "PURSUIT_ACTOR_BUSY",
            player_id=player_id,
            busy_until_tick=busy_until_tick,
        )
