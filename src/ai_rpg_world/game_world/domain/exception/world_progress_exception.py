from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class WorldAlreadyEndedException(GameWorldDomainException):
    error_code = "GAME_WORLD.WORLD_ALREADY_ENDED"


class GroupDecisionAlreadyOpenException(GameWorldDomainException):
    error_code = "GAME_WORLD.GROUP_DECISION_ALREADY_OPEN"


class GroupDecisionNotOpenException(GameWorldDomainException):
    error_code = "GAME_WORLD.GROUP_DECISION_NOT_OPEN"


class NoVotersGivenException(GameWorldDomainException):
    error_code = "GAME_WORLD.NO_VOTERS_GIVEN"


class NoChoicesGivenException(GameWorldDomainException):
    error_code = "GAME_WORLD.NO_CHOICES_GIVEN"


class VoterNotInDecisionException(GameWorldDomainException):
    error_code = "GAME_WORLD.VOTER_NOT_IN_DECISION"


class ChoiceNotInDecisionException(GameWorldDomainException):
    error_code = "GAME_WORLD.CHOICE_NOT_IN_DECISION"


class BallotAlreadyCastException(GameWorldDomainException):
    error_code = "GAME_WORLD.BALLOT_ALREADY_CAST"


class AbstainNotAllowedException(GameWorldDomainException):
    error_code = "GAME_WORLD.ABSTAIN_NOT_ALLOWED"
