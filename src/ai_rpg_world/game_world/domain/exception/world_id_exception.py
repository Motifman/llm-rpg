from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class BlankWorldIdException(GameWorldDomainException):
    error_code = "GAME_WORLD.BLANK_WORLD_ID"
