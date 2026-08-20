"""
Tradeドメインの例外定義

DDDの原則に従い、ドメイン固有の意味を持つカスタム例外を使用します。
全てのTradeドメイン例外はTradeDomainExceptionと適切なカテゴリ例外を多重継承し、
エラーコードは"TRADE.xxx"の形式で統一します。
"""

from ai_rpg_world.domain.common.exception import (
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


class TradeOfferValidationException(TradeDomainException, ValidationException):
    """同席取引の提案が、成立しえない形で作られた (Phase 2)。

    成立しえない提案を store に入れると、失敗が発火の瞬間ではなく承諾の
    瞬間に出て、原因が読めなくなる。作る時点で弾く。
    """
    error_code = "TRADE.OFFER_VALIDATION"


class TradeOfferStateException(TradeDomainException, StateException):
    """既に返事のついた提案へ、もう一度返事をしようとした (Phase 2)。"""
    error_code = "TRADE.OFFER_STATE"


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


class CannotDeclineTradeException(TradeDomainException, BusinessRuleException):
    """取引を断れない例外（直接取引の宛先以外、または出品者本人）"""
    error_code = "TRADE.CANNOT_DECLINE"


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

class MarketOrderValidationException(TradeDomainException, ValidationException):
    """市場の板に出す注文が、成立しえない形で作られた (Phase 3)。

    値の付いていない注文や数量 0 の注文を板に載せると、失敗が「出した瞬間」
    ではなく「誰かが受けた瞬間」に出て、原因が読めなくなる。作る時点で弾く。
    """
    error_code = "TRADE.MARKET_ORDER_VALIDATION"


class MarketOrderStateException(TradeDomainException, StateException):
    """市場の注文に、いまの状態では通らない操作をした (Phase 3)。

    残数を超える約定、引き取り待ちの注文への約定など。黙って切り詰めると
    「3 つ買えたつもりで 2 つしか届かない」形の食い違いが残る。
    """
    error_code = "TRADE.MARKET_ORDER_STATE"


class MarketBoardStateException(TradeDomainException, StateException):
    """市場の板に、いまの状態では通らない操作をした (Phase 3)。

    存在しない注文の取り下げ、他人の注文の取り下げ、自分の注文の自己約定など。
    """
    error_code = "TRADE.MARKET_BOARD_STATE"
