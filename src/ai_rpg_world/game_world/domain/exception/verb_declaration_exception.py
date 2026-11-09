from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


class ShownKeyHoldsNoWrittenTextException(GameWorldDomainException):
    error_code = "GAME_WORLD.VERB_DECLARATION.SHOWN_KEY_HOLDS_NO_WRITTEN_TEXT"


class NoJointActionPartsException(GameWorldDomainException):
    error_code = "GAME_WORLD.VERB_DECLARATION.NO_JOINT_ACTION_PARTS"


class DuplicateJointActionPartException(GameWorldDomainException):
    error_code = "GAME_WORLD.VERB_DECLARATION.DUPLICATE_JOINT_ACTION_PART"


class DuplicateArgumentNameException(GameWorldDomainException):
    error_code = "GAME_WORLD.VERB_DECLARATION.DUPLICATE_ARGUMENT_NAME"


class NotBuiltInActionPerceptionException(GameWorldDomainException):
    error_code = "GAME_WORLD.VERB_DECLARATION.NOT_BUILT_IN_ACTION_PERCEPTION"


class UnfilledNameInBuiltInActionPerceptionException(GameWorldDomainException):
    error_code = "GAME_WORLD.VERB_DECLARATION.UNFILLED_NAME_IN_BUILT_IN_ACTION_PERCEPTION"
