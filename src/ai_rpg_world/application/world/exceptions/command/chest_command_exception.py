"""
チェストコマンド関連の例外定義
"""

from typing import Optional
from ai_rpg_world.application.world.exceptions.base_exception import WorldApplicationException


class ChestCommandException(WorldApplicationException):
    """チェストコマンド関連の例外"""

    def __init__(
        self,
        message: str,
        error_code: str = None,
        player_id: Optional[int] = None,
        spot_id: Optional[int] = None,
        chest_id: Optional[int] = None,
        item_instance_id: Optional[int] = None,
        **context,
    ):
        all_context = context.copy()
        if player_id is not None:
            all_context["player_id"] = player_id
        if spot_id is not None:
            all_context["spot_id"] = spot_id
        if chest_id is not None:
            all_context["chest_id"] = chest_id
        if item_instance_id is not None:
            all_context["item_instance_id"] = item_instance_id
        super().__init__(message, error_code, **all_context)


class ChestNotFoundException(ChestCommandException):
    """チェストまたはマップが見つからない場合の例外"""

    def __init__(self, spot_id: int, chest_id: int):
        message = f"スポット {spot_id} のマップまたはチェスト {chest_id} が見つかりません"
        super().__init__(message, "CHEST_NOT_FOUND", spot_id=spot_id, chest_id=chest_id)


class ItemNotInPlayerInventoryException(ChestCommandException):
    """プレイヤーが指定アイテムを所持していない場合の例外"""

    def __init__(self, player_id: int, item_instance_id: int):
        message = f"プレイヤー {player_id} はアイテム {item_instance_id} を所持していません"
        super().__init__(
            message,
            "ITEM_NOT_IN_INVENTORY",
            player_id=player_id,
            item_instance_id=item_instance_id,
        )


class PlayerInventoryNotFoundException(ChestCommandException):
    """プレイヤーインベントリが見つからない場合の例外"""

    def __init__(self, player_id: int):
        message = f"プレイヤー {player_id} のインベントリが見つかりません"
        super().__init__(message, "INVENTORY_NOT_FOUND", player_id=player_id)


class ItemNotInChestCommandException(ChestCommandException):
    """チェストから取得しようとしたアイテムがチェストに存在しない場合の例外"""

    def __init__(self, spot_id: int, chest_id: int, item_instance_id: int):
        message = f"スポット {spot_id} のチェスト {chest_id} にアイテム {item_instance_id} は存在しません"
        super().__init__(
            message,
            "ITEM_NOT_IN_CHEST",
            spot_id=spot_id,
            chest_id=chest_id,
            item_instance_id=item_instance_id,
        )
