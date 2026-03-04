"""DefaultGameToolRegistry のテスト（正常・例外）"""

import pytest

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.services.availability_resolvers import (
    NoOpAvailabilityResolver,
)
from ai_rpg_world.application.llm.services.game_tool_registry import (
    DefaultGameToolRegistry,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_NO_OP


class TestDefaultGameToolRegistry:
    """DefaultGameToolRegistry の正常・例外ケース"""

    @pytest.fixture
    def registry(self):
        return DefaultGameToolRegistry()

    def test_register_and_get_definitions_with_resolvers(self, registry):
        """register したツールが get_definitions_with_resolvers で取得できる"""
        definition = ToolDefinitionDto(
            name=TOOL_NAME_NO_OP,
            description="何もしない。",
            parameters={"type": "object", "properties": {}, "required": []},
        )
        resolver = NoOpAvailabilityResolver()
        registry.register(definition, resolver)
        entries = registry.get_definitions_with_resolvers()
        assert len(entries) == 1
        def_got, res_got = entries[0]
        assert def_got.name == TOOL_NAME_NO_OP
        assert res_got is resolver

    def test_register_multiple_returns_all(self, registry):
        """複数登録するとすべて返る"""
        d1 = ToolDefinitionDto("a", "desc a", {})
        d2 = ToolDefinitionDto("b", "desc b", {})
        r = NoOpAvailabilityResolver()
        registry.register(d1, r)
        registry.register(d2, r)
        entries = registry.get_definitions_with_resolvers()
        assert len(entries) == 2
        names = [e[0].name for e in entries]
        assert "a" in names and "b" in names

    def test_register_definition_not_tool_definition_dto_raises_type_error(self, registry):
        """definition が ToolDefinitionDto でないとき TypeError"""
        with pytest.raises(TypeError, match="definition must be ToolDefinitionDto"):
            registry.register(
                {"name": "x", "description": "d", "parameters": {}},  # type: ignore[arg-type]
                NoOpAvailabilityResolver(),
            )

    def test_register_resolver_not_availability_resolver_raises_type_error(self, registry):
        """resolver が IAvailabilityResolver でないとき TypeError"""
        definition = ToolDefinitionDto("x", "d", {})
        with pytest.raises(TypeError, match="resolver must be IAvailabilityResolver"):
            registry.register(definition, None)  # type: ignore[arg-type]
