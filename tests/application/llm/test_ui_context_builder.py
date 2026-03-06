"""DefaultLlmUiContextBuilder のテスト。"""

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto
from ai_rpg_world.application.llm.services.ui_context_builder import (
    DefaultLlmUiContextBuilder,
)
from ai_rpg_world.application.world.contracts.dtos import (
    AvailableMoveDto,
    PlayerCurrentStateDto,
    VisibleObjectDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel


def _make_state() -> PlayerCurrentStateDto:
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="Alice",
        current_spot_id=1,
        current_spot_name="広場",
        current_spot_description="人が集まる広場",
        x=0,
        y=0,
        z=0,
        area_id=None,
        area_name=None,
        current_player_count=2,
        current_player_ids={1, 2},
        connected_spot_ids={2},
        connected_spot_names={"港町"},
        weather_type="clear",
        weather_intensity=0.0,
        current_terrain_type="grass",
        visible_objects=[
            VisibleObjectDto(
                object_id=100,
                object_type="PLAYER",
                x=1,
                y=0,
                z=0,
                distance=1,
                display_name="Bob",
                object_kind="player",
                direction_from_player="東",
                player_id_value=2,
                is_self=False,
            ),
            VisibleObjectDto(
                object_id=1,
                object_type="PLAYER",
                x=0,
                y=0,
                z=0,
                distance=0,
                display_name="Alice",
                object_kind="player",
                direction_from_player="ここ",
                player_id_value=1,
                is_self=True,
            ),
            VisibleObjectDto(
                object_id=200,
                object_type="NPC",
                x=0,
                y=1,
                z=0,
                distance=1,
                display_name="老人",
                object_kind="npc",
                direction_from_player="南",
                is_interactable=True,
            ),
        ],
        view_distance=5,
        available_moves=[
            AvailableMoveDto(
                spot_id=2,
                spot_name="港町",
                road_id=1,
                road_description="街道",
                conditions_met=True,
                failed_conditions=[],
            )
        ],
        total_available_moves=1,
        attention_level=AttentionLevel.FULL,
    )


class TestDefaultLlmUiContextBuilder:
    def test_build_adds_visible_target_labels_and_runtime_context(self):
        builder = DefaultLlmUiContextBuilder()
        state = _make_state()

        result = builder.build("現在地: 広場", state)

        assert "視界内の対象ラベル:" in result.current_state_text
        assert "P1: Bob" in result.current_state_text
        assert "N1: 老人" in result.current_state_text
        assert isinstance(result.tool_runtime_context, ToolRuntimeContextDto)
        assert result.tool_runtime_context.targets["P1"].player_id == 2
        assert result.tool_runtime_context.targets["N1"].world_object_id == 200

    def test_build_adds_move_labels(self):
        builder = DefaultLlmUiContextBuilder()
        state = _make_state()

        result = builder.build("現在地: 広場", state)

        assert "移動先ラベル:" in result.current_state_text
        assert "S1: 港町" in result.current_state_text
        assert result.tool_runtime_context.targets["S1"].spot_id == 2
        assert result.tool_runtime_context.targets["S1"].destination_type == "spot"

    def test_build_with_none_state_returns_empty_runtime_context(self):
        builder = DefaultLlmUiContextBuilder()

        result = builder.build("現在地: 未配置", None)

        assert result.current_state_text == "現在地: 未配置"
        assert result.tool_runtime_context.targets == {}
