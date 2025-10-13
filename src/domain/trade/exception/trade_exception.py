"""
Tradeドメインの例外定義

DDDの原則に従い、ドメイン固有の意味を持つカスタム例外を使用します。
全てのTradeドメイン例外はTradeDomainExceptionと適切なカテゴリ例外を多重継承し、
エラーコードは"TRADE.xxx"の形式で統一します。
"""

from src.domain.common.exception import (
    BusinessRuleException,
    DomainException,
    StateException,
    ValidationException
)


class TradeDomainException(DomainException):
    """Tradeドメインの基底例外

    全てのTradeドメイン例外はこのクラスを継承します。
    """
    domain = "trade"


# ===== 具体的な例外クラス =====

class TradeIdValidationException(TradeDomainException, ValidationException):
    """取引IDバリデーション例外"""
    error_code = "TRADE.ID_VALIDATION"


class TradeRequestedGoldValidationException(TradeDomainException, ValidationException):
    """取引要求金額バリデーション例外"""
    error_code = "TRADE.REQUESTED_GOLD_VALIDATION"


class TradeScopeValidationException(TradeDomainException, ValidationException):
    """取引範囲バリデーション例外"""
    error_code = "TRADE.SCOPE_VALIDATION"


class TradeSearchFilterValidationException(TradeDomainException, ValidationException):
    """取引検索フィルタバリデーション例外"""
    error_code = "TRADE.SEARCH_FILTER_VALIDATION"


class InvalidTradeStatusException(TradeDomainException, StateException):
    """無効な取引状態例外"""
    error_code = "TRADE.INVALID_STATUS"


class CannotAcceptOwnTradeException(TradeDomainException, BusinessRuleException):
    """自身の取引を受け入れられない例外"""
    error_code = "TRADE.CANNOT_ACCEPT_OWN"


class CannotAcceptTradeWithOtherPlayerException(TradeDomainException, BusinessRuleException):
    """他のプレイヤーの取引を受け入れられない例外"""
    error_code = "TRADE.CANNOT_ACCEPT_OTHER"


class CannotCancelTradeWithOtherPlayerException(TradeDomainException, BusinessRuleException):
    """他のプレイヤーの取引をキャンセルできない例外"""
    error_code = "TRADE.CANNOT_CANCEL_OTHER"


class InsufficientItemsException(TradeDomainException, BusinessRuleException):
    """アイテム不足例外"""
    error_code = "TRADE.INSUFFICIENT_ITEMS"


class InsufficientGoldException(TradeDomainException, BusinessRuleException):
    """ゴールド不足例外"""
    error_code = "TRADE.INSUFFICIENT_GOLD"


class ItemNotTradeableException(TradeDomainException, BusinessRuleException):
    """取引不可能なアイテム例外"""
    error_code = "TRADE.ITEM_NOT_TRADEABLE"


class InsufficientInventorySpaceException(TradeDomainException, BusinessRuleException):
    """インベントリスペース不足例外"""
    error_code = "TRADE.INSUFFICIENT_INVENTORY_SPACE"