from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class NoDayPhasesDeclaredException(GameWorldDomainException):
    error_code = "GAME_WORLD.NO_DAY_PHASES_DECLARED"


class DayPhasesNotAscendingException(GameWorldDomainException):
    error_code = "GAME_WORLD.DAY_PHASES_NOT_ASCENDING"


class DayPhaseNameDuplicatedException(GameWorldDomainException):
    error_code = "GAME_WORLD.DAY_PHASE_NAME_DUPLICATED"


class TimeOfDayBeyondDayException(GameWorldDomainException):
    error_code = "GAME_WORLD.TIME_OF_DAY_BEYOND_DAY"


class NoNextWeatherDeclaredException(GameWorldDomainException):
    error_code = "GAME_WORLD.NO_NEXT_WEATHER_DECLARED"


class WeatherTransitionDuplicatedException(GameWorldDomainException):
    error_code = "GAME_WORLD.WEATHER_TRANSITION_DUPLICATED"
