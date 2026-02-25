"""
ショップドメインの例外定義

DDDの原則に従い、ドメイン固有の意味を持つカスタム例外を使用します。
全てのShopドメイン例外はShopDomainExceptionと適切なカテゴリ例外を多重継承し、
エラーコードは"SHOP.xxx"の形式で統一します。
"""

from ai_rpg_world.domain.common.exception import (
    BusinessRuleException,
    DomainException,
    ValidationException,
    NotFoundException,
)


class ShopDomainException(DomainException):
    """ショップドメインの基底例外

    全てのショップドメイン例外はこのクラスを継承します。
    """
    domain = "shop"


# ===== バリデーション例外 =====

class ShopIdValidationException(ShopDomainException, ValidationException):
    """ショップIDバリデーション例外"""
    error_code = "SHOP.ID_VALIDATION"


class ShopListingIdValidationException(ShopDomainException, ValidationException):
    """ショップリストIDバリデーション例外"""
    error_code = "SHOP.LISTING_ID_VALIDATION"


class ShopListingPriceValidationException(ShopDomainException, ValidationException):
    """ショップ販売価格バリデーション例外"""
    error_code = "SHOP.LISTING_PRICE_VALIDATION"


# ===== ビジネスルール例外 =====

class NotShopOwnerException(ShopDomainException, BusinessRuleException):
    """ショップオーナーでない場合の例外"""
    error_code = "SHOP.NOT_OWNER"


class DuplicateShopAtLocationException(ShopDomainException, BusinessRuleException):
    """同一ロケーションに既にショップが存在する場合の例外"""
    error_code = "SHOP.DUPLICATE_AT_LOCATION"


# ===== 存在確認例外 =====

class ShopNotFoundException(ShopDomainException, NotFoundException):
    """ショップが見つからない例外"""
    error_code = "SHOP.NOT_FOUND"


class ListingNotFoundException(ShopDomainException, NotFoundException):
    """リストが見つからない例外"""
    error_code = "SHOP.LISTING_NOT_FOUND"


class InsufficientStockException(ShopDomainException, BusinessRuleException):
    """在庫不足例外"""
    error_code = "SHOP.INSUFFICIENT_STOCK"
