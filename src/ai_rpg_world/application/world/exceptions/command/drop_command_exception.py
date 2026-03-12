"""意図的ドロップコマンド関連の例外定義"""

from typing import Optional
from ai_rpg_world.application.world.exceptions.base_exception import WorldApplicationException


class DropCommandException(WorldApplicationException):
    """意図的ドロップコマンド関連の例外"""

    def __init__(
        self,
        message: str,
        error_code: str,
        player_id: Optional[int] = None,
        slot_id: Optional[int] = None,
        **context,
    ):
        all_context = context.copy()
        if player_id is not None:
            all_context["player_id"] = player_id
        if slot_id is not None:
            all_context["slot_id"] = slot_id
        super().__init__(message, error_code, **all_context)


class NoItemInSlotForDropException(DropCommandException):
    """ドロップ時に指定スロットにアイテムがない場合の例外"""

    def __init__(self, player_id: int, slot_id: int):
        message = f"プレイヤー {player_id} のスロット {slot_id} にアイテムがありません"
        super().__init__(message, "NO_ITEM_IN_SLOT", player_id=player_id, slot_id=slot_id)


class ItemReservedForDropException(DropCommandException):
    """ドロップ対象のアイテムが取引などで予約中の場合の例外"""

    def __init__(self, player_id: int, slot_id: int):
        message = f"プレイヤー {player_id} のスロット {slot_id} のアイテムは予約中で捨てられません"
        super().__init__(message, "ITEM_RESERVED", player_id=player_id, slot_id=slot_id)


class DropPlayerOrInventoryNotFoundException(DropCommandException):
    """ドロップ時にプレイヤーステータスまたはインベントリが見つからない場合の例外"""

    def __init__(self, player_id: int):
        message = f"プレイヤー {player_id} のステータスまたはインベントリが取得できません"
        super().__init__(message, "PLAYER_OR_INVENTORY_NOT_FOUND", player_id=player_id)
