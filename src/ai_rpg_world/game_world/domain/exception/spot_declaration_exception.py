from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class InitialPassageStateNotDeclaredException(GameWorldDomainException):
    error_code = "GAME_WORLD.SPOT_DECLARATION.INITIAL_PASSAGE_STATE_NOT_DECLARED"


class NoPassageStatesException(GameWorldDomainException):
    error_code = "GAME_WORLD.SPOT_DECLARATION.NO_PASSAGE_STATES"


class UndeclaredPassageStateException(GameWorldDomainException):
    error_code = "GAME_WORLD.SPOT_DECLARATION.UNDECLARED_PASSAGE_STATE"


class DuplicatePassageStateNameException(GameWorldDomainException):
    error_code = "GAME_WORLD.SPOT_DECLARATION.DUPLICATE_PASSAGE_STATE_NAME"


class PassageEndsAtSameSpotException(GameWorldDomainException):
    error_code = "GAME_WORLD.SPOT_DECLARATION.PASSAGE_ENDS_AT_SAME_SPOT"


class DuplicateReachableObjectException(GameWorldDomainException):
    error_code = "GAME_WORLD.SPOT_DECLARATION.DUPLICATE_REACHABLE_OBJECT"
