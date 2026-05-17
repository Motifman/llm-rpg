"""sns / trade executor の ActiveGameAppConflictError サニタイズテスト (PR-1)。

Issue #168 + PR #156 のセキュリティ反省を踏まえた回帰防止。
``str(e)`` 漏洩は executor の SNS / Trade enter で発生していた。

検証する不変条件:
- 例外メッセージそのもの (path / 内部 ID 含みうる) は LLM 向け message に
  含めない
- 代わりに ``active_kind`` (GameAppKind の enum 値) など構造化情報だけを使う
- ``error_code="ACTIVE_APP_CONFLICT"`` で remediation_mapping から hint を引く
- サーバログには warning レベルで全文脈を残す (観測性)
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from ai_rpg_world.application.llm.services.executors.sns_executor import (
    SnsToolExecutor,
)
from ai_rpg_world.application.llm.services.executors.trade_executor import (
    TradeToolExecutor,
)
from ai_rpg_world.application.social.services.active_game_app_session_service import (
    ActiveGameAppConflictError,
)
from ai_rpg_world.application.social.services.game_app_kind import GameAppKind


def _build_sns_executor_with_conflict(sensitive_text: str) -> SnsToolExecutor:
    """sns enter 時に必ず ActiveGameAppConflictError を投げる Executor を作る。"""
    sns_mode_session = MagicMock()
    sns_mode_session.enter_sns_mode.side_effect = ActiveGameAppConflictError(
        sensitive_text,
        player_id=42,
        active_kind=GameAppKind.TRADE,
        requested_kind=GameAppKind.SNS,
    )
    return SnsToolExecutor(sns_mode_session=sns_mode_session)


def _build_trade_executor_with_conflict(sensitive_text: str) -> TradeToolExecutor:
    sns_mode_session = MagicMock()
    sns_mode_session.enter_trade_mode.side_effect = ActiveGameAppConflictError(
        sensitive_text,
        player_id=42,
        active_kind=GameAppKind.SNS,
        requested_kind=GameAppKind.TRADE,
    )
    return TradeToolExecutor(sns_mode_session=sns_mode_session)


class TestSnsEnterSanitization:
    """sns_enter で ActiveGameAppConflictError が来たときのサニタイズ。"""

    def test_str_exc_is_not_leaked_to_message(self, caplog) -> None:
        """例外メッセージに含まれる機微情報が LLM 向け message に出ない。"""
        sensitive = "/home/user/secret_path: token=abcd1234 内部ID=xxx"
        executor = _build_sns_executor_with_conflict(sensitive)
        with caplog.at_level(
            logging.WARNING,
            logger="ai_rpg_world.application.llm.services.executors.sns_executor",
        ):
            result = executor._execute_sns_enter(player_id=42, args={})
        assert result.success is False
        assert result.error_code == "ACTIVE_APP_CONFLICT"
        # 漏洩しないこと
        assert "/home/user/secret_path" not in result.message
        assert "token=abcd1234" not in result.message
        assert "内部ID" not in result.message
        # サーバログには文脈が残る (観測性)
        assert any(
            "active=" in r.message and "requested=" in r.message
            for r in caplog.records
        )

    def test_message_contains_structured_kind(self) -> None:
        """LLM への message には ``active_kind.value`` (= 安全な enum 値) が入る。"""
        executor = _build_sns_executor_with_conflict("...")
        result = executor._execute_sns_enter(player_id=42, args={})
        # active_kind=GameAppKind.TRADE → value="trade" が入る
        assert "trade" in result.message.lower()

    def test_remediation_is_populated(self) -> None:
        """remediation が ``ACTIVE_APP_CONFLICT`` 用に埋まる。"""
        executor = _build_sns_executor_with_conflict("...")
        result = executor._execute_sns_enter(player_id=42, args={})
        assert result.remediation is not None and result.remediation != ""


class TestTradeEnterSanitization:
    """trade_enter で同様のサニタイズ。"""

    def test_str_exc_is_not_leaked_to_message(self, caplog) -> None:
        sensitive = "/etc/passwd の中身が雰囲気で書かれた攻撃文字列"
        executor = _build_trade_executor_with_conflict(sensitive)
        with caplog.at_level(
            logging.WARNING,
            logger="ai_rpg_world.application.llm.services.executors.trade_executor",
        ):
            result = executor._execute_trade_enter(player_id=42, args={})
        assert result.success is False
        assert result.error_code == "ACTIVE_APP_CONFLICT"
        # 漏洩しないこと
        assert "/etc/passwd" not in result.message
        assert "攻撃" not in result.message
        # サーバログには文脈
        assert any(
            "active=" in r.message and "requested=" in r.message
            for r in caplog.records
        )

    def test_message_contains_structured_kind(self) -> None:
        executor = _build_trade_executor_with_conflict("...")
        result = executor._execute_trade_enter(player_id=42, args={})
        # active_kind=GameAppKind.SNS → value="sns" が入る
        assert "sns" in result.message.lower()

    def test_remediation_is_populated(self) -> None:
        executor = _build_trade_executor_with_conflict("...")
        result = executor._execute_trade_enter(player_id=42, args={})
        assert result.remediation is not None and result.remediation != ""
