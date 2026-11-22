class PlaySessionDomainException(Exception):
    error_code: str = "PLAY_SESSION.DOMAIN_ERROR"


class CastValidationException(PlaySessionDomainException):
    error_code = "PLAY_SESSION.CAST_VALIDATION"


class PersonNotCastException(PlaySessionDomainException):
    error_code = "PLAY_SESSION.PERSON_NOT_CAST"


class PersonNotBriefedException(PlaySessionDomainException):
    error_code = "PLAY_SESSION.PERSON_NOT_BRIEFED"


class CastNotFoundException(PlaySessionDomainException):
    error_code = "PLAY_SESSION.CAST_NOT_FOUND"


class PersonAlreadyBriefedException(PlaySessionDomainException):
    error_code = "PLAY_SESSION.PERSON_ALREADY_BRIEFED"


class RoundValidationException(PlaySessionDomainException):
    error_code = "PLAY_SESSION.ROUND_VALIDATION"


class RoundAlreadyOpenException(PlaySessionDomainException):
    error_code = "PLAY_SESSION.ROUND_ALREADY_OPEN"


class RoundNotOpenException(PlaySessionDomainException):
    error_code = "PLAY_SESSION.ROUND_NOT_OPEN"


class RoundStillHasTurnsException(PlaySessionDomainException):
    error_code = "PLAY_SESSION.ROUND_STILL_HAS_TURNS"


class TurnNotDueException(PlaySessionDomainException):
    error_code = "PLAY_SESSION.TURN_NOT_DUE"
