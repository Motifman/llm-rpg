from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class DiscoverableElsewhereException(GameWorldDomainException):
    error_code = "GAME_WORLD.DISCOVERABLE_ELSEWHERE"


class SearchCountIsZeroException(GameWorldDomainException):
    error_code = "GAME_WORLD.SEARCH_COUNT_IS_ZERO"


class OnceInWorldFoundByManyException(GameWorldDomainException):
    error_code = "GAME_WORLD.ONCE_IN_WORLD_FOUND_BY_MANY"


class LatestActionsDisagreeWithAnyoneException(GameWorldDomainException):
    error_code = "GAME_WORLD.LATEST_ACTIONS_DISAGREE_WITH_ANYONE"
