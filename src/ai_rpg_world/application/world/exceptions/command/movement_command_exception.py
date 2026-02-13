"""
移動コマンド関連の例外定義
"""

from typing import Optional
from ai_rpg_world.application.world.exceptions.base_exception import WorldApplicationException


class MovementCommandException(WorldApplicationException):
    """移動コマンド関連の例外"""

    def __init__(
        self, 
        message: str, 
        error_code: str = None, 
        player_id: Optional[int] = None, 
        spot_id: Optional[int] = None, 
        **context
    ):
        all_context = context.copy()
        if player_id is not None:
            all_context['player_id'] = player_id
        if spot_id is not None:
            all_context['spot_id'] = spot_id
        super().__init__(message, error_code, **all_context)


class PlayerNotFoundException(MovementCommandException):
    """プレイヤーが見つからない場合の例外"""

    def __init__(self, player_id: int):
        message = f"プレイヤーが見つかりません: {player_id}"
        super().__init__(message, "PLAYER_NOT_FOUND", player_id=player_id)


class MapNotFoundException(MovementCommandException):
    """マップが見つからない場合の例外"""

    def __init__(self, spot_id: int):
        message = f"スポット {spot_id} のマップが見つかりません"
        super().__init__(message, "MAP_NOT_FOUND", spot_id=spot_id)


class MovementInvalidException(MovementCommandException):
    """移動が不正な場合の例外"""

    def __init__(self, message: str, player_id: int, **context):
        super().__init__(message, "MOVEMENT_INVALID", player_id=player_id, **context)


class PlayerStaminaExhaustedException(MovementInvalidException):
    """スタミナ不足による移動不可"""

    def __init__(self, player_id: int, required: float, current: float):
        message = f"スタミナが不足しています (必要: {required}, 現在: {current})"
        super().__init__(message, player_id, required=required, current=current)


class PathBlockedException(MovementInvalidException):
    """障害物による移動不可"""

    def __init__(self, player_id: int, coordinate: dict):
        message = f"座標 {coordinate} は通行できません"
        super().__init__(message, player_id, blocked_coordinate=coordinate)


class ActorBusyException(MovementInvalidException):
    """ビジー状態による移動不可"""

    def __init__(self, player_id: int, busy_until: int):
        message = f"現在行動中です (完了まで残り: {busy_until} ticks)"
        super().__init__(message, player_id, busy_until=busy_until)


class MapTransitionInvalidException(MovementInvalidException):
    """不正なマップ遷移"""

    def __init__(self, player_id: int, message: str):
        super().__init__(message, player_id)


class GatewayObjectNotFoundException(MovementCommandException):
    """ゲートウェイ通過時にマップ上にオブジェクトが存在しない場合の例外"""

    def __init__(self, object_id: int, spot_id: int):
        message = f"ゲートウェイ通過対象のオブジェクトがマップ上に存在しません: object_id={object_id}, spot_id={spot_id}"
        super().__init__(message, "GATEWAY_OBJECT_NOT_FOUND", spot_id=spot_id)


class GatewayMonsterNotFoundException(MovementCommandException):
    """ゲートウェイ通過時にワールドオブジェクトIDに紐づくモンスターが見つからない場合の例外"""

    def __init__(self, world_object_id: int):
        message = f"ゲートウェイ通過対象のモンスターが見つかりません: world_object_id={world_object_id}"
        super().__init__(message, "GATEWAY_MONSTER_NOT_FOUND")
