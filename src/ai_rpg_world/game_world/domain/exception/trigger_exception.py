from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class SubjectNotInTriggerException(GameWorldDomainException):
    error_code = "GAME_WORLD.SUBJECT_NOT_IN_TRIGGER"


class ItemNotInTriggerException(GameWorldDomainException):
    error_code = "GAME_WORLD.ITEM_NOT_IN_TRIGGER"


class ArgumentNotInTriggerException(GameWorldDomainException):
    error_code = "GAME_WORLD.ARGUMENT_NOT_IN_TRIGGER"
