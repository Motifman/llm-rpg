from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class HeldItemNotCarriedException(GameWorldDomainException):
    error_code = "GAME_WORLD.HELD_ITEM_NOT_CARRIED"


class ThingFromAnotherSpotException(GameWorldDomainException):
    error_code = "GAME_WORLD.THING_FROM_ANOTHER_SPOT"
