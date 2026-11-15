from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class PeopleNotWrittenOnceException(GameWorldDomainException):
    error_code = "GAME_WORLD.SURROUNDINGS_TEXTS.PEOPLE_NOT_WRITTEN_ONCE"


class PersonInSurroundingsNoticeException(GameWorldDomainException):
    error_code = "GAME_WORLD.SURROUNDINGS_TEXTS.PERSON_IN_NOTICE"


class BlankPeopleJoinerException(GameWorldDomainException):
    error_code = "GAME_WORLD.SURROUNDINGS_TEXTS.BLANK_PEOPLE_JOINER"


class NoPeopleToListException(GameWorldDomainException):
    error_code = "GAME_WORLD.SURROUNDINGS_TEXTS.NO_PEOPLE_TO_LIST"
