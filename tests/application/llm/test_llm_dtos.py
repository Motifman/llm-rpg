"""LLM 向け DTO（SystemPromptPlayerInfoDto, ActionResultEntry, LlmCommandResultDto, ToolDefinitionDto）のテスト（正常・例外）"""

import pytest
from datetime import datetime

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionResultEntry,
    LlmCommandResultDto,
    SystemPromptPlayerInfoDto,
    ToolDefinitionDto,
)


class TestSystemPromptPlayerInfoDto:
    """SystemPromptPlayerInfoDto の正常・例外ケース"""

    def test_create_with_valid_fields(self):
        """全フィールドが str なら正常に生成される"""
        dto = SystemPromptPlayerInfoDto(
            player_name="TestPlayer",
            role="citizen",
            race="human",
            element="neutral",
            game_description="A game.",
        )
        assert dto.player_name == "TestPlayer"
        assert dto.role == "citizen"
        assert dto.race == "human"
        assert dto.element == "neutral"
        assert dto.game_description == "A game."

    def test_game_description_can_be_empty(self):
        """game_description は空文字可"""
        dto = SystemPromptPlayerInfoDto(
            player_name="P",
            role="r",
            race="r",
            element="e",
            game_description="",
        )
        assert dto.game_description == ""

    def test_player_name_not_str_raises_type_error(self):
        """player_name が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="player_name must be str"):
            SystemPromptPlayerInfoDto(
                player_name=123,  # type: ignore[arg-type]
                role="r",
                race="r",
                element="e",
                game_description="",
            )

    def test_role_not_str_raises_type_error(self):
        """role が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="role must be str"):
            SystemPromptPlayerInfoDto(
                player_name="P",
                role=None,  # type: ignore[arg-type]
                race="r",
                element="e",
                game_description="",
            )

    def test_race_not_str_raises_type_error(self):
        """race が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="race must be str"):
            SystemPromptPlayerInfoDto(
                player_name="P",
                role="r",
                race=1,  # type: ignore[arg-type]
                element="e",
                game_description="",
            )

    def test_element_not_str_raises_type_error(self):
        """element が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="element must be str"):
            SystemPromptPlayerInfoDto(
                player_name="P",
                role="r",
                race="r",
                element=[],  # type: ignore[arg-type]
                game_description="",
            )

    def test_game_description_not_str_raises_type_error(self):
        """game_description が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="game_description must be str"):
            SystemPromptPlayerInfoDto(
                player_name="P",
                role="r",
                race="r",
                element="e",
                game_description=0.0,  # type: ignore[arg-type]
            )


class TestActionResultEntry:
    """ActionResultEntry の正常・例外ケース"""

    def test_create_with_valid_fields(self):
        """occurred_at / action_summary / result_summary が正しい型なら正常"""
        now = datetime.now()
        entry = ActionResultEntry(
            occurred_at=now,
            action_summary="move_to を実行",
            result_summary="スポットAに到着しました。",
        )
        assert entry.occurred_at == now
        assert entry.action_summary == "move_to を実行"
        assert entry.result_summary == "スポットAに到着しました。"

    def test_occurred_at_not_datetime_raises_type_error(self):
        """occurred_at が datetime でない場合 TypeError"""
        with pytest.raises(TypeError, match="occurred_at must be datetime"):
            ActionResultEntry(
                occurred_at="2025-01-01",  # type: ignore[arg-type]
                action_summary="a",
                result_summary="b",
            )

    def test_action_summary_not_str_raises_type_error(self):
        """action_summary が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="action_summary must be str"):
            ActionResultEntry(
                occurred_at=datetime.now(),
                action_summary=123,  # type: ignore[arg-type]
                result_summary="b",
            )

    def test_result_summary_not_str_raises_type_error(self):
        """result_summary が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="result_summary must be str"):
            ActionResultEntry(
                occurred_at=datetime.now(),
                action_summary="a",
                result_summary=None,  # type: ignore[arg-type]
            )


class TestLlmCommandResultDto:
    """LlmCommandResultDto の正常・例外ケース"""

    def test_create_success_minimal(self):
        """成功時は message のみで error_code / remediation は None"""
        dto = LlmCommandResultDto(success=True, message="完了しました。")
        assert dto.success is True
        assert dto.message == "完了しました。"
        assert dto.error_code is None
        assert dto.remediation is None

    def test_create_failure_with_remediation(self):
        """失敗時は message / error_code / remediation を指定できる"""
        dto = LlmCommandResultDto(
            success=False,
            message="移動に失敗しました。",
            error_code="MOVEMENT_INVALID",
            remediation="接続先を確認してください。",
        )
        assert dto.success is False
        assert dto.message == "移動に失敗しました。"
        assert dto.error_code == "MOVEMENT_INVALID"
        assert dto.remediation == "接続先を確認してください。"

    def test_success_not_bool_raises_type_error(self):
        """success が bool でない場合 TypeError"""
        with pytest.raises(TypeError, match="success must be bool"):
            LlmCommandResultDto(success=1, message="ok")  # type: ignore[arg-type]

    def test_message_not_str_raises_type_error(self):
        """message が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="message must be str"):
            LlmCommandResultDto(success=True, message=None)  # type: ignore[arg-type]

    def test_error_code_not_str_raises_type_error(self):
        """error_code が str でない場合（None 以外）TypeError"""
        with pytest.raises(TypeError, match="error_code must be str or None"):
            LlmCommandResultDto(
                success=False,
                message="err",
                error_code=123,  # type: ignore[arg-type]
            )

    def test_remediation_not_str_raises_type_error(self):
        """remediation が str でない場合（None 以外）TypeError"""
        with pytest.raises(TypeError, match="remediation must be str or None"):
            LlmCommandResultDto(
                success=False,
                message="err",
                remediation=[],  # type: ignore[arg-type]
            )


class TestToolDefinitionDto:
    """ToolDefinitionDto の正常・例外ケース"""

    def test_create_with_valid_fields(self):
        """name / description / parameters が正しい型なら正常"""
        dto = ToolDefinitionDto(
            name="world_no_op",
            description="何もしない。",
            parameters={"type": "object", "properties": {}, "required": []},
        )
        assert dto.name == "world_no_op"
        assert dto.description == "何もしない。"
        assert dto.parameters == {"type": "object", "properties": {}, "required": []}

    def test_name_not_str_raises_type_error(self):
        """name が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="name must be str"):
            ToolDefinitionDto(
                name=123,  # type: ignore[arg-type]
                description="d",
                parameters={},
            )

    def test_description_not_str_raises_type_error(self):
        """description が str でない場合 TypeError"""
        with pytest.raises(TypeError, match="description must be str"):
            ToolDefinitionDto(
                name="n",
                description=None,  # type: ignore[arg-type]
                parameters={},
            )

    def test_parameters_not_dict_raises_type_error(self):
        """parameters が dict でない場合 TypeError"""
        with pytest.raises(TypeError, match="parameters must be dict"):
            ToolDefinitionDto(
                name="n",
                description="d",
                parameters="{}",  # type: ignore[arg-type]
            )
