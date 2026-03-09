"""DefaultToolArgumentResolver のテスト。"""

import pytest

from ai_rpg_world.application.llm.contracts.dtos import (
    AttentionLevelToolRuntimeTargetDto,
    ChestItemToolRuntimeTargetDto,
    ChestToolRuntimeTargetDto,
    ConversationChoiceToolRuntimeTargetDto,
    DestinationToolRuntimeTargetDto,
    InventoryToolRuntimeTargetDto,
    MonsterToolRuntimeTargetDto,
    NpcToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    ResourceToolRuntimeTargetDto,
    SkillToolRuntimeTargetDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services.tool_argument_resolver import (
    DefaultToolArgumentResolver,
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_CHANGE_ATTENTION,
    TOOL_NAME_CHEST_STORE,
    TOOL_NAME_CHEST_TAKE,
    TOOL_NAME_COMBAT_USE_SKILL,
    TOOL_NAME_CONVERSATION_ADVANCE,
    TOOL_NAME_DESTROY_PLACEABLE,
    TOOL_NAME_HARVEST_START,
    TOOL_NAME_INSPECT_ITEM,
    TOOL_NAME_INSPECT_TARGET,
    TOOL_NAME_INTERACT_WORLD_OBJECT,
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_PLACE_OBJECT,
    TOOL_NAME_SAY,
    TOOL_NAME_WHISPER,
)
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel


def _make_context() -> ToolRuntimeContextDto:
    return ToolRuntimeContextDto(
        targets={
            "S1": DestinationToolRuntimeTargetDto(
                label="S1",
                kind="destination",
                display_name="港町",
                spot_id=2,
                destination_type="spot",
            ),
            "P1": PlayerToolRuntimeTargetDto(
                label="P1",
                kind="player",
                display_name="Bob",
                player_id=2,
                world_object_id=100,
            ),
            "N1": NpcToolRuntimeTargetDto(
                label="N1",
                kind="npc",
                display_name="老人",
                world_object_id=200,
            ),
            "O2": ChestToolRuntimeTargetDto(
                label="O2",
                kind="chest",
                display_name="宝箱",
                world_object_id=210,
            ),
            "O1": ResourceToolRuntimeTargetDto(
                label="O1",
                kind="resource",
                display_name="薬草",
                world_object_id=300,
            ),
            "I1": InventoryToolRuntimeTargetDto(
                label="I1",
                kind="inventory_item",
                display_name="木箱",
                item_instance_id=400,
                inventory_slot_id=2,
                is_placeable=True,
                available_interactions=("place_object",),
            ),
            "C1": ChestItemToolRuntimeTargetDto(
                label="C1",
                kind="chest_item",
                display_name="ポーション",
                item_instance_id=500,
                chest_world_object_id=210,
            ),
            "R1": ConversationChoiceToolRuntimeTargetDto(
                label="R1",
                kind="conversation_choice",
                display_name="はい",
                world_object_id=200,
                conversation_choice_index=0,
            ),
            "K1": SkillToolRuntimeTargetDto(
                label="K1",
                kind="skill",
                display_name="火球",
                skill_loadout_id=10,
                skill_slot_index=1,
            ),
            "A1": AttentionLevelToolRuntimeTargetDto(
                label="A1",
                kind="attention_level",
                display_name="フル",
                attention_level_value="FULL",
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

    def test_resolve_say_sets_say_channel(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_SAY,
            {"content": "やあ"},
            _make_context(),
        )

        assert result["content"] == "やあ"
        assert result["channel"] == SpeechChannel.SAY

    def test_resolve_interact_target_label(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_INTERACT_WORLD_OBJECT,
            {"target_label": "N1"},
            _make_context(),
        )

        assert result["target_world_object_id"] == 200
        assert result["target_display_name"] == "老人"

    def test_resolve_harvest_target_label(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_HARVEST_START,
            {"target_label": "O1"},
            _make_context(),
        )

        assert result["target_world_object_id"] == 300
        assert result["target_display_name"] == "薬草"

    def test_resolve_change_attention_level_label(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_CHANGE_ATTENTION,
            {"level_label": "A1"},
            _make_context(),
        )

        assert result["attention_level_value"] == "FULL"

    def test_resolve_conversation_advance_labels(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_CONVERSATION_ADVANCE,
            {"target_label": "N1", "choice_label": "R1"},
            _make_context(),
        )

        assert result["npc_world_object_id"] == 200
        assert result["choice_index"] == 0

    def test_resolve_place_object_inventory_label(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_PLACE_OBJECT,
            {"inventory_item_label": "I1"},
            _make_context(),
        )

        assert result["inventory_slot_id"] == 2

    def test_resolve_inspect_item_inventory_label(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_INSPECT_ITEM,
            {"inventory_item_label": "I1"},
            _make_context(),
        )

        assert result["item_instance_id"] == 400

    def test_resolve_inspect_target_npc_label(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_INSPECT_TARGET,
            {"target_label": "N1"},
            _make_context(),
        )

        assert result["target_world_object_id"] == 200

    def test_resolve_inspect_item_invalid_label_raises(self):
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_INSPECT_ITEM,
                {"inventory_item_label": "X99"},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"

    def test_resolve_inspect_item_empty_label_raises(self):
        """inventory_item_label が空文字のとき INVALID_TARGET_LABEL"""
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_INSPECT_ITEM,
                {"inventory_item_label": ""},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
        assert "指定されていません" in str(exc_info.value)

    def test_resolve_inspect_item_none_label_raises(self):
        """inventory_item_label が None（args に含まれない）のとき INVALID_TARGET_LABEL"""
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_INSPECT_ITEM,
                {},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"

    def test_resolve_inspect_target_invalid_label_raises(self):
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_INSPECT_TARGET,
                {"target_label": "X99"},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"

    def test_resolve_inspect_target_empty_label_raises(self):
        """target_label が空文字のとき INVALID_TARGET_LABEL"""
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_INSPECT_TARGET,
                {"target_label": ""},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"
        assert "指定されていません" in str(exc_info.value)

    def test_resolve_inspect_target_none_label_raises(self):
        """target_label が None（args に含まれない）のとき INVALID_TARGET_LABEL"""
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_INSPECT_TARGET,
                {},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_LABEL"

    def test_resolve_destroy_placeable_returns_empty(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_DESTROY_PLACEABLE,
            {},
            _make_context(),
        )

        assert result == {}

    def test_resolve_chest_store_labels(self):
        resolver = DefaultToolArgumentResolver()

        result = resolver.resolve(
            TOOL_NAME_CHEST_STORE,
            {"target_label": "O2", "inventory_item_label": "I1"},
            _make_context(),
        )

        assert result["item_instance_id"] == 400

    def test_resolve_chest_take_labels(self):
        resolver = DefaultToolArgumentResolver()

        ctx = _make_context()
        result = resolver.resolve(
            TOOL_NAME_CHEST_TAKE,
            {"target_label": "O2", "chest_item_label": "C1"},
            ctx,
        )

        assert result["item_instance_id"] == 500

    def test_resolve_combat_use_skill_with_target(self):
        resolver = DefaultToolArgumentResolver()
        ctx = _make_context()
        ctx.targets["M1"] = MonsterToolRuntimeTargetDto(
            label="M1",
            kind="monster",
            display_name="ゴブリン",
            relative_dx=1,
            relative_dy=-1,
            relative_dz=0,
        )

        result = resolver.resolve(
            TOOL_NAME_COMBAT_USE_SKILL,
            {"skill_label": "K1", "target_label": "M1"},
            ctx,
        )

        assert result["skill_loadout_id"] == 10
        assert result["skill_slot_index"] == 1
        assert result["target_direction"] == "NORTHEAST"
        assert result["auto_aim"] is False

    def test_resolve_whisper_non_player_label_raises(self):
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_WHISPER,
                {"target_label": "N1", "content": "こんにちは"},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_KIND"

    def test_resolve_interact_destination_label_raises(self):
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_INTERACT_WORLD_OBJECT,
                {"target_label": "S1"},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_KIND"

    def test_resolve_harvest_non_resource_label_raises(self):
        resolver = DefaultToolArgumentResolver()

        with pytest.raises(ToolArgumentResolutionException) as exc_info:
            resolver.resolve(
                TOOL_NAME_HARVEST_START,
                {"target_label": "N1"},
                _make_context(),
            )

        assert exc_info.value.error_code == "INVALID_TARGET_KIND"

    def test_resolve_place_object_non_placeable_label_raises(self):
        resolver = DefaultToolArgumentResolver()
        ctx = _make_context()
        ctx.targets["I2"] = InventoryToolRuntimeTargetDto(
            label="I2",
            kind="inventory_item",
            display_name="石",
            item_instance_id=401,
            inventory_slot_id=3,
        )
        with pytest.raises(ToolArgumentResolutionException):
            resolver.resolve(
                TOOL_NAME_PLACE_OBJECT,
                {"inventory_item_label": "I2"},
                ctx,
            )
