from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class NoChoicesDeclaredException(GameWorldDomainException):
    error_code = "GAME_WORLD.NO_CHOICES_DECLARED"


class ChoiceDuplicatedException(GameWorldDomainException):
    error_code = "GAME_WORLD.CHOICE_DUPLICATED"


class StockCapacityBelowOneException(GameWorldDomainException):
    error_code = "GAME_WORLD.STOCK_CAPACITY_BELOW_ONE"


class StockRefillIntervalBelowOneException(GameWorldDomainException):
    error_code = "GAME_WORLD.STOCK_REFILL_INTERVAL_BELOW_ONE"


class TextBodyBlankException(GameWorldDomainException):
    error_code = "GAME_WORLD.TEXT_BODY_BLANK"


class StateValueMismatchesKindException(GameWorldDomainException):
    error_code = "GAME_WORLD.STATE_VALUE_MISMATCHES_KIND"


class StateKeyDuplicatedException(GameWorldDomainException):
    error_code = "GAME_WORLD.STATE_KEY_DUPLICATED"


class StateKeyOwnerMismatchException(GameWorldDomainException):
    error_code = "GAME_WORLD.STATE_KEY_OWNER_MISMATCH"


class ItemStateKindNotAllowedException(GameWorldDomainException):
    error_code = "GAME_WORLD.ITEM_STATE_KIND_NOT_ALLOWED"


class LightKeyNotDeclaredException(GameWorldDomainException):
    error_code = "GAME_WORLD.LIGHT_KEY_NOT_DECLARED"
