from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class GroundItemAlreadyPlacedException(GameWorldDomainException):
    error_code = "GAME_WORLD.GROUND_ITEM_ALREADY_PLACED"


class GroundItemNotFoundException(GameWorldDomainException):
    error_code = "GAME_WORLD.GROUND_ITEM_NOT_FOUND"


class StateKeyNotOwnedException(GameWorldDomainException):
    error_code = "GAME_WORLD.STATE_KEY_NOT_OWNED"


class ItemAlreadyLeftWorldException(GameWorldDomainException):
    error_code = "GAME_WORLD.ITEM_ALREADY_LEFT_WORLD"


class ItemDoesNotRunOutException(GameWorldDomainException):
    error_code = "GAME_WORLD.ITEM_DOES_NOT_RUN_OUT"


class ItemHasNotRunOutException(GameWorldDomainException):
    error_code = "GAME_WORLD.ITEM_HAS_NOT_RUN_OUT"


class ItemAlreadyCarriedException(GameWorldDomainException):
    error_code = "GAME_WORLD.ITEM_ALREADY_CARRIED"


class ItemNotCarriedException(GameWorldDomainException):
    error_code = "GAME_WORLD.ITEM_NOT_CARRIED"


class InventoryFullException(GameWorldDomainException):
    error_code = "GAME_WORLD.INVENTORY_FULL"


class OperationNotForStateKindException(GameWorldDomainException):
    error_code = "GAME_WORLD.OPERATION_NOT_FOR_STATE_KIND"


class StateValueOfAnotherKindException(GameWorldDomainException):
    error_code = "GAME_WORLD.STATE_VALUE_OF_ANOTHER_KIND"


class NotEnoughStockException(GameWorldDomainException):
    error_code = "GAME_WORLD.NOT_ENOUGH_STOCK"


class NotEnoughItemsOfSpecException(GameWorldDomainException):
    error_code = "GAME_WORLD.NOT_ENOUGH_ITEMS_OF_SPEC"


class NeverHiddenObjectUnrevealedException(GameWorldDomainException):
    error_code = "GAME_WORLD.NEVER_HIDDEN_OBJECT_UNREVEALED"
