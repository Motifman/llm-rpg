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
