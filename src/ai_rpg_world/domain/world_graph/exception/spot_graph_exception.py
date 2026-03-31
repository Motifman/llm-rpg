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
