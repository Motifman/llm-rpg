from __future__ import annotations

from typing import TYPE_CHECKING

from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.action_refusal import ActionRefusal


class UndeclaredNounException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.UNDECLARED_NOUN"


class BlankSpeechContentException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.BLANK_SPEECH_CONTENT"


class BlankWaitReasonException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.BLANK_WAIT_REASON"


class NothingToHandOverException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.NOTHING_TO_HAND_OVER"


class HandOverToSelfException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.HAND_OVER_TO_SELF"


class StealthNotAllowedException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.STEALTH_NOT_ALLOWED"


class UnseenTargetNotAllowedException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.UNSEEN_TARGET_NOT_ALLOWED"


class ArgumentsDoNotMatchDeclarationException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.ARGUMENTS_DO_NOT_MATCH_DECLARATION"


class ArgumentsNotChosenException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.ARGUMENTS_NOT_CHOSEN"


class SeveralItemsNotOfferedException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.SEVERAL_ITEMS_NOT_OFFERED"


class BlankRefusalCodeException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.BLANK_REFUSAL_CODE"


class MissingCommonRuleRefusalTextException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.MISSING_COMMON_RULE_REFUSAL_TEXT"


class UnknownPersonInRefusalTextException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.UNKNOWN_PERSON_IN_REFUSAL_TEXT"


class ActionRefusedException(GameWorldDomainException):
    error_code = "GAME_WORLD.ACTION.ACTION_REFUSED"

    def __init__(self, refusal: ActionRefusal) -> None:
        super().__init__(type(refusal.reason).__name__)
        self.refusal = refusal
