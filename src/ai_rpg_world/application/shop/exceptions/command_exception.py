"""ショップコマンド関連の例外"""
from typing import Optional
from ai_rpg_world.application.shop.exceptions.base_exception import ShopApplicationException


class ShopCommandException(ShopApplicationException):
    """ショップコマンド関連の例外"""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        user_id: Optional[int] = None,
        shop_id: Optional[int] = None,
        listing_id: Optional[int] = None,
        **context,
    ):
        all_context = dict(context)
        if user_id is not None:
            all_context["user_id"] = user_id
        if shop_id is not None:
            all_context["shop_id"] = shop_id
        if listing_id is not None:
            all_context["listing_id"] = listing_id
        super().__init__(message, error_code, **all_context)


class ShopNotFoundForCommandException(ShopCommandException):
    """コマンド実行時にショップが見つからない場合の例外"""

    def __init__(self, shop_id: int, command_name: str):
        message = f"コマンド '{command_name}' の実行時にショップが見つかりません: {shop_id}"
        super().__init__(message, "SHOP_NOT_FOUND_FOR_COMMAND", shop_id=shop_id)


class NotAtShopLocationException(ShopCommandException):
    """購入者がショップのロケーションにいない場合の例外"""

    def __init__(self, buyer_id: int, shop_id: int):
        message = f"プレイヤー {buyer_id} はショップ {shop_id} のロケーションにいません"
        super().__init__(message, "NOT_AT_SHOP_LOCATION", user_id=buyer_id, shop_id=shop_id)


class NotShopOwnerException(ShopCommandException):
    """ショップオーナーでない場合の例外"""

    def __init__(self, player_id: int, shop_id: int, action: str):
        message = f"プレイヤー {player_id} はショップ {shop_id} のオーナーではありません（{action}）"
        super().__init__(message, "NOT_SHOP_OWNER", user_id=player_id, shop_id=shop_id)


class ListingNotFoundForCommandException(ShopCommandException):
    """コマンド実行時にリストが見つからない場合の例外"""

    def __init__(self, shop_id: int, listing_id: int, command_name: str):
        message = f"コマンド '{command_name}' の実行時にリストが見つかりません: shop={shop_id}, listing={listing_id}"
        super().__init__(message, "LISTING_NOT_FOUND_FOR_COMMAND", shop_id=shop_id, listing_id=listing_id)


class InsufficientStockForPurchaseException(ShopCommandException):
    """購入時に在庫が不足している場合の例外"""

    def __init__(self, listing_id: int, requested: int, available: int):
        message = f"在庫不足: リスト {listing_id} の在庫 {available} に対して {requested} 個を要求しました"
        super().__init__(message, "INSUFFICIENT_STOCK_FOR_PURCHASE", listing_id=listing_id)


class CannotPartiallyPurchaseException(ShopCommandException):
    """部分購入が許可されていないアイテム（耐久度あり・非スタック等）の場合の例外"""

    def __init__(self, listing_id: int, reason: str):
        message = f"リスト {listing_id} は部分購入できません: {reason}"
        super().__init__(message, "CANNOT_PARTIALLY_PURCHASE", listing_id=listing_id)


class ShopAlreadyExistsAtLocationException(ShopCommandException):
    """同一ロケーションに既にショップが存在する場合の例外"""

    def __init__(self, spot_id: int, location_area_id: int):
        message = f"ロケーション (spot_id={spot_id}, location_area_id={location_area_id}) には既にショップが存在します"
        super().__init__(message, "SHOP_ALREADY_EXISTS_AT_LOCATION")
