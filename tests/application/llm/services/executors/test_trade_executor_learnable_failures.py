"""Issue #168 PR-6: ``TradeToolExecutor`` の bare failure (2 件) を learnable
に統一する。

PR #170 で enter の ``ActiveGameAppConflictError`` サニタイズは対応済み。
本 PR は ``open_page`` の「未対応の画面」フォールバックと ``switch_tab`` の
画面制約に ``error_code`` + ``remediation`` を付ける。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.llm.services.executors.trade_executor import (
    TradeToolExecutor,
)
from ai_rpg_world.application.trade.trade_virtual_pages.kinds import (
    TradeVirtualPageKind,
)


def _assert_learnable(result, expected_error_code: str) -> None:
    assert result.success is False
    assert result.error_code == expected_error_code
    assert result.remediation


class TestSwitchTabPageRestriction:
    """``_execute_switch_tab`` は my_trades 以外では使えない。"""

    def test_switch_tab_off_my_trades_is_learnable(self) -> None:
        sess = MagicMock()
        sess.get_state.return_value = MagicMock(
            page_kind=TradeVirtualPageKind.MARKET
        )
        executor = TradeToolExecutor(
            sns_mode_session=MagicMock(),
            trade_page_session=sess,
        )
        result = executor._execute_switch_tab(
            player_id=1, args={"tab": "incoming"}
        )
        _assert_learnable(result, "TRADE_PAGE_NOT_SUPPORTED")
        # remediation 含む遷移ヒント
        assert "my_trades" in result.message


class TestAllFailuresHaveLearnableShape:
    """ファイル走査による不変条件: bare ``success=False`` が残らない。"""

    def test_no_bare_failure_in_trade_executor_source(self) -> None:
        import re
        from pathlib import Path

        src = (
            Path(__file__).resolve().parents[5]
            / "src"
            / "ai_rpg_world"
            / "application"
            / "llm"
            / "services"
            / "executors"
            / "trade_executor.py"
        ).read_text(encoding="utf-8")
        for m in re.finditer(r"success=False", src):
            window = src[m.start(): m.start() + 600]
            assert "error_code" in window, (
                f"bare success=False at pos {m.start()}: {window[:200]!r}"
            )
