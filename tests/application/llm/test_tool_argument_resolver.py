"""DefaultToolArgumentResolver のテスト。"""

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    ToolRuntimeContextDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services.tool_argument_resolver import (
    DefaultToolArgumentResolver,
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_WHISPER,
)
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel


def _make_context() -> ToolRuntimeContextDto:
    return ToolRuntimeContextDto(
        targets={
            "S1": ToolRuntimeTargetDto(
                label="S1",
                kind="destination",
                display_name="港町",
                spot_id=2,
                destination_type="spot",
            ),
            "P1": ToolRuntimeTargetDto(
                label="P1",
                kind="player",
                display_name="Bob",
                player_id=2,
                world_object_id=100,
            ),
            "N1": ToolRuntimeTargetDto(
                label="N1",
                kind="npc",
                display_name="老人",
                world_object_id=200,
            ),
        }
    )


class TestDefaultToolArgumentResolver:
    def test_resolve_move_destination_label(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_MOVE_TO_DESTINATION,
            {"destination_label": "S1"},
            _make_context(),
        )

        assert result == {
            "destination_type": "spot",
            "target_spot_id": 2,
            "target_location_area_id": None,
        }

    def test_resolve_whisper_target_label(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_WHISPER,
            {"target_label": "P1", "content": "こんにちは"},
            _make_context(),
        )

        assert result["target_player_id"] == 2
        assert result["content"] == "こんにちは"
        assert result["channel"] == SpeechChannel.WHISPER

    def test_resolve_move_unknown_label_raises(self):
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_MOVE_TO_DESTINATION,
                {"destination_label": "S9"},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_DESTINATION_LABEL"

    def test_resolve_whisper_non_player_label_raises(self):
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_WHISPER,
                {"target_label": "N1", "content": "こんにちは"},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_KIND"
