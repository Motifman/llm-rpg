"""game_world のドメイン例外。

game_world は古い ``ai_rpg_world.domain`` を import しないので、``domain.common.exception`` の
基底は使わず、ここに基底を持つ。``error_code`` は断った理由の印 (``RefusalCode``) になる。
"""


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
