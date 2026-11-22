from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class MalformedBriefingHeadingException(GameWorldDomainException):
    error_code = "GAME_WORLD.BRIEFING_HEADINGS.MALFORMED_HEADING"


class RepeatedBriefingHeadingException(GameWorldDomainException):
    error_code = "GAME_WORLD.BRIEFING_HEADINGS.REPEATED_HEADING"
