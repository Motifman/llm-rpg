class GameWorldDomainException(Exception):
    error_code: str = "GAME_WORLD.DOMAIN_ERROR"


class ValueOutOfRangeException(GameWorldDomainException):
    error_code = "GAME_WORLD.VALUE_OUT_OF_RANGE"


class TickOrderException(GameWorldDomainException):
    error_code = "GAME_WORLD.TICK_ORDER"


class CountBelowZeroException(GameWorldDomainException):
    error_code = "GAME_WORLD.COUNT_BELOW_ZERO"


class InsufficientGoldException(GameWorldDomainException):
    error_code = "GAME_WORLD.INSUFFICIENT_GOLD"


class InvalidSpotIdException(GameWorldDomainException):
    error_code = "GAME_WORLD.INVALID_SPOT_ID"


class RepeatedMementoKeyException(GameWorldDomainException):
    error_code = "GAME_WORLD.REPEATED_MEMENTO_KEY"
