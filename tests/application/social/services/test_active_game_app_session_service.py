"""ActiveGameAppSessionService: 単一 active app slot と enter 拒否。"""

import pytest

from ai_rpg_world.application.social.services.active_game_app_session_service import (
    ActiveGameAppConflictError,
    ActiveGameAppSessionService,
)
from ai_rpg_world.application.social.services.game_app_kind import GameAppKind


class TestActiveGameAppSessionService:
    def test_none_to_sns_to_none_to_trade(self) -> None:
        s = ActiveGameAppSessionService()
        pid = 1
        assert s.get_active_app(pid) == GameAppKind.NONE

        s.enter_sns(pid)
        assert s.get_active_app(pid) == GameAppKind.SNS

        s.exit_sns(pid)
        assert s.get_active_app(pid) == GameAppKind.NONE

        s.enter_trade(pid)
        assert s.get_active_app(pid) == GameAppKind.TRADE

        s.exit_trade(pid)
        assert s.get_active_app(pid) == GameAppKind.NONE

    def test_enter_sns_idempotent(self) -> None:
        s = ActiveGameAppSessionService()
        s.enter_sns(1)
        s.enter_sns(1)
        assert s.get_active_app(1) == GameAppKind.SNS

    def test_enter_trade_idempotent(self) -> None:
        s = ActiveGameAppSessionService()
        s.enter_trade(1)
        s.enter_trade(1)
        assert s.get_active_app(1) == GameAppKind.TRADE

    def test_enter_sns_rejected_when_trade_active(self) -> None:
        s = ActiveGameAppSessionService()
        s.enter_trade(1)
        with pytest.raises(ActiveGameAppConflictError) as ei:
            s.enter_sns(1)
        assert ei.value.active_kind == GameAppKind.TRADE
        assert ei.value.requested_kind == GameAppKind.SNS

    def test_enter_trade_rejected_when_sns_active(self) -> None:
        s = ActiveGameAppSessionService()
        s.enter_sns(1)
        with pytest.raises(ActiveGameAppConflictError) as ei:
            s.enter_trade(1)
        assert ei.value.active_kind == GameAppKind.SNS
        assert ei.value.requested_kind == GameAppKind.TRADE

    def test_exit_sns_noop_when_none(self) -> None:
        s = ActiveGameAppSessionService()
        s.exit_sns(1)
        assert s.get_active_app(1) == GameAppKind.NONE

    def test_exit_sns_noop_when_trade(self) -> None:
        s = ActiveGameAppSessionService()
        s.enter_trade(1)
        s.exit_sns(1)
        assert s.get_active_app(1) == GameAppKind.TRADE

    def test_exit_trade_noop_when_sns(self) -> None:
        s = ActiveGameAppSessionService()
        s.enter_sns(1)
        s.exit_trade(1)
        assert s.get_active_app(1) == GameAppKind.SNS
