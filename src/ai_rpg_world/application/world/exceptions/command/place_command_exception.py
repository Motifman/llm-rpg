"""
設置・破壊コマンド関連の例外定義
"""

from typing import Optional
from ai_rpg_world.application.world.exceptions.base_exception import WorldApplicationException


class PlaceCommandException(WorldApplicationException):
    """設置・破壊コマンド関連の例外"""

    def __init__(
        self,
        message: str,
        error_code: str = None,
        player_id: Optional[int] = None,
        spot_id: Optional[int] = None,
        slot_id: Optional[int] = None,
        **context,
    ):
        all_context = context.copy()
        if player_id is not None:
            all_context["player_id"] = player_id
        if spot_id is not None:
            all_context["spot_id"] = spot_id
        if slot_id is not None:
            all_context["slot_id"] = slot_id
        super().__init__(message, error_code, **all_context)


class ItemNotPlaceableException(PlaceCommandException):
    """指定スロットのアイテムが設置可能でない場合の例外"""

    def __init__(self, player_id: int, slot_id: int):
        message = f"プレイヤー {player_id} のスロット {slot_id} のアイテムは設置できません"
        super().__init__(message, "ITEM_NOT_PLACEABLE", player_id=player_id, slot_id=slot_id)


class NoItemInSlotException(PlaceCommandException):
    """指定スロットにアイテムがない場合の例外"""

    def __init__(self, player_id: int, slot_id: int):
        message = f"プレイヤー {player_id} のスロット {slot_id} にアイテムがありません"
        super().__init__(message, "NO_ITEM_IN_SLOT", player_id=player_id, slot_id=slot_id)


class PlacementSpotNotFoundException(PlaceCommandException):
    """マップまたはプレイヤー位置が見つからない場合の例外"""

    def __init__(self, player_id: int, spot_id: int):
        message = f"プレイヤー {player_id} のスポット {spot_id} のマップまたは位置が取得できません"
        super().__init__(message, "PLACEMENT_SPOT_NOT_FOUND", player_id=player_id, spot_id=spot_id)


class PlacementBlockedException(PlaceCommandException):
    """設置先がブロックされている場合の例外"""

    def __init__(self, player_id: int, spot_id: int):
        message = f"プレイヤー {player_id} の前方は設置できません（ブロックされているか範囲外です）"
        super().__init__(message, "PLACEMENT_BLOCKED", player_id=player_id, spot_id=spot_id)


class NoPlaceableInFrontException(PlaceCommandException):
    """破壊対象の設置物が前方にない場合の例外"""

    def __init__(self, player_id: int, spot_id: int):
        message = f"プレイヤー {player_id} の前方に破壊可能な設置物がありません"
        super().__init__(message, "NO_PLACEABLE_IN_FRONT", player_id=player_id, spot_id=spot_id)
