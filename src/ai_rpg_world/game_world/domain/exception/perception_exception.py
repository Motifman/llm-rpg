from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class DeadPersonCannotPerceiveAsLivingException(GameWorldDomainException):
    error_code = "GAME_WORLD.PERCEPTION.DEAD_PERSON_CANNOT_PERCEIVE_AS_LIVING"


class TargetNotInvolvedException(GameWorldDomainException):
    error_code = "GAME_WORLD.PERCEPTION.TARGET_NOT_INVOLVED"


class PerceptionTargetNotGivenException(GameWorldDomainException):
    error_code = "GAME_WORLD.PERCEPTION.TARGET_NOT_GIVEN"


class PerceivedItemSpecNotGivenException(GameWorldDomainException):
    error_code = "GAME_WORLD.PERCEPTION.ITEM_SPEC_NOT_GIVEN"
