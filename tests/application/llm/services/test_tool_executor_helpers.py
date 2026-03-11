"""tool_executor_helpers のユニットテスト"""

import pytest

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
        exc = ValueError("invalid value")
        result = exception_result(exc)
        assert result.success is False
        assert result.message == "invalid value"
        assert result.error_code == "SYSTEM_ERROR"
        assert result.remediation is not None

    def test_exception_with_error_code_uses_it(self):
        class AppError(Exception):
            error_code = "INVALID_TARGET_LABEL"

        exc = AppError("対象が不正です")
        result = exception_result(exc)
        assert result.success is False
        assert result.error_code == "INVALID_TARGET_LABEL"
