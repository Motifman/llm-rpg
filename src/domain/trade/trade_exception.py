class TradeException(Exception):
    pass


class InvalidTradeStatusException(TradeException):
    pass


class CannotAcceptOwnTradeException(TradeException):
    pass


class CannotAcceptTradeWithOtherPlayerException(TradeException):
    pass


class CannotCancelTradeWithOtherPlayerException(TradeException):
    pass


class InsufficientItemsException(TradeException):
    pass


class InsufficientGoldException(TradeException):
    pass

