from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class UnknownPersonPlaceholderException(GameWorldDomainException):
    error_code = "GAME_WORLD.UNKNOWN_PERSON_PLACEHOLDER"


class NotDeclaredInThisWorldException(GameWorldDomainException):
    error_code = "GAME_WORLD.NOT_DECLARED_IN_THIS_WORLD"


class TickModuloOutOfRangeException(GameWorldDomainException):
    error_code = "GAME_WORLD.TICK_MODULO_OUT_OF_RANGE"
