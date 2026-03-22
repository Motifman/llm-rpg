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


def invalid_arg_result(field_name: str) -> LlmCommandResultDto:
    """必須引数未指定時の失敗結果を返す。"""
    return LlmCommandResultDto(
        success=False,
        message=f"{field_name} が指定されていません。",
        error_code="INVALID_TARGET_LABEL",
        remediation=get_remediation("INVALID_TARGET_LABEL"),
    )


def invalid_arg_value_result(field_name: str, allowed: str) -> LlmCommandResultDto:
    """列挙値など、引数の値が不正なときの失敗結果を返す。"""
    return LlmCommandResultDto(
        success=False,
        message=f"{field_name} が不正です。次を指定してください: {allowed}。",
        error_code="INVALID_TARGET_LABEL",
        remediation=get_remediation("INVALID_TARGET_LABEL"),
    )
