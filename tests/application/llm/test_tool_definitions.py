"""tool_catalog（register_default_tools, 定義定数）のテスト"""

import pytest

from ai_rpg_world.application.llm.services.game_tool_registry import (
    DefaultGameToolRegistry,
)
from ai_rpg_world.application.llm.services.tool_catalog import (
    register_default_tools,
)
from ai_rpg_world.application.llm.services.tool_catalog.combat import (
    COMBAT_USE_SKILL_DEFINITION,
    SKILL_ACCEPT_PROPOSAL_DEFINITION,
    SKILL_ACTIVATE_AWAKENED_MODE_DEFINITION,
    SKILL_EQUIP_DEFINITION,
    SKILL_REJECT_PROPOSAL_DEFINITION,
)
from ai_rpg_world.application.llm.services.tool_catalog.movement import (
    CANCEL_MOVEMENT_DEFINITION,
    MOVE_TO_DESTINATION_DEFINITION,
    NO_OP_DEFINITION,
)
from ai_rpg_world.application.llm.services.tool_catalog.pursuit import (
    PURSUIT_CANCEL_DEFINITION,
    PURSUIT_START_DEFINITION,
)
from ai_rpg_world.application.llm.services.tool_catalog.speech import (
    SAY_DEFINITION,
    WHISPER_DEFINITION,
)
from ai_rpg_world.application.llm.services.tool_catalog.world import (
    CHANGE_ATTENTION_DEFINITION,
    CHEST_STORE_DEFINITION,
    CHEST_TAKE_DEFINITION,
    CONVERSATION_ADVANCE_DEFINITION,
    DESTROY_PLACEABLE_DEFINITION,
    HARVEST_CANCEL_DEFINITION,
    HARVEST_START_DEFINITION,
    INSPECT_ITEM_DEFINITION,
    INSPECT_TARGET_DEFINITION,
    INTERACT_WORLD_OBJECT_DEFINITION,
    PLACE_OBJECT_DEFINITION,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_CANCEL_MOVEMENT,
    TOOL_NAME_CHANGE_ATTENTION,
    TOOL_NAME_CHEST_STORE,
    TOOL_NAME_CHEST_TAKE,
    TOOL_NAME_COMBAT_USE_SKILL,
    TOOL_NAME_CONVERSATION_ADVANCE,
    TOOL_NAME_DESTROY_PLACEABLE,
    TOOL_NAME_HARVEST_CANCEL,
    TOOL_NAME_HARVEST_START,
    TOOL_NAME_INSPECT_ITEM,
    TOOL_NAME_INSPECT_TARGET,
    TOOL_NAME_INTERACT_WORLD_OBJECT,
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_NO_OP,
    TOOL_NAME_PLACE_OBJECT,
    TOOL_NAME_PURSUIT_CANCEL,
    TOOL_NAME_PURSUIT_START,
    TOOL_NAME_SAY,
    TOOL_NAME_SKILL_ACCEPT_PROPOSAL,
    TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE,
    TOOL_NAME_SKILL_EQUIP,
    TOOL_NAME_SKILL_REJECT_PROPOSAL,
    TOOL_NAME_WHISPER,
    TOOL_NAME_SNS_ENTER,
    TOOL_NAME_SNS_CREATE_REPLY,
    TOOL_NAME_SNS_LIKE_POST,
    TOOL_NAME_SNS_FOLLOW,
    TOOL_NAME_SNS_MARK_NOTIFICATION_READ,
    TOOL_NAME_SNS_LOGOUT,
    TOOL_NAME_SNS_VIEW_CURRENT_PAGE,
    TOOL_NAME_TRADE_ENTER,
    TOOL_NAME_TRADE_EXIT,
    TOOL_NAME_TRADE_OFFER,
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

    def test_harvest_cancel_definition_has_expected_name_and_params(self):
        assert HARVEST_CANCEL_DEFINITION.name == TOOL_NAME_HARVEST_CANCEL
        params = HARVEST_CANCEL_DEFINITION.parameters
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

    def test_skill_management_definitions_have_label_params(self):
        assert SKILL_EQUIP_DEFINITION.name == TOOL_NAME_SKILL_EQUIP
        assert "skill_label" in SKILL_EQUIP_DEFINITION.parameters.get("properties", {})
        assert "slot_label" in SKILL_EQUIP_DEFINITION.parameters.get("properties", {})
        assert SKILL_ACCEPT_PROPOSAL_DEFINITION.name == TOOL_NAME_SKILL_ACCEPT_PROPOSAL
        assert "proposal_label" in SKILL_ACCEPT_PROPOSAL_DEFINITION.parameters.get("properties", {})
        assert SKILL_REJECT_PROPOSAL_DEFINITION.name == TOOL_NAME_SKILL_REJECT_PROPOSAL
        assert "proposal_label" in SKILL_REJECT_PROPOSAL_DEFINITION.parameters.get("properties", {})
        assert SKILL_ACTIVATE_AWAKENED_MODE_DEFINITION.name == TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE
        assert "awakened_action_label" in SKILL_ACTIVATE_AWAKENED_MODE_DEFINITION.parameters.get("properties", {})

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

    def test_pursuit_definitions_have_expected_params(self):
        assert PURSUIT_START_DEFINITION.name == TOOL_NAME_PURSUIT_START
        assert "target_label" in PURSUIT_START_DEFINITION.parameters.get("properties", {})
        assert "target_label" in PURSUIT_START_DEFINITION.parameters.get("required", [])
        assert PURSUIT_CANCEL_DEFINITION.name == TOOL_NAME_PURSUIT_CANCEL
        assert PURSUIT_CANCEL_DEFINITION.parameters.get("required") == []

    def test_cancel_movement_definition_has_expected_name_and_empty_params(self):
        """CANCEL_MOVEMENT_DEFINITION は name=move_cancel, parameters は空"""
        assert CANCEL_MOVEMENT_DEFINITION.name == TOOL_NAME_CANCEL_MOVEMENT
        assert CANCEL_MOVEMENT_DEFINITION.parameters.get("required") == []


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

    def test_register_default_tools_adds_cancel_movement(self):
        """登録後は cancel_movement が取得できる"""
        registry = DefaultGameToolRegistry()
        register_default_tools(registry)
        names = [e[0].name for e in registry.get_definitions_with_resolvers()]
        assert TOOL_NAME_CANCEL_MOVEMENT in names

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

    def test_register_default_tools_with_harvest_enabled_adds_harvest_tools(self):
        registry = DefaultGameToolRegistry()
        register_default_tools(registry, harvest_enabled=True)
        entries = registry.get_definitions_with_resolvers()
        names = [e[0].name for e in entries]
        assert TOOL_NAME_HARVEST_START in names
        assert TOOL_NAME_HARVEST_CANCEL in names

    def test_register_default_tools_with_pursuit_enabled_adds_pursuit_tools(self):
        registry = DefaultGameToolRegistry()
        register_default_tools(registry, pursuit_enabled=True)
        names = [e[0].name for e in registry.get_definitions_with_resolvers()]
        assert TOOL_NAME_PURSUIT_START in names
        assert TOOL_NAME_PURSUIT_CANCEL in names

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
        assert TOOL_NAME_SKILL_EQUIP in names
        assert TOOL_NAME_SKILL_ACCEPT_PROPOSAL in names
        assert TOOL_NAME_SKILL_REJECT_PROPOSAL in names
        assert TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE in names

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

    def test_register_default_tools_trade_only_registers_trade_family(self):
        """trade_enabled のみで取引カタログ（入退場・4 ミューテーション）が登録される"""
        registry = DefaultGameToolRegistry()
        register_default_tools(registry, trade_enabled=True)
        names = [e[0].name for e in registry.get_definitions_with_resolvers()]
        assert TOOL_NAME_TRADE_ENTER in names
        assert TOOL_NAME_TRADE_EXIT in names
        assert TOOL_NAME_TRADE_OFFER in names

    def test_register_default_tools_trade_virtual_pages_adds_nav_tools(self):
        """trade_enabled かつ trade_virtual_pages_enabled で仮想取引所ナビツールが追加される"""
        from ai_rpg_world.application.llm.tool_constants import (
            TOOL_NAME_TRADE_OPEN_PAGE,
            TOOL_NAME_TRADE_VIEW_CURRENT_PAGE,
        )

        registry = DefaultGameToolRegistry()
        register_default_tools(
            registry, trade_enabled=True, trade_virtual_pages_enabled=True
        )
        names = [e[0].name for e in registry.get_definitions_with_resolvers()]
        assert TOOL_NAME_TRADE_VIEW_CURRENT_PAGE in names
        assert TOOL_NAME_TRADE_OPEN_PAGE in names

    def test_register_default_tools_trade_with_sns_registers_both(self):
        """trade_enabled かつ sns_enabled で SNS と取引の両カタログが登録される"""
        registry = DefaultGameToolRegistry()
        register_default_tools(registry, trade_enabled=True, sns_enabled=True)
        names = [e[0].name for e in registry.get_definitions_with_resolvers()]
        assert TOOL_NAME_SNS_ENTER in names
        assert TOOL_NAME_TRADE_OFFER in names

    def test_register_default_tools_sns_enabled_registers_sns_enter(self):
        """sns_enabled で sns_enter が登録される"""
        registry = DefaultGameToolRegistry()
        register_default_tools(registry, sns_enabled=True)
        names = [e[0].name for e in registry.get_definitions_with_resolvers()]
        assert TOOL_NAME_SNS_ENTER in names
        assert TOOL_NAME_SNS_LOGOUT in names

    def test_register_default_tools_sns_definitions_use_ref_arguments(self):
        """仮想画面 SNS の書き込み系ツールは raw ID ではなく ref を表に出す"""
        registry = DefaultGameToolRegistry()
        register_default_tools(registry, sns_enabled=True)
        defs = {
            entry[0].name: entry[0] for entry in registry.get_definitions_with_resolvers()
        }

        create_reply = defs[TOOL_NAME_SNS_CREATE_REPLY].parameters
        assert "parent_post_ref" in create_reply["properties"]
        assert "parent_reply_ref" in create_reply["properties"]
        assert "parent_post_id" not in create_reply["properties"]
        assert "parent_reply_id" not in create_reply["properties"]

        like_post = defs[TOOL_NAME_SNS_LIKE_POST].parameters
        assert "post_ref" in like_post["properties"]
        assert "post_id" not in like_post["properties"]

        follow = defs[TOOL_NAME_SNS_FOLLOW].parameters
        assert "target_user_ref" in follow["properties"]
        assert "target_user_id" not in follow["properties"]

        mark_notification = defs[TOOL_NAME_SNS_MARK_NOTIFICATION_READ].parameters
        assert "notification_ref" in mark_notification["properties"]
        assert "notification_id" not in mark_notification["properties"]

    def test_register_default_tools_sns_virtual_pages_adds_navigation_tools(self):
        """sns_enabled かつ sns_virtual_pages_enabled で仮想画面ナビツールが追加される"""
        registry = DefaultGameToolRegistry()
        register_default_tools(
            registry, sns_enabled=True, sns_virtual_pages_enabled=True
        )
        names = [e[0].name for e in registry.get_definitions_with_resolvers()]
        assert TOOL_NAME_SNS_VIEW_CURRENT_PAGE in names

    def test_register_default_tools_virtual_pages_without_sns_does_not_add(self):
        """sns_enabled が False なら sns_virtual_pages_enabled だけではナビを足さない"""
        registry = DefaultGameToolRegistry()
        register_default_tools(registry, sns_virtual_pages_enabled=True)
        names = [e[0].name for e in registry.get_definitions_with_resolvers()]
        assert TOOL_NAME_SNS_VIEW_CURRENT_PAGE not in names
