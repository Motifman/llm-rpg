from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class InvalidLightingConditionsException(GameWorldDomainException):
    error_code = "GAME_WORLD.INVALID_LIGHTING_CONDITIONS"
