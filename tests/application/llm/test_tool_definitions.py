"""tool_definitions（register_default_tools, 定義定数）のテスト"""

import pytest

from ai_rpg_world.application.llm.services.game_tool_registry import (
    DefaultGameToolRegistry,
)
from ai_rpg_world.application.llm.services.tool_definitions import (
    CHANGE_ATTENTION_DEFINITION,
    CHEST_STORE_DEFINITION,
    CHEST_TAKE_DEFINITION,
    COMBAT_USE_SKILL_DEFINITION,
    CONVERSATION_ADVANCE_DEFINITION,
    DESTROY_PLACEABLE_DEFINITION,
    HARVEST_START_DEFINITION,
    INSPECT_ITEM_DEFINITION,
    INSPECT_TARGET_DEFINITION,
    INTERACT_WORLD_OBJECT_DEFINITION,
    MOVE_TO_DESTINATION_DEFINITION,
    NO_OP_DEFINITION,
    PLACE_OBJECT_DEFINITION,
    SAY_DEFINITION,
    WHISPER_DEFINITION,
    register_default_tools,
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
    TOOL_NAME_NO_OP,
    TOOL_NAME_PLACE_OBJECT,
    TOOL_NAME_SAY,
    TOOL_NAME_WHISPER,
)


class TestToolDefinitions:
    """ツール定義定数の内容"""

    def test_no_op_definition_has_expected_name_and_empty_params(self):
        """NO_OP_DEFINITION は name=world_no_op, parameters は空オブジェクト"""
        assert NO_OP_DEFINITION.name == TOOL_NAME_NO_OP
        assert NO_OP_DEFINITION.parameters.get("type") == "object"
        assert NO_OP_DEFINITION.parameters.get("required") == []

    def test_move_to_destination_definition_has_expected_name_and_params(self):
        """MOVE_TO_DESTINATION_DEFINITION は destination_label を持つ"""
        assert MOVE_TO_DESTINATION_DEFINITION.name == TOOL_NAME_MOVE_TO_DESTINATION
        params = MOVE_TO_DESTINATION_DEFINITION.parameters
        assert "destination_label" in params.get("properties", {})
        assert "destination_label" in params.get("required", [])

    def test_whisper_definition_has_expected_name_and_params(self):
        """WHISPER_DEFINITION は target_label, content を持つ"""
        assert WHISPER_DEFINITION.name == TOOL_NAME_WHISPER
        params = WHISPER_DEFINITION.parameters
        assert "target_label" in params.get("properties", {})
        assert "content" in params.get("properties", {})
        assert "target_label" in params.get("required", [])
        assert "content" in params.get("required", [])

    def test_say_definition_has_expected_name_and_params(self):
        assert SAY_DEFINITION.name == TOOL_NAME_SAY
        params = SAY_DEFINITION.parameters
        assert "content" in params.get("properties", {})
        assert "content" in params.get("required", [])

    def test_interact_definition_has_expected_name_and_params(self):
        assert INTERACT_WORLD_OBJECT_DEFINITION.name == TOOL_NAME_INTERACT_WORLD_OBJECT
        params = INTERACT_WORLD_OBJECT_DEFINITION.parameters
        assert "target_label" in params.get("properties", {})
        assert "target_label" in params.get("required", [])

    def test_harvest_start_definition_has_expected_name_and_params(self):
        assert HARVEST_START_DEFINITION.name == TOOL_NAME_HARVEST_START
        params = HARVEST_START_DEFINITION.parameters
        assert "target_label" in params.get("properties", {})
        assert "target_label" in params.get("required", [])

    def test_change_attention_definition_has_expected_name_and_params(self):
        assert CHANGE_ATTENTION_DEFINITION.name == TOOL_NAME_CHANGE_ATTENTION
        assert "level_label" in CHANGE_ATTENTION_DEFINITION.parameters.get("properties", {})

    def test_conversation_advance_definition_has_expected_name_and_params(self):
        assert CONVERSATION_ADVANCE_DEFINITION.name == TOOL_NAME_CONVERSATION_ADVANCE
        params = CONVERSATION_ADVANCE_DEFINITION.parameters
        assert "target_label" in params.get("properties", {})
        assert "choice_label" in params.get("properties", {})

    def test_place_and_destroy_definition_have_expected_params(self):
        assert PLACE_OBJECT_DEFINITION.name == TOOL_NAME_PLACE_OBJECT
        assert "inventory_item_label" in PLACE_OBJECT_DEFINITION.parameters.get("properties", {})
        assert DESTROY_PLACEABLE_DEFINITION.name == TOOL_NAME_DESTROY_PLACEABLE
        assert DESTROY_PLACEABLE_DEFINITION.parameters.get("required") == []

    def test_chest_definitions_have_expected_params(self):
        assert CHEST_STORE_DEFINITION.name == TOOL_NAME_CHEST_STORE
        assert CHEST_TAKE_DEFINITION.name == TOOL_NAME_CHEST_TAKE
        assert "inventory_item_label" in CHEST_STORE_DEFINITION.parameters.get("properties", {})
        assert "chest_item_label" in CHEST_TAKE_DEFINITION.parameters.get("properties", {})

    def test_combat_use_skill_definition_has_expected_params(self):
        assert COMBAT_USE_SKILL_DEFINITION.name == TOOL_NAME_COMBAT_USE_SKILL
        params = COMBAT_USE_SKILL_DEFINITION.parameters
        assert "skill_label" in params.get("properties", {})
        assert "target_label" in params.get("properties", {})

    def test_inspect_item_definition_has_expected_params(self):
        assert INSPECT_ITEM_DEFINITION.name == TOOL_NAME_INSPECT_ITEM
        params = INSPECT_ITEM_DEFINITION.parameters
        assert "inventory_item_label" in params.get("properties", {})
        assert "inventory_item_label" in params.get("required", [])

    def test_inspect_target_definition_has_expected_params(self):
        assert INSPECT_TARGET_DEFINITION.name == TOOL_NAME_INSPECT_TARGET
        params = INSPECT_TARGET_DEFINITION.parameters
        assert "target_label" in params.get("properties", {})
        assert "target_label" in params.get("required", [])


