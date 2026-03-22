"""ゲーム内 SNS モード（アプリ起動メタファ）のセッション状態。

永続化は行わずプロセス内の dict で player_id ごとに ON/OFF を保持する。
LLM ツール sns_enter / sns_logout と PlayerCurrentStateDto の is_sns_mode_active の参照点を共有する。

真実の状態は ActiveGameAppSessionService の単一スロットに保持し、本クラスは SNS 向け API を提供する。
"""


from __future__ import annotations

from typing import Optional

from ai_rpg_world.application.social.services.active_game_app_session_service import (
    ActiveGameAppSessionService,
)
from ai_rpg_world.application.social.services.game_app_kind import GameAppKind


class SnsModeSessionService:
    """SNS モード ON/OFF をセッションとして保持するアプリケーションサービス。"""

    def __init__(
        self,
        active_game_app_session: Optional[ActiveGameAppSessionService] = None,
    ) -> None:
        self._active_app = active_game_app_session or ActiveGameAppSessionService()

    @property
    def active_game_app_session(self) -> ActiveGameAppSessionService:
        return self._active_app

    def is_sns_mode_active(self, player_id: int) -> bool:
        return self._active_app.get_active_app(player_id) == GameAppKind.SNS

    def enter_sns_mode(self, player_id: int) -> None:
        self._active_app.enter_sns(player_id)

    def exit_sns_mode(self, player_id: int) -> None:
        self._active_app.exit_sns(player_id)

    def enter_trade_mode(self, player_id: int) -> None:
        """取引所アプリをフォアグラウンドにする（単一スロット。SNS アクティブ時は拒否）。"""
        self._active_app.enter_trade(player_id)

    def exit_trade_mode(self, player_id: int) -> None:
        self._active_app.exit_trade(player_id)

    def is_trade_mode_active(self, player_id: int) -> bool:
        return self._active_app.get_active_app(player_id) == GameAppKind.TRADE


__all__ = ["SnsModeSessionService"]
