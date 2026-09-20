"""ショップアプリケーション例外"""
from ai_rpg_world.application.shop.exceptions.base_exception import (
    ShopApplicationException,
    ShopSystemErrorException,
)
from ai_rpg_world.application.shop.exceptions.command_exception import (
    CannotPartiallyPurchaseException,
    InsufficientStockForPurchaseException,
    ListingNotFoundForCommandException,
    NotAtShopLocationException,
    NotShopOwnerException,
    ShopAlreadyExistsAtLocationException,
    ShopCommandException,
    ShopNotFoundForCommandException,
)
from ai_rpg_world.application.shop.exceptions.query_exception import (
    ShopQueryApplicationException,
)

__all__ = [
    "ShopApplicationException",
    "ShopSystemErrorException",
    "ShopCommandException",
    "ShopNotFoundForCommandException",
    "NotAtShopLocationException",
    "NotShopOwnerException",
    "ListingNotFoundForCommandException",
    "InsufficientStockForPurchaseException",
    "CannotPartiallyPurchaseException",
    "ShopAlreadyExistsAtLocationException",
    "ShopQueryApplicationException",
]
