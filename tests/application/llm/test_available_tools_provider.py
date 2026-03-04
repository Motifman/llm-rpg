"""DefaultAvailableToolsProvider のテスト（正常・例外）"""

import pytest

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.services.availability_resolvers import (
    NoOpAvailabilityResolver,
    SetDestinationAvailabilityResolver,
)
from ai_rpg_world.application.llm.services.available_tools_provider import (
    DefaultAvailableToolsProvider,
)
from ai_rpg_world.application.llm.services.game_tool_registry import (
    DefaultGameToolRegistry,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_NO_OP,
    TOOL_NAME_SET_DESTINATION,
)
from ai_rpg_world.application.llm.services.tool_definitions import (
    register_default_tools,
)
from ai_rpg_world.application.world.contracts.dtos import (
    AvailableMoveDto,
    PlayerCurrentStateDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def _context_with_moves(total: int):
    moves = [
        AvailableMoveDto(spot_id=2, spot_name="B", road_id=1, road_description="", conditions_met=True, failed_conditions=[])
    ] * max(0, total)
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="P",
        current_spot_id=1,
        current_spot_name="A",
        current_spot_description="",
        x=0, y=0, z=0,
        area_id=None,
        area_name=None,
        current_player_count=0,
        current_player_ids=set(),
        connected_spot_ids=set(),
        connected_spot_names=set(),
        weather_type="clear",
        weather_intensity=0.0,
        current_terrain_type=None,
        visible_objects=[],
        view_distance=5,
        available_moves=moves if total else [],
        total_available_moves=total,
        attention_level=AttentionLevel.FULL,
    )


class TestDefaultAvailableToolsProvider:
    """DefaultAvailableToolsProvider の正常・例外ケース"""

    @pytest.fixture
    def registry(self):
        r = DefaultGameToolRegistry()
        register_default_tools(r)
        return r

    @pytest.fixture
    def provider(self, registry):
        return DefaultAvailableToolsProvider(registry)

    def test_get_available_tools_context_none_returns_no_op_only(self, provider):
        """context が None のときは no_op のみ（set_destination は利用不可）"""
        tools = provider.get_available_tools(None)
        assert isinstance(tools, list)
        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == TOOL_NAME_NO_OP

    def test_get_available_tools_context_with_moves_returns_both(self, provider):
        """context に移動先があるときは no_op と set_destination の両方"""
        ctx = _context_with_moves(1)
        tools = provider.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
        assert TOOL_NAME_NO_OP in names
        assert TOOL_NAME_SET_DESTINATION in names

    def test_tool_format_openai_compatible(self, provider):
        """返却形式が OpenAI の function ツール形式である"""
        tools = provider.get_available_tools(None)
        for t in tools:
            assert "type" in t and t["type"] == "function"
            assert "function" in t
            assert "name" in t["function"]
            assert "description" in t["function"]
            assert "parameters" in t["function"]

    def test_init_registry_not_registry_raises_type_error(self):
        """registry が IGameToolRegistry でないとき TypeError"""
        with pytest.raises(TypeError, match="registry must be IGameToolRegistry"):
            DefaultAvailableToolsProvider(None)  # type: ignore[arg-type]
