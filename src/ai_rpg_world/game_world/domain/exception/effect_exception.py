from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class ArgumentIsNotAnItemException(GameWorldDomainException):
    error_code = "GAME_WORLD.ARGUMENT_IS_NOT_AN_ITEM"


class ArgumentIsNotTextException(GameWorldDomainException):
    error_code = "GAME_WORLD.ARGUMENT_IS_NOT_TEXT"


class TextHasNoAuthorException(GameWorldDomainException):
    error_code = "GAME_WORLD.TEXT_HAS_NO_AUTHOR"


class NoBranchesException(GameWorldDomainException):
    error_code = "GAME_WORLD.NO_BRANCHES"
