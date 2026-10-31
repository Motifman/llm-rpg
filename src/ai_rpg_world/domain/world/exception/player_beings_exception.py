"""「プレイヤー → Being」の対応表 (``PlayerBeings``) の例外。"""

from ai_rpg_world.domain.common.exception import BusinessRuleException, ValidationException
from ai_rpg_world.domain.world.exception.map_exception import MapDomainException


class PlayerBeingsDomainException(MapDomainException):
    """対応表の例外の基底。"""


class PlayerAlreadyDrivenException(PlayerBeingsDomainException, BusinessRuleException):
    """別の Being がもう動かしているプレイヤーを、ほかの Being に動かさせようとした。"""

    error_code = "PLAYER_BEINGS.PLAYER_ALREADY_DRIVEN"


class PlayerBeingsValidationException(PlayerBeingsDomainException, ValidationException):
    """対応表に、同じプレイヤーか同じ Being が 2 回出てくる。"""

    error_code = "PLAYER_BEINGS.VALIDATION"


__all__ = [
    "PlayerAlreadyDrivenException",
    "PlayerBeingsDomainException",
    "PlayerBeingsValidationException",
]
