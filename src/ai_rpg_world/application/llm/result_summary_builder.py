"""
LlmCommandResultDto から IActionResultStore 用の result_summary 文字列を組み立てる。
"""

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto


def build_result_summary(dto: LlmCommandResultDto) -> str:
    """
    成功時は message をそのまま、失敗時は「失敗。{message} 対処: {remediation}」を返す。
    """
    if not isinstance(dto, LlmCommandResultDto):
        raise TypeError("dto must be LlmCommandResultDto")
    if dto.success:
        return dto.message
    parts = [f"失敗。{dto.message}"]
    if dto.remediation:
        parts.append(f"対処: {dto.remediation}")
    return " ".join(parts)
