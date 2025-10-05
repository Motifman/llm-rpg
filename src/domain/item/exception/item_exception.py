"""
Itemドメインの例外定義

DDDの観点では、ドメイン層で汎用的なValueErrorを使用せず、
ドメイン固有の意味を持つカスタム例外を使用すべきです。
これにより、ビジネスルールの明確化、テストの容易性、
適切なエラーハンドリングが可能になります。
"""


class ItemDomainException(Exception):
    """Itemドメインの基底例外"""
    error_code: str = "DOMAIN_ERROR"


class ValidationException(ItemDomainException):
    """バリデーション関連の例外"""
    pass


class NotFoundException(ItemDomainException):
    """存在確認関連の例外"""
    pass


class BusinessRuleException(ItemDomainException):
    """ビジネスルール違反関連の例外"""
    pass


class StateException(ItemDomainException):
    """状態関連の例外"""
    pass


# 具体的な例外クラス（後方互換性のため既存のクラス名を維持）

class ItemNotFoundException(NotFoundException):
    """アイテムが見つからない場合の例外"""
    error_code = "ITEM_NOT_FOUND"

    def __init__(self, item_id: int, message: str = None):
        self.item_id = item_id
        if message is None:
            message = f"アイテムが見つかりません。item_id: {item_id}"
        super().__init__(message)


class ItemNotUsableException(BusinessRuleException):
    """アイテムが使用できない場合の例外"""
    error_code = "ITEM_NOT_USABLE"

    def __init__(self, item_id: int, reason: str = None, message: str = None):
        self.item_id = item_id
        self.reason = reason
        if message is None:
            message = f"アイテムを使用できません。item_id: {item_id}"
            if reason:
                message += f" 理由: {reason}"
        super().__init__(message)


class ItemNotEquippableException(BusinessRuleException):
    """アイテムが装備できない場合の例外"""
    error_code = "ITEM_NOT_EQUIPPABLE"

    def __init__(self, item_id: int, reason: str = None, message: str = None):
        self.item_id = item_id
        self.reason = reason
        if message is None:
            message = f"アイテムを装備できません。item_id: {item_id}"
            if reason:
                message += f" 理由: {reason}"
        super().__init__(message)


class ItemInstanceIdValidationException(ValidationException):
    """ItemInstanceIdのバリデーション例外"""
    error_code = "ITEM_INSTANCE_ID_VALIDATION_ERROR"

    def __init__(self, value, message: str = None):
        self.value = value
        if message is None:
            message = f"ItemInstanceIdは正の数値である必要があります。入力値: {value}"
        super().__init__(message)


class RecipeNotFoundException(NotFoundException):
    """レシピが見つからない場合の例外"""
    error_code = "RECIPE_NOT_FOUND"

    def __init__(self, recipe_id: int, message: str = None):
        self.recipe_id = recipe_id
        if message is None:
            message = f"レシピが見つかりません。recipe_id: {recipe_id}"
        super().__init__(message)


class InsufficientIngredientsException(BusinessRuleException):
    """材料が不足している場合の例外"""
    error_code = "INSUFFICIENT_INGREDIENTS"

    def __init__(self, recipe_id: int, missing_ingredients: dict, message: str = None):
        self.recipe_id = recipe_id
        self.missing_ingredients = missing_ingredients
        if message is None:
            message = f"レシピの材料が不足しています。recipe_id: {recipe_id}, 不足材料: {missing_ingredients}"
        super().__init__(message)


class InvalidRecipeException(ValidationException):
    """無効なレシピの場合の例外"""
    error_code = "INVALID_RECIPE"

    def __init__(self, recipe_id: int, reason: str = None, message: str = None):
        self.recipe_id = recipe_id
        self.reason = reason
        if message is None:
            message = f"無効なレシピです。recipe_id: {recipe_id}"
            if reason:
                message += f" 理由: {reason}"
        super().__init__(message)


# 追加のバリデーション例外クラス

class QuantityValidationException(ValidationException):
    """数量バリデーション例外"""
    error_code = "QUANTITY_VALIDATION_ERROR"

    def __init__(self, quantity: int, reason: str = None, message: str = None):
        self.quantity = quantity
        if message is None:
            message = f"数量が無効です。quantity: {quantity}"
            if reason:
                message += f" 理由: {reason}"
        super().__init__(message)


class DurabilityValidationException(ValidationException):
    """耐久値バリデーション例外"""
    error_code = "DURABILITY_VALIDATION_ERROR"

    def __init__(self, current: int, max_value: int, reason: str = None, message: str = None):
        self.current = current
        self.max_value = max_value
        if message is None:
            message = f"耐久値が無効です。current: {current}, max_value: {max_value}"
            if reason:
                message += f" 理由: {reason}"
        super().__init__(message)


class ItemSpecValidationException(ValidationException):
    """アイテム仕様バリデーション例外"""
    error_code = "ITEM_SPEC_VALIDATION_ERROR"

    def __init__(self, field: str, value, reason: str = None, message: str = None):
        self.field = field
        self.value = value
        if message is None:
            message = f"アイテム仕様のフィールドが無効です。field: {field}, value: {value}"
            if reason:
                message += f" 理由: {reason}"
        super().__init__(message)


class MaxStackSizeValidationException(ValidationException):
    """最大スタックサイズバリデーション例外"""
    error_code = "MAX_STACK_SIZE_VALIDATION_ERROR"

    def __init__(self, value: int, message: str = None):
        self.value = value
        if message is None:
            message = f"最大スタックサイズは正の数値である必要があります。value: {value}"
        super().__init__(message)


class ItemEffectValidationException(ValidationException):
    """アイテム効果バリデーション例外"""
    error_code = "ITEM_EFFECT_VALIDATION_ERROR"

    def __init__(self, effect_type: str, amount: int, reason: str = None, message: str = None):
        self.effect_type = effect_type
        self.amount = amount
        if message is None:
            message = f"アイテム効果が無効です。effect_type: {effect_type}, amount: {amount}"
            if reason:
                message += f" 理由: {reason}"
        super().__init__(message)


class StackSizeExceededException(BusinessRuleException):
    """スタックサイズ超過例外"""
    error_code = "STACK_SIZE_EXCEEDED"

    def __init__(self, current_quantity: int, max_stack_size: int, message: str = None):
        self.current_quantity = current_quantity
        self.max_stack_size = max_stack_size
        if message is None:
            message = f"スタックサイズを超過します。現在の数量: {current_quantity}, 最大スタックサイズ: {max_stack_size}"
        super().__init__(message)


class InsufficientQuantityException(BusinessRuleException):
    """数量不足例外"""
    error_code = "INSUFFICIENT_QUANTITY"

    def __init__(self, requested: int, available: int, message: str = None):
        self.requested = requested
        self.available = available
        if message is None:
            message = f"数量が不足しています。要求数量: {requested}, 利用可能数量: {available}"
        super().__init__(message)