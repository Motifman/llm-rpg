"""主観入力 schema の付与対象を確認するテスト。"""

from ai_rpg_world.application.llm.contracts.dtos import EMOTION_HINT_VALUES, ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.available_tools_provider import (
    DefaultAvailableToolsProvider,
)
from ai_rpg_world.application.llm.services.game_tool_registry import DefaultGameToolRegistry
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMORY_QUERY,
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_WORKING_MEMORY_APPEND,
)


class _AlwaysAvailableResolver(IAvailabilityResolver):
    def is_available(self, context):
        return True


def _tool_by_name(tools, name):
    for tool in tools:
        if tool["function"]["name"] == name:
            return tool
    raise AssertionError(f"tool not found: {name}")


def test_world_action_tool_schema_requires_subjective_fields() -> None:
    registry = DefaultGameToolRegistry()
    registry.register(
        ToolDefinitionDto(
            name=TOOL_NAME_MOVE_TO_DESTINATION,
            description="move",
            parameters={
                "type": "object",
                "properties": {"destination_label": {"type": "string"}},
                "required": ["destination_label"],
            },
        ),
        _AlwaysAvailableResolver(),
    )

    tools = DefaultAvailableToolsProvider(registry).get_available_tools(None)
    tool = _tool_by_name(tools, TOOL_NAME_MOVE_TO_DESTINATION)
    params = tool["function"]["parameters"]
    props = params["properties"]
    required = params["required"]

    for field in (
        "inner_thought",
        "intention",
        "expected_result",
        "attention",
        "emotion_hint",
    ):
        assert field in props
        assert field in required
    assert props["emotion_hint"]["enum"] == list(EMOTION_HINT_VALUES)


def test_meta_tools_do_not_get_subjective_fields() -> None:
    registry = DefaultGameToolRegistry()
    for name in (TOOL_NAME_MEMORY_QUERY, TOOL_NAME_WORKING_MEMORY_APPEND):
        registry.register(
            ToolDefinitionDto(
                name=name,
                description="meta",
                parameters={
                    "type": "object",
                    "properties": {"expr": {"type": "string"}},
                    "required": ["expr"],
                },
            ),
            _AlwaysAvailableResolver(),
        )

    tools = DefaultAvailableToolsProvider(registry).get_available_tools(None)

    for name in (TOOL_NAME_MEMORY_QUERY, TOOL_NAME_WORKING_MEMORY_APPEND):
        tool = _tool_by_name(tools, name)
        props = tool["function"]["parameters"]["properties"]
        required = tool["function"]["parameters"]["required"]
        for field in (
            "inner_thought",
            "intention",
            "expected_result",
            "attention",
            "emotion_hint",
        ):
            assert field not in props
            assert field not in required
