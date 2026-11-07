from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class EmptyAppearanceException(GameWorldDomainException):
    error_code = "GAME_WORLD.EMPTY_APPEARANCE"


class EmptyVisibleNameException(GameWorldDomainException):
    error_code = "GAME_WORLD.EMPTY_VISIBLE_NAME"


class MalformedTemplateException(GameWorldDomainException):
    error_code = "GAME_WORLD.MALFORMED_TEMPLATE"


class HolesAndPeopleMismatchException(GameWorldDomainException):
    error_code = "GAME_WORLD.HOLES_AND_PEOPLE_MISMATCH"
