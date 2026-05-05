"""Spot Graph ドメインの例外定義"""

from ai_rpg_world.domain.common.exception import (
    BusinessRuleException,
    DomainException,
    ValidationException,
)


class SpotGraphDomainException(DomainException):
    """Spot Graph ドメインの基底例外"""

    domain = "world_graph"


class EntityIdValidationException(SpotGraphDomainException, ValidationException):
    """エンティティIDバリデーション例外"""
    error_code = "WORLD_GRAPH.ENTITY_ID_VALIDATION"


class ConnectionIdValidationException(SpotGraphDomainException, ValidationException):
    """接続IDバリデーション例外"""
    error_code = "WORLD_GRAPH.CONNECTION_ID_VALIDATION"


class SpotGraphIdValidationException(SpotGraphDomainException, ValidationException):
    """スポットグラフ集約IDバリデーション例外"""
    error_code = "WORLD_GRAPH.GRAPH_ID_VALIDATION"


class SpotNotInGraphException(SpotGraphDomainException, BusinessRuleException):
    """グラフに存在しないスポットを参照した"""
    error_code = "WORLD_GRAPH.SPOT_NOT_IN_GRAPH"


class UnknownConnectionException(SpotGraphDomainException, BusinessRuleException):
    """未知の接続ID"""
    error_code = "WORLD_GRAPH.UNKNOWN_CONNECTION"


class EntityNotInGraphException(SpotGraphDomainException, BusinessRuleException):
    """エンティティがグラフ上に配置されていない"""
    error_code = "WORLD_GRAPH.ENTITY_NOT_IN_GRAPH"


class EntityNotAtSpotException(SpotGraphDomainException, BusinessRuleException):
    """エンティティが期待したスポットにいない"""
    error_code = "WORLD_GRAPH.ENTITY_NOT_AT_SPOT"


class ConnectionNotPassableException(SpotGraphDomainException, BusinessRuleException):
    """接続が通行不能（閉鎖または条件未満足）"""
    error_code = "WORLD_GRAPH.CONNECTION_NOT_PASSABLE"


class DuplicateSpotException(SpotGraphDomainException, BusinessRuleException):
    """同一スポットIDの重複登録"""
    error_code = "WORLD_GRAPH.DUPLICATE_SPOT"


class DuplicateConnectionIdException(SpotGraphDomainException, BusinessRuleException):
    """接続IDの重複"""
    error_code = "WORLD_GRAPH.DUPLICATE_CONNECTION_ID"


class SpotPresenceInvariantException(SpotGraphDomainException, BusinessRuleException):
    """在席情報の不整合"""
    error_code = "WORLD_GRAPH.PRESENCE_INVARIANT"


class SubLocationIdValidationException(SpotGraphDomainException, ValidationException):
    """サブロケーションIDバリデーション例外"""
    error_code = "WORLD_GRAPH.SUB_LOCATION_ID_VALIDATION"


class SpotObjectIdValidationException(SpotGraphDomainException, ValidationException):
    """スポットオブジェクトIDバリデーション例外"""
    error_code = "WORLD_GRAPH.SPOT_OBJECT_ID_VALIDATION"


class UnknownSpotObjectException(SpotGraphDomainException, BusinessRuleException):
    """スポット内に存在しないオブジェクトを参照した"""
    error_code = "WORLD_GRAPH.UNKNOWN_SPOT_OBJECT"


class InteractionNotFoundException(SpotGraphDomainException, BusinessRuleException):
    """指定した操作名のインタラクションがない"""
    error_code = "WORLD_GRAPH.INTERACTION_NOT_FOUND"


class InteractionNotAllowedException(SpotGraphDomainException, BusinessRuleException):
    """インタラクションの前提条件を満たしていない"""
    error_code = "WORLD_GRAPH.INTERACTION_NOT_ALLOWED"


class UnsupportedInteractionEffectException(SpotGraphDomainException, BusinessRuleException):
    """未対応の interaction effect が指定された"""
    error_code = "WORLD_GRAPH.UNSUPPORTED_INTERACTION_EFFECT"


class SpotTravelUnreachableException(SpotGraphDomainException, BusinessRuleException):
    """指定スポットへの経路が存在しない（または到達不能）"""
    error_code = "WORLD_GRAPH.SPOT_TRAVEL_UNREACHABLE"


class SpotTravelAlreadyInProgressException(SpotGraphDomainException, BusinessRuleException):
    """既にスポット間移動中のときに再度移動開始しようとした"""
    error_code = "WORLD_GRAPH.SPOT_TRAVEL_ALREADY_IN_PROGRESS"


class DayNightPhaseValidationException(SpotGraphDomainException, ValidationException):
    """昼夜サイクルのフェーズ定義バリデーション例外"""
    error_code = "WORLD_GRAPH.DAY_NIGHT_PHASE_VALIDATION"


class DayNightCycleValidationException(SpotGraphDomainException, ValidationException):
    """昼夜サイクル定義バリデーション例外"""
    error_code = "WORLD_GRAPH.DAY_NIGHT_CYCLE_VALIDATION"


class TimeOfDayValidationException(SpotGraphDomainException, ValidationException):
    """TimeOfDay 値オブジェクトのバリデーション例外"""
    error_code = "WORLD_GRAPH.TIME_OF_DAY_VALIDATION"


class AmbientSoundFilterValidationException(SpotGraphDomainException, ValidationException):
    """環境音フィルタのバリデーション例外"""
    error_code = "WORLD_GRAPH.AMBIENT_SOUND_FILTER_VALIDATION"


class AmbientSoundDefValidationException(SpotGraphDomainException, ValidationException):
    """環境音定義のバリデーション例外"""
    error_code = "WORLD_GRAPH.AMBIENT_SOUND_DEF_VALIDATION"


class AmbientSoundAtlasValidationException(SpotGraphDomainException, ValidationException):
    """環境音 atlas のバリデーション例外"""
    error_code = "WORLD_GRAPH.AMBIENT_SOUND_ATLAS_VALIDATION"


class AmbientSoundConfigValidationException(SpotGraphDomainException, ValidationException):
    """環境音設定のバリデーション例外"""
    error_code = "WORLD_GRAPH.AMBIENT_SOUND_CONFIG_VALIDATION"

