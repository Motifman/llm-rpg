"""result_summary_builder（build_result_summary）のテスト（正常・例外）"""

import pytest

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.result_summary_builder import build_result_summary


class TestBuildResultSummary:
    """build_result_summary の正常・例外ケース"""

    def test_success_returns_message_as_is(self):
        """成功時は message をそのまま返す"""
        dto = LlmCommandResultDto(success=True, message="目的地を設定しました。")
        assert build_result_summary(dto) == "目的地を設定しました。"

    def test_failure_includes_message_and_remediation(self):
        """失敗時は「失敗。{message} 対処: {remediation}」形式"""
        dto = LlmCommandResultDto(
            success=False,
            message="経路が見つかりません。",
            remediation="接続先スポットを確認してください。",
        )
        assert build_result_summary(dto) == "失敗。経路が見つかりません。 対処: 接続先スポットを確認してください。"

    def test_failure_without_remediation_returns_only_message(self):
        """失敗時でも remediation が None なら「失敗。」＋ message のみ"""
        dto = LlmCommandResultDto(
            success=False,
            message="エラーが発生しました。",
            remediation=None,
        )
        assert build_result_summary(dto) == "失敗。エラーが発生しました。"

    def test_dto_not_llm_command_result_dto_raises_type_error(self):
        """dto が LlmCommandResultDto でない場合 TypeError"""
        with pytest.raises(TypeError, match="dto must be LlmCommandResultDto"):
            build_result_summary({"success": True, "message": "ok"})  # type: ignore[arg-type]
