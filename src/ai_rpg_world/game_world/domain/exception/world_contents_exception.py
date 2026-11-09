from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class AggregateNotInWorldException(GameWorldDomainException):
    error_code = "GAME_WORLD.AGGREGATE_NOT_IN_WORLD"
