"""SNS の公開参照用識別子に関する例外。"""

from ai_rpg_world.domain.common.exception import ValidationException
from ai_rpg_world.domain.sns.exception.base_exceptions import SnsDomainException


class SnsIdentityValidationException(SnsDomainException, ValidationException):
    """識別子が正規形の UUID4 でないときに復元を拒否する。"""

    error_code = "SNS_IDENTITY_VALIDATION_ERROR"
