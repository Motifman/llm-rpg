from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class BlankDisplayNameException(GameWorldDomainException):
    error_code = "GAME_WORLD.BLANK_DISPLAY_NAME"


class MultilineDisplayNameException(GameWorldDomainException):
    error_code = "GAME_WORLD.MULTILINE_DISPLAY_NAME"


class BlankDescriptionTextException(GameWorldDomainException):
    error_code = "GAME_WORLD.BLANK_DESCRIPTION_TEXT"
