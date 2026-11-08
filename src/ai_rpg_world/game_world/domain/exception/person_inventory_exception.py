from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class PackIsEmptyException(GameWorldDomainException):
    error_code = "GAME_WORLD.PACK_IS_EMPTY"


class ItemNotHeldException(GameWorldDomainException):
    error_code = "GAME_WORLD.ITEM_NOT_HELD"


class ItemNotPackedException(GameWorldDomainException):
    error_code = "GAME_WORLD.ITEM_NOT_PACKED"
