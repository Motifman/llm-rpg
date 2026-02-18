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


class AreaTriggerIdValidationException(MapDomainException, ValidationException):
    """エリアトリガーIDバリデーション例外"""
    error_code = "MAP.AREA_TRIGGER_ID_VALIDATION"


class AreaTriggerNotFoundException(MapDomainException, NotFoundException):
    """エリアトリガーが見つからない例外"""
    error_code = "MAP.AREA_TRIGGER_NOT_FOUND"


class DuplicateAreaTriggerException(MapDomainException, BusinessRuleException):
    """エリアトリガーが既に存在する例外"""
    error_code = "MAP.DUPLICATE_AREA_TRIGGER"


class NotAnActorException(MapDomainException, BusinessRuleException):
    """オブジェクトがアクターではない場合の例外"""
    error_code = "MAP.NOT_AN_ACTOR"


class InteractionOutOfRangeException(MapDomainException, BusinessRuleException):
    """インタラクションの範囲外である例外"""
    error_code = "MAP.INTERACTION_OUT_OF_RANGE"


class NotFacingTargetException(MapDomainException, BusinessRuleException):
    """ターゲットの方を向いていない例外"""
    error_code = "MAP.NOT_FACING_TARGET"


class NotInteractableException(MapDomainException, BusinessRuleException):
    """インタラクション不可能なオブジェクトである例外"""
    error_code = "MAP.NOT_INTERACTABLE"


class SameCoordinateDirectionException(MapDomainException, BusinessRuleException):
    """同じ座標間の方向を計算しようとした際の例外"""
    error_code = "MAP.SAME_COORDINATE_DIRECTION"


class LocationAreaIdValidationException(MapDomainException, ValidationException):
    """ロケーションエリアIDバリデーション例外"""
    error_code = "MAP.LOCATION_AREA_ID_VALIDATION"


class LocationAreaNotFoundException(MapDomainException, NotFoundException):
    """ロケーションエリアが見つからない例外"""
    error_code = "MAP.LOCATION_AREA_NOT_FOUND"


class DuplicateLocationAreaException(MapDomainException, BusinessRuleException):
    """ロケーションエリアが既に存在する例外"""
    error_code = "MAP.DUPLICATE_LOCATION_AREA"


class GatewayIdValidationException(MapDomainException, ValidationException):
    """ゲートウェイIDバリデーション例外"""
    error_code = "MAP.GATEWAY_ID_VALIDATION"


class GatewayNotFoundException(MapDomainException, NotFoundException):
    """ゲートウェイが見つからない例外"""
    error_code = "MAP.GATEWAY_NOT_FOUND"


class DuplicateGatewayException(MapDomainException, BusinessRuleException):
    """ゲートウェイが既に存在する例外"""
    error_code = "MAP.DUPLICATE_GATEWAY"


class PathNotFoundException(MapDomainException, BusinessRuleException):
    """経路が見つからない例外"""
    error_code = "MAP.PATH_NOT_FOUND"


class ActorBusyException(MapDomainException, BusinessRuleException):
    """アクターがアクション中で操作不能な場合の例外"""
    error_code = "MAP.ACTOR_BUSY"


class PathfindingLimitReachedException(MapDomainException, BusinessRuleException):
    """経路探索の試行回数上限に達した例外"""
    error_code = "MAP.PATHFINDING_LIMIT_REACHED"


class InvalidPathRequestException(MapDomainException, ValidationException):
    """不正な経路探索リクエストの例外"""
    error_code = "MAP.INVALID_PATH_REQUEST"


class PackIdValidationException(MapDomainException, ValidationException):
    """PackIdバリデーション例外"""
    error_code = "MAP.PACK_ID_VALIDATION"


class ChestClosedException(MapDomainException, BusinessRuleException):
    """チェストが閉じているため収納・取得できない例外"""
    error_code = "MAP.CHEST_CLOSED"


class NotAChestException(MapDomainException, BusinessRuleException):
    """対象がチェストではない例外"""
    error_code = "MAP.NOT_A_CHEST"


class ItemNotInChestException(MapDomainException, BusinessRuleException):
    """指定アイテムがチェストに存在しない例外"""
    error_code = "MAP.ITEM_NOT_IN_CHEST"


class ItemAlreadyInChestException(MapDomainException, BusinessRuleException):
    """指定アイテムが既にチェストに存在する例外"""
    error_code = "MAP.ITEM_ALREADY_IN_CHEST"


class NotADoorException(MapDomainException, BusinessRuleException):
    """対象がドアではない例外"""
    error_code = "MAP.NOT_A_DOOR"
