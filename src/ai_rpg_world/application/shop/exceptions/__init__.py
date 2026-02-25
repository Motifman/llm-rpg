"""ショップアプリケーション例外"""
from ai_rpg_world.application.shop.exceptions.base_exception import (
    ShopApplicationException,
    ShopSystemErrorException,
)
from ai_rpg_world.application.shop.exceptions.command_exception import (
    ShopCommandException,
    ShopNotFoundForCommandException,
    NotAtShopLocationException,
    NotShopOwnerException,
    ListingNotFoundForCommandException,
    InsufficientStockForPurchaseException,
    CannotPartiallyPurchaseException,
    ShopAlreadyExistsAtLocationException,
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
