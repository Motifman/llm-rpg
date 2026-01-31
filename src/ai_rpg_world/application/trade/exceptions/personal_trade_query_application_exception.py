"""
PersonalTradeQueryService専用のアプリケーション例外
"""

from typing import Optional
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.application.common.exceptions import ApplicationException


class PersonalTradeQueryApplicationException(ApplicationException):
    """PersonalTradeQueryアプリケーション層例外"""

    @classmethod
    def from_domain_error(cls, e: DomainException) -> "PersonalTradeQueryApplicationException":
        """ドメイン例外からの変換

        Args:
            e: ドメイン例外

        Returns:
            PersonalTradeQueryApplicationException: 変換されたアプリケーション例外
        """
        return cls(f"Domain error in PersonalTradeQuery usecase: {e.error_code}", cause=e)

    @classmethod
    def invalid_player_id(cls, player_id: int) -> "PersonalTradeQueryApplicationException":
        """無効なプレイヤーIDの場合の例外

        Args:
            player_id: プレイヤーID

        Returns:
            PersonalTradeQueryApplicationException: アプリケーション例外
        """
        return cls(
            f"Invalid player ID: {player_id}",
            player_id=player_id
        )

    @classmethod
    def personal_trades_not_found(cls, player_id: int) -> "PersonalTradeQueryApplicationException":
        """個人取引が見つからない場合の例外

        Args:
            player_id: プレイヤーID

        Returns:
            PersonalTradeQueryApplicationException: アプリケーション例外
        """
        return cls(
            f"No personal trades found for player: {player_id}",
            player_id=player_id
        )

    @classmethod
    def invalid_limit(cls, limit: int) -> "PersonalTradeQueryApplicationException":
        """無効なlimit値の場合の例外

        Args:
            limit: 無効なlimit値

        Returns:
            PersonalTradeQueryApplicationException: アプリケーション例外
        """
        return cls(
            f"Limit must be between 1 and 50, got {limit}",
            limit=limit
        )
