"""
ツール実行の共通ヘルパー。

ToolCommandMapper およびサブマッパー（executors）から共有する。
失敗時の error_code と remediation 付き LlmCommandResultDto を組み立てる。
"""

from typing import Any, Dict, FrozenSet

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)

# 脱出ゲーム定義（spot_graph）で inner_thought を必須にしているツール。欠落時は失敗にせず警告を先頭に付与する。
_ESCAPE_INNER_THOUGHT_REQUIRED: FrozenSet[str] = frozenset(
    {
        TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
        TOOL_NAME_SPOT_GRAPH_EXPLORE,
        TOOL_NAME_SPOT_GRAPH_INTERACT,
        TOOL_NAME_SPOT_GRAPH_WAIT,
    }
)

_INNER_THOUGHT_EMPTY_WARNING_PREFIX = (
    "【警告】inner_thought が空です。次のツール呼び出しでは、"
    "必ずペルソナの口調で短い内心を含めてください。\n\n"
)


def _is_inner_thought_arg_empty(args: Dict[str, Any]) -> bool:
    raw = args.get("inner_thought")
    if raw is None:
        return True
    if not isinstance(raw, str):
        s = str(raw).strip()
        return not s
    return not raw.strip()


def with_inner_thought_empty_warning(
    tool_name: str,
    arguments: Dict[str, Any],
    result: LlmCommandResultDto,
) -> LlmCommandResultDto:
    """成功したが inner_thought が空のとき、LLM 向け message 先頭に警告を付与する（成功は維持）。"""
    if not result.success:
        return result
    if tool_name not in _ESCAPE_INNER_THOUGHT_REQUIRED:
        return result
    if not _is_inner_thought_arg_empty(arguments):
        return result
    return LlmCommandResultDto(
        success=result.success,
        message=_INNER_THOUGHT_EMPTY_WARNING_PREFIX + result.message,
        error_code=result.error_code,
        remediation=result.remediation,
        should_reschedule=result.should_reschedule,
        was_no_op=result.was_no_op,
    )


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


def append_inner_thought_to_message(message: str, args: Dict[str, Any]) -> str:
    """LlmCommandResultDto.message 末尾に、ツール引数の inner_thought を表示用に付与する。"""
    raw = args.get("inner_thought", "")
    if not isinstance(raw, str):
        raw = str(raw) if raw is not None else ""
    s = raw.strip()
    if not s:
        return message
    return f"{message.rstrip()}\n【心の声】{s}"


def invalid_arg_value_result(field_name: str, allowed: str) -> LlmCommandResultDto:
    """列挙値など、引数の値が不正なときの失敗結果を返す。"""
    return LlmCommandResultDto(
        success=False,
        message=f"{field_name} が不正です。次を指定してください: {allowed}。",
        error_code="INVALID_TARGET_LABEL",
        remediation=get_remediation("INVALID_TARGET_LABEL"),
    )
