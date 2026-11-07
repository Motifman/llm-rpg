from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class PersonStartsFallenException(GameWorldDomainException):
    error_code = "GAME_WORLD.PERSON_STARTS_FALLEN"


class PersonNotAliveException(GameWorldDomainException):
    error_code = "GAME_WORLD.PERSON_NOT_ALIVE"


class PersonNotDownException(GameWorldDomainException):
    error_code = "GAME_WORLD.PERSON_NOT_DOWN"


class BlankStatusEffectTypeException(GameWorldDomainException):
    error_code = "GAME_WORLD.BLANK_STATUS_EFFECT_TYPE"


class PersonNotInWorldException(GameWorldDomainException):
    error_code = "GAME_WORLD.PERSON_NOT_IN_WORLD"


class PersonListedTwiceException(GameWorldDomainException):
    error_code = "GAME_WORLD.PERSON_LISTED_TWICE"


class OutcomeAlreadyDecidedException(GameWorldDomainException):
    error_code = "GAME_WORLD.OUTCOME_ALREADY_DECIDED"


class GroupingDoesNotChangeException(GameWorldDomainException):
    error_code = "GAME_WORLD.GROUPING_DOES_NOT_CHANGE"


class AlreadyInGroupException(GameWorldDomainException):
    error_code = "GAME_WORLD.ALREADY_IN_GROUP"


class AlreadyInAnotherGroupOfGroupingException(GameWorldDomainException):
    error_code = "GAME_WORLD.ALREADY_IN_ANOTHER_GROUP_OF_GROUPING"


class NotInGroupException(GameWorldDomainException):
    error_code = "GAME_WORLD.NOT_IN_GROUP"
