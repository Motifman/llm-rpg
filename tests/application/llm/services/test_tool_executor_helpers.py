"""tool_executor_helpers のユニットテスト"""

import pytest

from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    exception_result,
    unknown_tool,
)


class TestUnknownTool:
    """unknown_tool() の振る舞い"""

    def test_returns_failure_dto(self):
        result = unknown_tool("ツールは利用できません。")
        assert isinstance(result, LlmCommandResultDto)
        assert result.success is False
        assert result.message == "ツールは利用できません。"
        assert result.error_code == "UNKNOWN_TOOL"
        assert result.remediation is not None
        assert "利用可能" in result.remediation or "ツール" in result.remediation


class TestExceptionResult:
    """exception_result() の振る舞い"""

    def test_generic_exception_returns_system_error(self):
        """PR-δ (Y_after_pr639_640 audit): 純英語 exception は LLM 向け
        日本語 fallback に置換される (旧: str(e) 直渡し)。error_code は
        SYSTEM_ERROR に落ちる。"""
        exc = ValueError("invalid value")
        result = exception_result(exc)
        assert result.success is False
        # PR-δ: 英語 message は LLM に漏らさず日本語 fallback
        assert "invalid value" not in result.message
        assert "システム" in result.message or "エラー" in result.message
        assert result.error_code == "SYSTEM_ERROR"
        assert result.remediation is not None

    def test_exception_with_error_code_uses_it(self):
        class AppError(Exception):
            error_code = "INVALID_TARGET_LABEL"

        exc = AppError("対象が不正です")
        result = exception_result(exc)
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"

    def test_post_commit_exception_reports_committed_success_without_retry(self):
        """commit後処理だけが失敗した操作は成功として伝え、同じ操作の再実行を促さない。"""
        exc = CommandPostCommitException(
            handoff_error=RuntimeError("delivery failed")
        )

        result = exception_result(exc)

        assert result.success is True
        assert result.error_code == "COMMAND_COMMITTED_POST_PROCESSING_FAILED"
        assert result.should_reschedule is False
        assert "反映済み" in result.message
        assert "繰り返さ" in result.message
        assert "再試行" not in result.message
        assert result.remediation is not None
        assert "繰り返さ" in result.remediation
        assert result.trace_payload == {
            "command_committed": True,
            "post_commit_cleanup_error_type": None,
            "post_commit_handoff_error_type": "RuntimeError",
            "post_commit_outbox_error_type": None,
        }
