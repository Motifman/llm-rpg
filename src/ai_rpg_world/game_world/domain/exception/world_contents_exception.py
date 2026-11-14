from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class AggregateNotInWorldException(GameWorldDomainException):
    error_code = "GAME_WORLD.AGGREGATE_NOT_IN_WORLD"


class WorldAlreadyStartedException(GameWorldDomainException):
    error_code = "GAME_WORLD.WORLD_ALREADY_STARTED"


class AggregateOwnedTwiceException(GameWorldDomainException):
    error_code = "GAME_WORLD.AGGREGATE_OWNED_TWICE"
