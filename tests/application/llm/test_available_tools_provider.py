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
    TOOL_NAME_CHANGE_ATTENTION,
    TOOL_NAME_CHEST_STORE,
    TOOL_NAME_COMBAT_USE_SKILL,
    TOOL_NAME_CONVERSATION_ADVANCE,
    TOOL_NAME_DESTROY_PLACEABLE,
    TOOL_NAME_HARVEST_START,
    TOOL_NAME_INTERACT_WORLD_OBJECT,
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_NO_OP,
    TOOL_NAME_PLACE_OBJECT,
    TOOL_NAME_SAY,
)
from ai_rpg_world.application.llm.services.tool_definitions import (
    register_default_tools,
)
from ai_rpg_world.application.world.contracts.dtos import (
    ActiveConversationDto,
    AvailableMoveDto,
    AttentionLevelOptionDto,
    ChestItemDto,
    ConversationChoiceDto,
    InventoryItemDto,
    PlayerCurrentStateDto,
    UsableSkillDto,
    VisibleObjectDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def _context_with_moves(total: int, *, is_busy: bool = False, visible_objects=None):
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
        visible_objects=visible_objects or [],
        view_distance=5,
        available_moves=moves if total else [],
        total_available_moves=total,
        attention_level=AttentionLevel.FULL,
        is_busy=is_busy,
    )


class TestDefaultAvailableToolsProvider:
    """DefaultAvailableToolsProvider の正常・例外ケース"""

    @pytest.fixture
    def registry(self):
        r = DefaultGameToolRegistry()
        register_default_tools(
            r,
            speech_enabled=True,
            interaction_enabled=True,
            harvest_enabled=True,
            attention_enabled=True,
            conversation_enabled=True,
            place_enabled=True,
            chest_enabled=True,
            combat_enabled=True,
        )
        return r

    @pytest.fixture
    def provider(self, registry):
        return DefaultAvailableToolsProvider(registry)

    def test_get_available_tools_context_none_returns_no_op_only(self, provider):
        """context が None のときは no_op のみ（move_to_destination は利用不可）"""
        tools = provider.get_available_tools(None)
        assert isinstance(tools, list)
        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == TOOL_NAME_NO_OP

    def test_get_available_tools_context_with_moves_returns_both(self, provider):
        """context に移動先があるときは no_op と move_to_destination の両方"""
        ctx = _context_with_moves(1)
        tools = provider.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
        assert TOOL_NAME_NO_OP in names
        assert TOOL_NAME_MOVE_TO_DESTINATION in names
        assert TOOL_NAME_SAY in names

    def test_get_available_tools_when_busy_hides_move_tool(self, provider):
        ctx = _context_with_moves(1, is_busy=True)
        tools = provider.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
        assert TOOL_NAME_NO_OP in names
        assert TOOL_NAME_MOVE_TO_DESTINATION not in names

    def test_get_available_tools_with_interaction_targets_adds_interact_and_harvest(self, provider):
        visible_objects = [
            VisibleObjectDto(
                object_id=10,
                object_type="NPC",
                x=1,
                y=0,
                z=0,
                distance=1,
                display_name="老人",
                object_kind="npc",
                available_interactions=["interact"],
            ),
            VisibleObjectDto(
                object_id=11,
                object_type="RESOURCE",
                x=0,
                y=1,
                z=0,
                distance=1,
                display_name="薬草",
                object_kind="resource",
                available_interactions=["harvest"],
            ),
        ]
        ctx = _context_with_moves(0, visible_objects=visible_objects)
        tools = provider.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
        assert TOOL_NAME_INTERACT_WORLD_OBJECT in names
        assert TOOL_NAME_HARVEST_START in names

    def test_get_available_tools_with_extended_context_adds_extended_tools(self, provider):
        visible_objects = [
            VisibleObjectDto(
                object_id=10,
                object_type="CHEST",
                x=1,
                y=0,
                z=0,
                distance=1,
                display_name="宝箱",
                object_kind="chest",
                available_interactions=["interact", "store_in_chest", "take_from_chest"],
            ),
        ]
        ctx = _context_with_moves(
            0,
            visible_objects=visible_objects,
        )
        ctx.inventory_items = [InventoryItemDto(2, 400, "木箱", 1, is_placeable=True)]
        ctx.chest_items = [ChestItemDto(10, "宝箱", 500, "ポーション", 1)]
        ctx.active_conversation = ActiveConversationDto(
            npc_world_object_id=20,
            npc_display_name="老人",
            node_text="どうする？",
            choices=[ConversationChoiceDto(display_text="はい", choice_index=0)],
            is_terminal=False,
        )
        ctx.usable_skills = [UsableSkillDto(10, 1, 100, "火球")]
        ctx.attention_level_options = [
            AttentionLevelOptionDto("FULL", "フル", "すべて受け取る"),
        ]
        ctx.can_destroy_placeable = True
        tools = provider.get_available_tools(ctx)
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]
        assert TOOL_NAME_CHANGE_ATTENTION in names
        assert TOOL_NAME_CONVERSATION_ADVANCE in names
        assert TOOL_NAME_PLACE_OBJECT in names
        assert TOOL_NAME_DESTROY_PLACEABLE in names
        assert TOOL_NAME_CHEST_STORE in names
        assert TOOL_NAME_COMBAT_USE_SKILL in names

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
