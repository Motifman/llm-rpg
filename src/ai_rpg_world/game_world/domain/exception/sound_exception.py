from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class MissingLoudnessLevelException(GameWorldDomainException):
    error_code = "GAME_WORLD.SOUND.MISSING_LOUDNESS_LEVEL"


class HearingBoundariesOutOfOrderException(GameWorldDomainException):
    error_code = "GAME_WORLD.SOUND.HEARING_BOUNDARIES_OUT_OF_ORDER"
