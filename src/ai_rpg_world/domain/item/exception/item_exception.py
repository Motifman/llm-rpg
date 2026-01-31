"""
Itemドメインの例外定義

DDDの原則に従い、ドメイン固有の意味を持つカスタム例外を使用します。
全てのItemドメイン例外はItemDomainExceptionと適切なカテゴリ例外を多重継承し、
エラーコードは"ITEM.xxx"の形式で統一します。
"""

from ai_rpg_world.domain.common.exception import (
    DomainException,
    ValidationException,
    NotFoundException,
    BusinessRuleException,
    StateException
)


class ItemDomainException(DomainException):
    """Itemドメインの基底例外

    全てのItemドメイン例外はこのクラスを継承します。
    """
    domain = "item"


# ===== 具体的な例外クラス =====

class ItemNotFoundException(ItemDomainException, NotFoundException):
    """アイテムが見つからない場合の例外"""
    error_code = "ITEM.NOT_FOUND"


class ItemNotUsableException(ItemDomainException, BusinessRuleException):
    """アイテムが使用できない場合の例外"""
    error_code = "ITEM.NOT_USABLE"


class ItemNotEquippableException(ItemDomainException, BusinessRuleException):
    """アイテムが装備できない場合の例外"""
    error_code = "ITEM.NOT_EQUIPPABLE"


class ItemInstanceIdValidationException(ItemDomainException, ValidationException):
    """ItemInstanceIdのバリデーション例外"""
    error_code = "ITEM.INSTANCE_ID_VALIDATION"


class RecipeNotFoundException(ItemDomainException, NotFoundException):
    """レシピが見つからない場合の例外"""
    error_code = "ITEM.RECIPE_NOT_FOUND"


class InsufficientIngredientsException(ItemDomainException, BusinessRuleException):
    """材料が不足している場合の例外"""
    error_code = "ITEM.INSUFFICIENT_INGREDIENTS"


class InvalidRecipeException(ItemDomainException, ValidationException):
    """無効なレシピの場合の例外"""
    error_code = "ITEM.INVALID_RECIPE"


class QuantityValidationException(ItemDomainException, ValidationException):
    """数量バリデーション例外"""
    error_code = "ITEM.QUANTITY_VALIDATION"


class DurabilityValidationException(ItemDomainException, ValidationException):
    """耐久値バリデーション例外"""
    error_code = "ITEM.DURABILITY_VALIDATION"


class ItemSpecValidationException(ItemDomainException, ValidationException):
    """アイテム仕様バリデーション例外"""
    error_code = "ITEM.SPEC_VALIDATION"


class MaxStackSizeValidationException(ItemDomainException, ValidationException):
    """最大スタックサイズバリデーション例外"""
    error_code = "ITEM.MAX_STACK_SIZE_VALIDATION"


class ItemEffectValidationException(ItemDomainException, ValidationException):
    """アイテム効果バリデーション例外"""
    error_code = "ITEM.EFFECT_VALIDATION"


class StackSizeExceededException(ItemDomainException, BusinessRuleException):
    """スタックサイズ超過例外"""
    error_code = "ITEM.STACK_SIZE_EXCEEDED"


class InsufficientQuantityException(ItemDomainException, BusinessRuleException):
    """数量不足例外"""
    error_code = "ITEM.INSUFFICIENT_QUANTITY"