"""
Guildドメインの例外定義

DDDの原則に従い、ドメイン固有の意味を持つカスタム例外を使用します。
全てのGuildドメイン例外はGuildDomainExceptionと適切なカテゴリ例外を多重継承し、
エラーコードは"GUILD.xxx"の形式で統一します。
"""

from ai_rpg_world.domain.common.exception import (
    BusinessRuleException,
    DomainException,
    StateException,
    ValidationException,
)


class GuildDomainException(DomainException):
    """Guildドメインの基底例外

    全てのGuildドメイン例外はこのクラスを継承します。
    """
    domain = "guild"


# ===== 具体的な例外クラス =====

class GuildIdValidationException(GuildDomainException, ValidationException):
    """ギルドIDバリデーション例外"""
    error_code = "GUILD.ID_VALIDATION"


class InvalidGuildStatusException(GuildDomainException, StateException):
    """無効なギルド状態例外"""
    error_code = "GUILD.INVALID_STATUS"


class CannotJoinGuildException(GuildDomainException, BusinessRuleException):
    """ギルドに参加できない例外"""
    error_code = "GUILD.CANNOT_JOIN"


class CannotLeaveGuildException(GuildDomainException, BusinessRuleException):
    """ギルドから脱退できない例外"""
    error_code = "GUILD.CANNOT_LEAVE"


class CannotChangeRoleException(GuildDomainException, BusinessRuleException):
    """役職を変更できない例外"""
    error_code = "GUILD.CANNOT_CHANGE_ROLE"


class NotGuildMemberException(GuildDomainException, BusinessRuleException):
    """ギルドメンバーでない例外"""
    error_code = "GUILD.NOT_MEMBER"


class InsufficientGuildPermissionException(GuildDomainException, BusinessRuleException):
    """ギルド権限不足例外"""
    error_code = "GUILD.INSUFFICIENT_PERMISSION"


class AlreadyGuildMemberException(GuildDomainException, StateException):
    """既にギルドメンバーである例外"""
    error_code = "GUILD.ALREADY_MEMBER"


class InsufficientGuildBankBalanceException(GuildDomainException, BusinessRuleException):
    """ギルド金庫の残高不足例外"""
    error_code = "GUILD.INSUFFICIENT_BANK_BALANCE"


class CannotDisbandGuildException(GuildDomainException, BusinessRuleException):
    """ギルドを解散できない例外（リーダーのみ解散可能）"""
    error_code = "GUILD.CANNOT_DISBAND"
