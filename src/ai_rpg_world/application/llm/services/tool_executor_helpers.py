"""
ツール実行の共通ヘルパー。

ToolCommandMapper およびサブマッパー（executors）から共有する。
失敗時の error_code と remediation 付き LlmCommandResultDto を組み立てる。
"""

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.remediation_mapping import get_remediation


def unknown_tool(message: str) -> LlmCommandResultDto:
    """未設定・未対応ツール用の失敗結果を返す。"""
    return LlmCommandResultDto(
        success=False,
        message=message,
        error_code="UNKNOWN_TOOL",
        remediation=get_remediation("UNKNOWN_TOOL"),
    )


def exception_result(e: Exception) -> LlmCommandResultDto:
    """例外を捕捉した際の失敗結果を返す。error_code と remediation を付与。"""
    error_code = getattr(e, "error_code", "SYSTEM_ERROR")
    return LlmCommandResultDto(
        success=False,
        message=str(e),
        error_code=error_code,
        remediation=get_remediation(error_code),
    )
