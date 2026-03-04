"""tool_definitions（register_default_tools, 定義定数）のテスト"""

import pytest

from ai_rpg_world.application.llm.services.game_tool_registry import (
    DefaultGameToolRegistry,
)
from ai_rpg_world.application.llm.services.tool_definitions import (
    MOVE_TO_DESTINATION_DEFINITION,
    NO_OP_DEFINITION,
    register_default_tools,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_NO_OP,
)


class TestToolDefinitions:
    """ツール定義定数の内容"""

    def test_no_op_definition_has_expected_name_and_empty_params(self):
        """NO_OP_DEFINITION は name=world_no_op, parameters は空オブジェクト"""
        assert NO_OP_DEFINITION.name == TOOL_NAME_NO_OP
        assert NO_OP_DEFINITION.parameters.get("type") == "object"
        assert NO_OP_DEFINITION.parameters.get("required") == []

    def test_move_to_destination_definition_has_expected_name_and_params(self):
        """MOVE_TO_DESTINATION_DEFINITION は destination_type, target_spot_id 等を持つ"""
        assert MOVE_TO_DESTINATION_DEFINITION.name == TOOL_NAME_MOVE_TO_DESTINATION
        params = MOVE_TO_DESTINATION_DEFINITION.parameters
        assert "destination_type" in params.get("properties", {})
        assert "target_spot_id" in params.get("properties", {})
        assert "target_location_area_id" in params.get("properties", {})
        assert "destination_type" in params.get("required", [])
        assert "target_spot_id" in params.get("required", [])


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

    def test_register_default_tools_registry_not_registry_raises_type_error(self):
        """registry が IGameToolRegistry でないとき TypeError"""
        with pytest.raises(TypeError, match="registry must be IGameToolRegistry"):
            register_default_tools(None)  # type: ignore[arg-type]
