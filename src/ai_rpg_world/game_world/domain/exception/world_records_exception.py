from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class DiscoverableElsewhereException(GameWorldDomainException):
    error_code = "GAME_WORLD.DISCOVERABLE_ELSEWHERE"
