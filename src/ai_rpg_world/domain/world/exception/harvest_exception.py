"""
採取システムに関連する例外定義
"""

from ai_rpg_world.domain.world.exception.map_exception import MapDomainException
from ai_rpg_world.domain.common.exception import BusinessRuleException, ValidationException


class HarvestDomainException(MapDomainException):
    """採取ドメインの基底例外"""
    domain = "world.harvest"


class ResourceExhaustedException(HarvestDomainException, BusinessRuleException):
    """資源が枯渇している場合の例外"""
    error_code = "HARVEST.RESOURCE_EXHAUSTED"


class ToolRequirementException(HarvestDomainException, BusinessRuleException):
    """必要なツールを持っていない場合の例外"""
    error_code = "HARVEST.TOOL_REQUIREMENT"


class HarvestQuantityValidationException(HarvestDomainException, ValidationException):
    """採取量のバリデーション例外"""
    error_code = "HARVEST.QUANTITY_VALIDATION"


class HarvestIntervalValidationException(HarvestDomainException, ValidationException):
    """採取間隔のバリデーション例外"""
    error_code = "HARVEST.INTERVAL_VALIDATION"


class NotHarvestableException(HarvestDomainException, BusinessRuleException):
    """オブジェクトが採取可能でない場合の例外"""
    error_code = "HARVEST.NOT_HARVESTABLE"


class HarvestInProgressException(HarvestDomainException, BusinessRuleException):
    """既に別の者が採取中の場合の例外"""
    error_code = "HARVEST.IN_PROGRESS"


class HarvestNotStartedException(HarvestDomainException, BusinessRuleException):
    """採取アクションが開始されていない場合の例外"""
    error_code = "HARVEST.NOT_STARTED"
