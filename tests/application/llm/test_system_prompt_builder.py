"""DefaultSystemPromptBuilder のテスト（正常・例外）"""

import pytest

from ai_rpg_world.application.llm.contracts.dtos import SystemPromptPlayerInfoDto
from ai_rpg_world.application.llm.services.system_prompt_builder import (
    DefaultSystemPromptBuilder,
    DEFAULT_SYSTEM_PROMPT_TEMPLATE,
)


class TestDefaultSystemPromptBuilder:
    """DefaultSystemPromptBuilder の正常・例外ケース"""

    @pytest.fixture
    def builder(self):
        return DefaultSystemPromptBuilder()

    @pytest.fixture
    def player_info(self):
        return SystemPromptPlayerInfoDto(
            player_name="冒険者",
            role="adventurer",
            race="human",
            element="fire",
            game_description="MMOの世界で冒険するゲームです。",
        )

    def test_build_includes_player_name_and_game_description(self, builder, player_info):
        """プレイヤー名とゲーム説明が含まれる"""
        text = builder.build(player_info)
        assert "冒険者" in text
        assert "MMOの世界で冒険するゲームです。" in text

    def test_build_includes_role_race_element(self, builder, player_info):
        """役職・種族・属性が含まれる"""
        text = builder.build(player_info)
        assert "adventurer" in text
        assert "human" in text
        assert "fire" in text

    def test_build_includes_rules_section(self, builder, player_info):
        """【ルール】セクションが含まれる"""
        text = builder.build(player_info)
        assert "【ルール】" in text
        assert "ツール" in text

    def test_build_empty_game_description_ok(self, builder):
        """game_description が空でも生成される"""
        info = SystemPromptPlayerInfoDto(
            player_name="P",
            role="r",
            race="r",
            element="e",
            game_description="",
        )
        text = builder.build(info)
        assert "P" in text

    def test_build_player_info_not_dto_raises_type_error(self, builder):
        """player_info が SystemPromptPlayerInfoDto でないとき TypeError"""
        with pytest.raises(TypeError, match="player_info must be SystemPromptPlayerInfoDto"):
            builder.build("not a dto")  # type: ignore[arg-type]

    def test_custom_template_is_used(self):
        """カスタムテンプレートを渡すとそれが使われる"""
        custom = "Hello {{player_name}} only."
        builder = DefaultSystemPromptBuilder(template=custom)
        info = SystemPromptPlayerInfoDto(
            player_name="Alice",
            role="r",
            race="r",
            element="e",
            game_description="",
        )
        text = builder.build(info)
        assert "Hello Alice only." in text

    def test_init_template_not_str_raises_type_error(self):
        """template が str でないとき TypeError"""
        with pytest.raises(TypeError, match="template must be str"):
            DefaultSystemPromptBuilder(template=123)  # type: ignore[arg-type]
