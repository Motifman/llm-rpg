"""
Worldドメインの例外定義

全てのWorldドメイン例外はMapDomainExceptionと適切なカテゴリ例外を多重継承し、
エラーコードは"MAP.xxx"の形式で統一します。
"""

from ai_rpg_world.domain.common.exception import (
    BusinessRuleException,
    DomainException,
    StateException,
    ValidationException,
)


class MapDomainException(DomainException):
    """Worldドメインの基底例外"""

    domain = "world"


class SpotIdValidationException(MapDomainException, ValidationException):
    """スポットIDバリデーション例外"""

    error_code = "MAP.SPOT_ID_VALIDATION"


class WorldIdValidationException(MapDomainException, ValidationException):
    """世界IDバリデーション例外"""

    error_code = "MAP.WORLD_ID_VALIDATION"


class CoordinateValidationException(MapDomainException, ValidationException):
    """座標バリデーション例外"""

    error_code = "MAP.COORDINATE_VALIDATION"


class WorldObjectIdValidationException(MapDomainException, ValidationException):
    """ワールドオブジェクトIDバリデーション例外"""

    error_code = "MAP.OBJECT_ID_VALIDATION"


class SpotNameEmptyException(MapDomainException, ValidationException):
    """スポット名が空である例外"""

    error_code = "MAP.SPOT_NAME_EMPTY"


class SameCoordinateDirectionException(MapDomainException, BusinessRuleException):
    """同じ座標間の方向を計算しようとした際の例外"""

    error_code = "MAP.SAME_COORDINATE_DIRECTION"


class DirectionDeltaUndefinedException(MapDomainException, BusinessRuleException):
    """移動量が定義されていない向きを使おうとした際の例外"""

    error_code = "MAP.DIRECTION_DELTA_UNDEFINED"


class LocationAreaIdValidationException(MapDomainException, ValidationException):
    """ロケーションエリアIDバリデーション例外"""

    error_code = "MAP.LOCATION_AREA_ID_VALIDATION"


class PackIdValidationException(MapDomainException, ValidationException):
    """PackIdバリデーション例外"""

    error_code = "MAP.PACK_ID_VALIDATION"


class LocationAlreadyOccupiedException(MapDomainException, StateException):
    """ロケーションが既に別の施設に占有されている例外"""

    error_code = "MAP.LOCATION_ALREADY_OCCUPIED"


class LocationNotOccupiedException(MapDomainException, StateException):
    """未割当のロケーションに対して release を呼んだ場合の例外"""

    error_code = "MAP.LOCATION_NOT_OCCUPIED"
