from ai_rpg_world.application.llm.contracts.dtos import SystemPromptPlayerInfoDto
from ai_rpg_world.application.llm.services.system_prompt_builder import (
    DefaultSystemPromptBuilder,
)


def test_system_prompt_includes_persona_block_when_provided() -> None:
    info = SystemPromptPlayerInfoDto(
        player_name="門前の少女",
        role="companion",
        race="human",
        element="none",
        game_description="脱出ゲーム世界を探索する。",
        persona_block="【ペルソナ】\n- 一人称: わたし",
    )

    text = DefaultSystemPromptBuilder().build(info)

    assert "門前の少女" in text
    assert "【ペルソナ】" in text
    assert "一人称: わたし" in text


def test_custom_template_can_place_persona_block_flexibly() -> None:
    builder = DefaultSystemPromptBuilder(
        template="NAME={{player_name}}\nPERSONA={{persona_block}}"
    )
    info = SystemPromptPlayerInfoDto(
        player_name="GateGirl",
        role="r",
        race="r",
        element="e",
        game_description="",
        persona_block="quiet",
    )

    assert builder.build(info) == "NAME=GateGirl\nPERSONA=quiet"
