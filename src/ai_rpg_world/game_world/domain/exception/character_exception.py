from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class HeldItemNotAmongInitialItemsException(GameWorldDomainException):
    error_code = "GAME_WORLD.HELD_ITEM_NOT_AMONG_INITIAL_ITEMS"


class DuplicatedInitialGroupException(GameWorldDomainException):
    error_code = "GAME_WORLD.DUPLICATED_INITIAL_GROUP"


class DuplicatedKnownPersonException(GameWorldDomainException):
    error_code = "GAME_WORLD.DUPLICATED_KNOWN_PERSON"
