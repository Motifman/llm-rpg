"""ショップアプリケーション層の基底例外"""
from typing import Optional, Any, Dict


class ShopApplicationException(Exception):
    """ショップアプリケーション層の基底例外"""

    def __init__(self, message: str, error_code: Optional[str] = None, **context: Any):
        self.message = message
        self.error_code = error_code or self.__class__.__name__.upper()
        self.context = context
        super().__init__(message)

        self.user_id = context.get("user_id")
        self.shop_id = context.get("shop_id")
        self.listing_id = context.get("listing_id")


class ShopSystemErrorException(ShopApplicationException):
    """ショップシステムエラー例外"""

    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        context: Dict[str, Any] = {}
        if original_exception is not None:
            context["original_exception"] = original_exception
        super().__init__(message, error_code="SHOP_SYSTEM_ERROR", **context)
        self.original_exception = original_exception
