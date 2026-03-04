"""LLM 向け DTO（SystemPromptPlayerInfoDto, ActionResultEntry）のテスト（正常・例外）"""

import pytest
from datetime import datetime

from ai_rpg_world.application.llm.contracts.dtos import (
    SystemPromptPlayerInfoDto,
    ActionResultEntry,
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