class TestRegisterDefaultTools:
    """register_default_tools の正常・例外"""

    def test_register_default_tools_adds_no_op_and_move_to_destination(self):
        """登録後は no_op と move_to_destination が取得できる"""
        registry = DefaultGameToolRegistry()
        register_default_tools(registry)
        entries = registry.get_definitions_with_resolvers()
        names = [e[0].name for e in entries]
        assert TOOL_NAME_NO_OP in names
        assert TOOL_NAME_MOVE_TO_DESTINATION in names

    def test_register_default_tools_with_speech_enabled_adds_whisper(self):
        registry = DefaultGameToolRegistry()
        register_default_tools(registry, speech_enabled=True)
        entries = registry.get_definitions_with_resolvers()
        names = [e[0].name for e in entries]
        assert TOOL_NAME_WHISPER in names
        assert TOOL_NAME_SAY in names

    def test_register_default_tools_with_interaction_enabled_adds_interact(self):
        registry = DefaultGameToolRegistry()
        register_default_tools(registry, interaction_enabled=True)
        entries = registry.get_definitions_with_resolvers()
        names = [e[0].name for e in entries]
        assert TOOL_NAME_INTERACT_WORLD_OBJECT in names

    def test_register_default_tools_with_harvest_enabled_adds_harvest_start(self):
        registry = DefaultGameToolRegistry()
        register_default_tools(registry, harvest_enabled=True)
        entries = registry.get_definitions_with_resolvers()
        names = [e[0].name for e in entries]
        assert TOOL_NAME_HARVEST_START in names

    def test_register_default_tools_with_all_extended_flags_adds_tools(self):
        registry = DefaultGameToolRegistry()
        register_default_tools(
            registry,
            attention_enabled=True,
            conversation_enabled=True,
            place_enabled=True,
            chest_enabled=True,
            combat_enabled=True,
        )
        names = [e[0].name for e in registry.get_definitions_with_resolvers()]
        assert TOOL_NAME_CHANGE_ATTENTION in names
        assert TOOL_NAME_CONVERSATION_ADVANCE in names
        assert TOOL_NAME_PLACE_OBJECT in names
        assert TOOL_NAME_DESTROY_PLACEABLE in names
        assert TOOL_NAME_CHEST_STORE in names
        assert TOOL_NAME_CHEST_TAKE in names
        assert TOOL_NAME_COMBAT_USE_SKILL in names

    def test_register_default_tools_with_inspect_item_enabled_adds_inspect_item(self):
        registry = DefaultGameToolRegistry()
        register_default_tools(registry, inspect_item_enabled=True)
        entries = registry.get_definitions_with_resolvers()
        names = [e[0].name for e in entries]
        assert TOOL_NAME_INSPECT_ITEM in names

    def test_register_default_tools_with_inspect_target_enabled_adds_inspect_target(self):
        registry = DefaultGameToolRegistry()
        register_default_tools(registry, inspect_target_enabled=True)
        entries = registry.get_definitions_with_resolvers()
        names = [e[0].name for e in entries]
        assert TOOL_NAME_INSPECT_TARGET in names

    def test_register_default_tools_registry_not_registry_raises_type_error(self):
        """registry が IGameToolRegistry でないとき TypeError"""
        with pytest.raises(TypeError, match="registry must be IGameToolRegistry"):
            register_default_tools(None)  # type: ignore[arg-type]
