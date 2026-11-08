from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class CharacterListedTwiceException(GameWorldDomainException):
    error_code = "GAME_WORLD.CHARACTER_LISTED_TWICE"


class PersonNotInRegisterException(GameWorldDomainException):
    error_code = "GAME_WORLD.PERSON_NOT_IN_REGISTER"


class PersonNotNamedException(GameWorldDomainException):
    error_code = "GAME_WORLD.PERSON_NOT_NAMED"


class PersonAlreadyNamedException(GameWorldDomainException):
    error_code = "GAME_WORLD.PERSON_ALREADY_NAMED"
