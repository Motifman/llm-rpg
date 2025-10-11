"""
Playerドメインの例外定義

DDDの原則に従い、ドメイン固有の意味を持つカスタム例外を使用します。
全てのPlayerドメイン例外はPlayerDomainExceptionと適切なカテゴリ例外を多重継承し、
エラーコードは"PLAYER.xxx"の形式で統一します。
"""

from src.domain.common.exception import (
    BusinessRuleException,
    DomainException,
    StateException,
    ValidationException
)


class PlayerDomainException(DomainException):
    """Playerドメインの基底例外

    全てのPlayerドメイン例外はこのクラスを継承します。
    """
    domain = "player"


# ===== 具体的な例外クラス =====

class PlayerIdValidationException(PlayerDomainException, ValidationException):
    """プレイヤーIDバリデーション例外"""
    error_code = "PLAYER.ID_VALIDATION"


class HpValidationException(PlayerDomainException, ValidationException):
    """HPバリデーション例外"""
    error_code = "PLAYER.HP_VALIDATION"


class MpValidationException(PlayerDomainException, ValidationException):
    """MPバリデーション例外"""
    error_code = "PLAYER.MP_VALIDATION"


class BaseStatusValidationException(PlayerDomainException, ValidationException):
    """基礎ステータスバリデーション例外(deprecated)"""
    error_code = "PLAYER.BASE_STATUS_VALIDATION"


class BaseStatsValidationException(PlayerDomainException, ValidationException):
    """基礎ステータスバリデーション例外"""
    error_code = "PLAYER.BASE_STATS_VALIDATION"


class MessageValidationException(PlayerDomainException, ValidationException):
    """メッセージバリデーション例外"""
    error_code = "PLAYER.MESSAGE_VALIDATION"


class PlayerInventorySlotIdValidationException(PlayerDomainException, ValidationException):
    """プレイヤーインベントリスロットIDバリデーション例外"""
    error_code = "PLAYER.INVENTORY_SLOT_ID_VALIDATION"


class PlayerNameValidationException(PlayerDomainException, ValidationException):
    """プレイヤー名バリデーション例外"""
    error_code = "PLAYER.NAME_VALIDATION"


class ExpTableValidationException(PlayerDomainException, ValidationException):
    """経験値テーブルバリデーション例外"""
    error_code = "PLAYER.EXP_TABLE_VALIDATION"


class StatGrowthFactorValidationException(PlayerDomainException, ValidationException):
    """ステータス成長率バリデーション例外"""
    error_code = "PLAYER.STAT_GROWTH_FACTOR_VALIDATION"


class GrowthValidationException(PlayerDomainException, ValidationException):
    """レベル/経験値管理バリデーション例外"""
    error_code = "PLAYER.GROWTH_VALIDATION"


class StaminaValidationException(PlayerDomainException, ValidationException):
    """スタミナバリデーション例外"""
    error_code = "PLAYER.STAMINA_VALIDATION"


class GoldValidationException(PlayerDomainException, ValidationException):
    """ゴールドバリデーション例外"""
    error_code = "PLAYER.GOLD_VALIDATION"


class InsufficientMpException(PlayerDomainException, BusinessRuleException):
    """MP不足例外"""
    error_code = "PLAYER.INSUFFICIENT_MP"


class InsufficientGoldException(PlayerDomainException, BusinessRuleException):
    """ゴールド不足例外"""
    error_code = "PLAYER.INSUFFICIENT_GOLD"


class PlayerDownedException(PlayerDomainException, StateException):
    """プレイヤー戦闘不能状態例外"""
    error_code = "PLAYER.DOWNED"


# ===== インベントリ関連例外 =====

class InventoryFullException(PlayerDomainException, BusinessRuleException):
    """インベントリ満杯例外"""
    error_code = "PLAYER.INVENTORY_FULL"


class InvalidSlotException(PlayerDomainException, BusinessRuleException):
    """無効なスロット例外"""
    error_code = "PLAYER.INVALID_SLOT"


class ItemNotInSlotException(PlayerDomainException, BusinessRuleException):
    """スロットにアイテムがない例外"""
    error_code = "PLAYER.ITEM_NOT_IN_SLOT"


class EquipmentSlotOccupiedException(PlayerDomainException, BusinessRuleException):
    """装備スロットが占有されている例外"""
    error_code = "PLAYER.EQUIPMENT_SLOT_OCCUPIED"


# ===== 装備関連例外 =====

class InvalidEquipmentItemException(PlayerDomainException, BusinessRuleException):
    """無効な装備アイテム例外"""
    error_code = "PLAYER.INVALID_EQUIPMENT_ITEM"


class EquipmentSlotMismatchException(PlayerDomainException, BusinessRuleException):
    """装備スロット不一致例外"""
    error_code = "PLAYER.EQUIPMENT_SLOT_MISMATCH"


class EquipmentSlotValidationException(PlayerDomainException, ValidationException):
    """装備スロットバリデーション例外"""
    error_code = "PLAYER.EQUIPMENT_SLOT_VALIDATION"
