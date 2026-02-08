"""
天候システムに関連する例外定義
"""

from ai_rpg_world.domain.world.exception.map_exception import MapDomainException
from ai_rpg_world.domain.common.exception import ValidationException, BusinessRuleException


class WeatherDomainException(MapDomainException):
    """天候ドメインの基底例外"""
    domain = "world.weather"


class WeatherIntensityValidationException(WeatherDomainException, ValidationException):
    """天候強度のバリデーション例外"""
    error_code = "WEATHER.INTENSITY_VALIDATION"


class WeatherZoneIdValidationException(WeatherDomainException, ValidationException):
    """天候ゾーンIDのバリデーション例外"""
    error_code = "WEATHER.ZONE_ID_VALIDATION"


class WeatherZoneNameValidationException(WeatherDomainException, ValidationException):
    """天候ゾーン名のバリデーション例外"""
    error_code = "WEATHER.ZONE_NAME_VALIDATION"


class WeatherZoneSpotNotFoundException(WeatherDomainException, BusinessRuleException):
    """天候ゾーンにスポットが見つからない場合の例外"""
    error_code = "WEATHER.SPOT_NOT_FOUND"
