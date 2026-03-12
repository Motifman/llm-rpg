"""消費アイテム効果ハンドラ関連の例外定義"""

from typing import Optional

from ai_rpg_world.application.world.exceptions.base_exception import WorldApplicationException


class ConsumableEffectException(WorldApplicationException):
    """消費アイテム効果適用関連の例外"""

    def __init__(
        self,
        message: str,
        error_code: str = "CONSUMABLE_EFFECT_ERROR",
        player_id: Optional[int] = None,
        item_spec_id: Optional[int] = None,
        **context,
    ):
        all_context = context.copy()
        if player_id is not None:
            all_context["player_id"] = player_id
        if item_spec_id is not None:
            all_context["item_spec_id"] = item_spec_id
        super().__init__(message, error_code, **all_context)


class ItemSpecNotFoundForConsumableEffectException(ConsumableEffectException):
    """消費効果適用時に ItemSpec が見つからない場合の例外"""

    def __init__(self, item_spec_id: int):
        message = f"消費効果適用: アイテム仕様 {item_spec_id} が見つかりません"
        super().__init__(message, "ITEM_SPEC_NOT_FOUND", item_spec_id=item_spec_id)


class PlayerNotFoundForConsumableEffectException(ConsumableEffectException):
    """消費効果適用時に PlayerStatus が見つからない場合の例外"""

    def __init__(self, player_id: int):
        message = f"消費効果適用: プレイヤー {player_id} のステータスが見つかりません"
        super().__init__(message, "PLAYER_NOT_FOUND", player_id=player_id)


class ConsumeEffectMissingException(ConsumableEffectException):
    """ConsumableUsedEvent を受け取ったが ItemSpec に consume_effect が設定されていない場合の例外"""

    def __init__(self, item_spec_id: int):
        message = f"消費効果適用: アイテム仕様 {item_spec_id} に consume_effect が設定されていません"
        super().__init__(message, "CONSUME_EFFECT_MISSING", item_spec_id=item_spec_id)
