"""単一 active app slot（プロセス内・プレイヤー単位）。

SNS と Trade は同時にアクティブにならない。別アプリへ入る前に明示的に exit する契約と整合させる。
"""

from __future__ import annotations

from ai_rpg_world.application.common.exceptions import ApplicationException
from ai_rpg_world.application.social.services.game_app_kind import GameAppKind


class ActiveGameAppConflictError(ApplicationException):
    """既に別アプリがアクティブなときに enter が拒否された。"""

    def __init__(
        self,
        message: str,
        *,
        player_id: int,
        active_kind: GameAppKind,
        requested_kind: GameAppKind,
    ) -> None:
        super().__init__(message, player_id=player_id, active_kind=active_kind, requested_kind=requested_kind)
        self.player_id = player_id
        self.active_kind = active_kind
        self.requested_kind = requested_kind


class ActiveGameAppSessionService:
    """player_id ごとに高々 1 つの GameAppKind を保持する。"""

    def __init__(self) -> None:
        self._active_by_player: dict[int, GameAppKind] = {}

    def get_active_app(self, player_id: int) -> GameAppKind:
        return self._active_by_player.get(player_id, GameAppKind.NONE)

    def enter_sns(self, player_id: int) -> None:
        current = self.get_active_app(player_id)
        if current == GameAppKind.SNS:
            return
        if current == GameAppKind.TRADE:
            raise ActiveGameAppConflictError(
                "Trade アプリがアクティブなため SNS に入れません。先に Trade を終了してください。",
                player_id=player_id,
                active_kind=current,
                requested_kind=GameAppKind.SNS,
            )
        self._active_by_player[player_id] = GameAppKind.SNS

    def exit_sns(self, player_id: int) -> None:
        if self.get_active_app(player_id) == GameAppKind.SNS:
            self._active_by_player[player_id] = GameAppKind.NONE

    def enter_trade(self, player_id: int) -> None:
        current = self.get_active_app(player_id)
        if current == GameAppKind.TRADE:
            return
        if current == GameAppKind.SNS:
            raise ActiveGameAppConflictError(
                "SNS アプリがアクティブなため取引所に入れません。先に SNS を終了してください。",
                player_id=player_id,
                active_kind=current,
                requested_kind=GameAppKind.TRADE,
            )
        self._active_by_player[player_id] = GameAppKind.TRADE

    def exit_trade(self, player_id: int) -> None:
        if self.get_active_app(player_id) == GameAppKind.TRADE:
            self._active_by_player[player_id] = GameAppKind.NONE


__all__ = [
    "ActiveGameAppConflictError",
    "ActiveGameAppSessionService",
]
