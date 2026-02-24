"""
ギルドコマンド関連の例外定義
"""

from typing import Optional
from ai_rpg_world.application.guild.exceptions.base_exception import GuildApplicationException


class GuildCommandException(GuildApplicationException):
    """ギルドコマンド関連の例外"""

    def __init__(
        self,
        message: str,
        error_code: str = None,
        user_id: Optional[int] = None,
        guild_id: Optional[int] = None,
        **context,
    ):
        all_context = context.copy()
        if user_id is not None:
            all_context["user_id"] = user_id
        if guild_id is not None:
            all_context["guild_id"] = guild_id
        super().__init__(message, error_code, **all_context)


class GuildCreationException(GuildCommandException):
    """ギルド作成関連の例外"""

    def __init__(self, message: str, user_id: Optional[int] = None):
        super().__init__(message, "GUILD_CREATION_ERROR", user_id=user_id)


class GuildNotFoundForCommandException(GuildCommandException):
    """コマンド実行時にギルドが見つからない場合の例外"""

    def __init__(self, guild_id: int, command_name: str):
        message = f"コマンド '{command_name}' の実行時にギルドが見つかりません: {guild_id}"
        super().__init__(message, "GUILD_NOT_FOUND_FOR_COMMAND", guild_id=guild_id)


class GuildAccessDeniedException(GuildCommandException):
    """ギルドに対するアクション権限がない場合の例外"""

    def __init__(self, guild_id: int, user_id: int, action: str):
        message = f"ギルド {guild_id} に対するアクション '{action}' の実行権限がありません: ユーザー {user_id}"
        super().__init__(message, "GUILD_ACCESS_DENIED", guild_id=guild_id, user_id=user_id)


class GuildBankNotFoundForCommandException(GuildCommandException):
    """コマンド実行時にギルド金庫が見つからない場合の例外"""

    def __init__(self, guild_id: int, command_name: str):
        message = f"コマンド '{command_name}' の実行時にギルド金庫が見つかりません: {guild_id}"
        super().__init__(message, "GUILD_BANK_NOT_FOUND_FOR_COMMAND", guild_id=guild_id)


class InsufficientGuildBankBalanceForCommandException(GuildCommandException):
    """ギルド金庫の残高不足で出金できない場合の例外"""

    def __init__(self, guild_id: int, requested: int, available: int):
        message = f"ギルド金庫の残高不足: リクエスト {requested}, 残高 {available}"
        super().__init__(message, "GUILD_BANK_INSUFFICIENT_BALANCE", guild_id=guild_id)
