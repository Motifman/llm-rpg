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
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)

# 脱出ゲーム定義（spot_graph）で inner_thought を必須にしているツール。欠落時は失敗にせず警告を先頭に付与する。
_ESCAPE_INNER_THOUGHT_REQUIRED: FrozenSet[str] = frozenset(
    {
        TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
        TOOL_NAME_SPOT_GRAPH_EXPLORE,
        TOOL_NAME_SPOT_GRAPH_INTERACT,
        TOOL_NAME_SPOT_GRAPH_LISTEN,
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


def _has_japanese_char(s: str) -> bool:
    """s に日本語文字 (hiragana / katakana / kanji / 全角記号系) が
    1 文字でも含まれるか。LLM 向け sanitizer で「message は日本語で
    書かれているか」の heuristic に使う。"""
    for ch in s:
        code = ord(ch)
        # Hiragana (3040-309F), Katakana (30A0-30FF), CJK (4E00-9FFF),
        # Halfwidth Katakana (FF66-FF9F), 全角記号 (FF00-FFEF) 等の
        # 主要日本語ブロックをカバー。厳密でなくていい (英語混じりを
        # 「日本語 message」として通す heuristic なので誤検出コスト小)。
        if (
            0x3040 <= code <= 0x309F
            or 0x30A0 <= code <= 0x30FF
            or 0x4E00 <= code <= 0x9FFF
            or 0xFF00 <= code <= 0xFFEF
        ):
            return True
    return False


# PR-δ (Y_after_pr639_640 audit 後続): exception_result が LLM に返す
# 汎用日本語 fallback。純英語 Exception (Python 組み込み例外の生 message
# や、application 層で raise される英語 error) が LLM に漏れないよう、
# 「日本語文字が 1 文字も無い」message はこの汎用文言に置換する。
_SANITIZED_SYSTEM_ERROR_MESSAGE = (
    "システムエラーが発生しました。少し tick を進めてから再試行するか、"
    "別の tool を選んでください。"
)


def exception_result(e: Exception) -> LlmCommandResultDto:
    """例外を捕捉した際の失敗結果を返す。error_code と remediation を付与。

    PR-δ (Y_after_pr639_640 audit): LLM に届く message から英語 + 内部 ID
    を排除するため、以下の分岐で sanitize する:

    1. exception が ``error_code`` 属性を持つ (= domain exception): 従来通り
       str(e) を尊重 (domain 層で LLM 向け日本語 message が組まれている前提)
    2. str(e) に日本語文字が 1 文字でも含まれる: そのまま尊重
       (application 層の日本語 ApplicationException 等の後方互換)
    3. str(e) が空 or 純 ASCII: 汎用日本語 fallback に置換
       (Python 組み込み ``KeyError``/``ValueError``/``RuntimeError`` 等)

    domain exception が既に日本語 message を持っている場合、``error_code``
    属性の存在によって pass-through する。error_code 無しでも日本語なら
    2 の経路で救う。
    """
    error_code = getattr(e, "error_code", "SYSTEM_ERROR")
    has_domain_error_code = hasattr(e, "error_code")
    raw_message = str(e)
    if has_domain_error_code:
        # domain exception。message は既に LLM 向けに整備されている
        message = raw_message
    elif raw_message and _has_japanese_char(raw_message):
        # 日本語 (混じり含む) message。application 層の意図的な日本語 raise
        message = raw_message
    else:
        # 純 ASCII の Python 組み込み exception 等 → 汎用日本語 fallback
        message = _SANITIZED_SYSTEM_ERROR_MESSAGE
    return LlmCommandResultDto(
        success=False,
        message=message,
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
