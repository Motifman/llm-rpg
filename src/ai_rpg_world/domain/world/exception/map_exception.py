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
    NotFoundException
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


class MovementCostValidationException(MapDomainException, ValidationException):
    """移動コストバリデーション例外"""
    error_code = "MAP.MOVEMENT_COST_VALIDATION"


class TileNotFoundException(MapDomainException, NotFoundException):
    """タイルが見つからない例外"""
    error_code = "MAP.TILE_NOT_FOUND"


class ObjectNotFoundException(MapDomainException, NotFoundException):
    """オブジェクトが見つからない例外"""
    error_code = "MAP.OBJECT_NOT_FOUND"


class SpotNotFoundException(MapDomainException, NotFoundException):
    """スポットが見つからない例外"""
    error_code = "MAP.SPOT_NOT_FOUND"


class DuplicateObjectException(MapDomainException, BusinessRuleException):
    """同じ場所にオブジェクトが既に存在する例外"""
    error_code = "MAP.DUPLICATE_OBJECT"


class InvalidPlacementException(MapDomainException, BusinessRuleException):
    """不正な場所にオブジェクトを配置しようとした例外"""
    error_code = "MAP.INVALID_PLACEMENT"


class InvalidMovementException(MapDomainException, BusinessRuleException):
    """不正なオブジェクト移動の例外"""
    error_code = "MAP.INVALID_MOVEMENT"


class InvalidConnectionException(MapDomainException, BusinessRuleException):
    """不正な接続の例外"""
    error_code = "MAP.INVALID_CONNECTION"


class DuplicateConnectionException(MapDomainException, BusinessRuleException):
    """重複する接続の例外"""
    error_code = "MAP.DUPLICATE_CONNECTION"


class LockedDoorException(MapDomainException, BusinessRuleException):
    """施錠されたドアを操作しようとした際の例外"""
    error_code = "MAP.LOCKED_DOOR"


class WorldObjectIdValidationException(MapDomainException, ValidationException):
    """ワールドオブジェクトIDバリデーション例外"""
    error_code = "MAP.OBJECT_ID_VALIDATION"


class SpotNameEmptyException(MapDomainException, ValidationException):
    """スポット名が空である例外"""
    error_code = "MAP.SPOT_NAME_EMPTY"
