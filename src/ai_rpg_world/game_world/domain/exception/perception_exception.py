from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class DeadPersonCannotPerceiveAsLivingException(GameWorldDomainException):
    error_code = "GAME_WORLD.PERCEPTION.DEAD_PERSON_CANNOT_PERCEIVE_AS_LIVING"
