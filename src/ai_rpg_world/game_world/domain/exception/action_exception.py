from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class UndeclaredNounException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.UNDECLARED_NOUN"


class BlankSpeechContentException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.BLANK_SPEECH_CONTENT"


class BlankWaitReasonException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.BLANK_WAIT_REASON"


class NoDeliveriesException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.NO_DELIVERIES"


class StealthNotAllowedException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.STEALTH_NOT_ALLOWED"


class UnseenTargetNotAllowedException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.UNSEEN_TARGET_NOT_ALLOWED"


class ArgumentsDoNotMatchDeclarationException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.ARGUMENTS_DO_NOT_MATCH_DECLARATION"


class BlankRefusalCodeException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.BLANK_REFUSAL_CODE"


class MissingCommonRuleRefusalTextException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.MISSING_COMMON_RULE_REFUSAL_TEXT"


class UnknownPersonInRefusalTextException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.UNKNOWN_PERSON_IN_REFUSAL_TEXT"
