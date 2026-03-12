"""消費アイテム使用コマンド関連の例外定義"""

from typing import Optional
from ai_rpg_world.application.world.exceptions.base_exception import WorldApplicationException


class UseCommandException(WorldApplicationException):
    """消費アイテム使用コマンド関連の例外"""

    def __init__(
        self,
        message: str,
        error_code: str = "USE_ITEM_ERROR",
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


class ItemNotConsumableException(UseCommandException):
    """指定スロットのアイテムが消費可能でない場合の例外"""

    def __init__(self, player_id: int, slot_id: int):
        message = f"プレイヤー {player_id} のスロット {slot_id} のアイテムは消費できません"
        super().__init__(message, "ITEM_NOT_CONSUMABLE", player_id=player_id, slot_id=slot_id)


class PlayerDownedCannotUseItemException(UseCommandException):
    """ダウン状態で回復系アイテムを使用できない場合の例外"""

    def __init__(self, player_id: int, slot_id: int):
        message = f"プレイヤー {player_id} はダウン状態のためアイテムを使用できません"
        super().__init__(message, "PLAYER_DOWNED", player_id=player_id, slot_id=slot_id)


class ItemReservedForUseException(UseCommandException):
    """使用対象のアイテムが取引などで予約中の場合の例外"""

    def __init__(self, player_id: int, slot_id: int):
        message = f"プレイヤー {player_id} のスロット {slot_id} のアイテムは予約中で使えません"
        super().__init__(message, "ITEM_RESERVED", player_id=player_id, slot_id=slot_id)


class NoItemInSlotForUseException(UseCommandException):
    """使用時に指定スロットにアイテムがない場合の例外"""

    def __init__(self, player_id: int, slot_id: int):
        message = f"プレイヤー {player_id} のスロット {slot_id} にアイテムがありません"
        super().__init__(message, "NO_ITEM_IN_SLOT", player_id=player_id, slot_id=slot_id)


class UseItemPlayerNotFoundException(UseCommandException):
    """アイテム使用時にプレイヤーステータスが見つからない場合の例外"""

    def __init__(self, player_id: int):
        message = f"プレイヤー {player_id} のステータスが取得できません"
        super().__init__(message, "PLAYER_NOT_FOUND", player_id=player_id)
