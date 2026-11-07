from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class LevelNameBlankException(GameWorldDomainException):
    error_code = "GAME_WORLD.LEVEL_NAME_BLANK"


class NoLevelsDeclaredException(GameWorldDomainException):
    error_code = "GAME_WORLD.NO_LEVELS_DECLARED"


class LevelsNotStartingAtZeroException(GameWorldDomainException):
    error_code = "GAME_WORLD.LEVELS_NOT_STARTING_AT_ZERO"


class LevelsNotAscendingException(GameWorldDomainException):
    error_code = "GAME_WORLD.LEVELS_NOT_ASCENDING"


class LevelNameDuplicatedException(GameWorldDomainException):
    error_code = "GAME_WORLD.LEVEL_NAME_DUPLICATED"


class LevelBeyondLimitException(GameWorldDomainException):
    error_code = "GAME_WORLD.LEVEL_BEYOND_LIMIT"


class RuleLimitBelowOneException(GameWorldDomainException):
    error_code = "GAME_WORLD.RULE_LIMIT_BELOW_ONE"
