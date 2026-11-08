from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class MalformedTemplateException(GameWorldDomainException):
    error_code = "GAME_WORLD.MALFORMED_TEMPLATE"


class PlaceholdersAndPeopleMismatchException(GameWorldDomainException):
    error_code = "GAME_WORLD.PLACEHOLDERS_AND_PEOPLE_MISMATCH"
