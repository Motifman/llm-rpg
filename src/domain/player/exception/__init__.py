"""
Playerドメインの例外パッケージ

DDDの原則に従い、ドメイン固有の意味を持つカスタム例外を定義します。
"""

from .player_exceptions import (
    BaseStatusValidationException,
    BaseStatsValidationException,
    ExpTableValidationException,
    GoldValidationException,
    GrowthValidationException,
    HpValidationException,
    InventoryFullException,
    InsufficientGoldException,
    InsufficientMpException,
    MessageValidationException,
    MpValidationException,
    PlayerDomainException,
    PlayerDownedException,
    PlayerIdValidationException,
    PlayerNameValidationException,
    StatGrowthFactorValidationException,
    StaminaValidationException,
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
    "MessageValidationException",
    "MpValidationException",
    "PlayerDomainException",
    "PlayerDownedException",
    "PlayerIdValidationException",
    "PlayerNameValidationException",
    "StatGrowthFactorValidationException",
    "StaminaValidationException",
]
