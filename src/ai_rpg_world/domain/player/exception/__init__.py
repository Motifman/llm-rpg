"""
Playerドメインの例外パッケージ

DDDの原則に従い、ドメイン固有の意味を持つカスタム例外を定義します。
"""

from .player_exceptions import (
    BaseStatsValidationException,
    BaseStatusValidationException,
    ExpTableValidationException,
    GoldValidationException,
    GrowthValidationException,
    HpValidationException,
    InsufficientGoldException,
    InsufficientHpException,
    InsufficientMpException,
    InsufficientStaminaException,
    InventoryFullException,
    MessageValidationException,
    MpValidationException,
    PlayerDomainException,
    PlayerDownedException,
    PlayerIdValidationException,
    PlayerNameValidationException,
    PlayerNotDownedException,
    PlayerOutcomeRegistryValidationException,
    SpeechValidationException,
    SpotNavigationStateInvalidException,
    StaminaValidationException,
    StatGrowthFactorValidationException,
)

__all__ = [
    "BaseStatusValidationException",
    "BaseStatsValidationException",
    "ExpTableValidationException",
    "GoldValidationException",
    "GrowthValidationException",
    "HpValidationException",
    "InventoryFullException",
    "InsufficientGoldException",
    "InsufficientMpException",
    "InsufficientHpException",
    "InsufficientStaminaException",
    "MessageValidationException",
    "MpValidationException",
    "PlayerDomainException",
    "PlayerDownedException",
    "PlayerNotDownedException",
    "PlayerOutcomeRegistryValidationException",
    "PlayerIdValidationException",
    "PlayerNameValidationException",
    "SpeechValidationException",
    "SpotNavigationStateInvalidException",
    "StatGrowthFactorValidationException",
    "StaminaValidationException",
]
