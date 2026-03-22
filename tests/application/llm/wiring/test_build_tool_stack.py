"""_build_tool_stack のテスト（正常・境界・統合）"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.services.available_tools_provider import (
    DefaultAvailableToolsProvider,
)
from ai_rpg_world.application.llm.services.game_tool_registry import (
    DefaultGameToolRegistry,
)
from ai_rpg_world.application.llm.services.memory_query_executor import (
    MemoryQueryExecutor,
)
from ai_rpg_world.application.llm.services.subagent_runner import SubagentRunner
from ai_rpg_world.application.llm.services.tool_argument_resolver import (
    DefaultToolArgumentResolver,
)
from ai_rpg_world.application.llm.services.tool_command_mapper import (
    ToolCommandMapper,
)
from ai_rpg_world.application.llm.wiring import (
    _build_tool_stack,
    _ToolStackResult,
)
from ai_rpg_world.application.world.services.movement_service import (
    MovementApplicationService,
)
from ai_rpg_world.domain.player.repository.player_profile_repository import (
    PlayerProfileRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)


def _minimal_tool_stack_deps():
    """_build_tool_stack に渡す最小限の依存を返す。"""
    from ai_rpg_world.application.llm.services.in_memory_todo_store import (
        InMemoryTodoStore,
    )
    from ai_rpg_world.application.llm.services.in_memory_working_memory_store import (
        InMemoryWorkingMemoryStore,
    )

    movement = MagicMock(spec=MovementApplicationService)
    movement.move_to_destination = MagicMock()
    movement.cancel_movement = MagicMock()
    return {
        "game_tool_registry": DefaultGameToolRegistry(),
        "memory_query_executor": MagicMock(spec=MemoryQueryExecutor),
        "subagent_runner": MagicMock(spec=SubagentRunner),
        "working_memory_store": InMemoryWorkingMemoryStore(),
        "todo_store": InMemoryTodoStore(),
        "movement_service": movement,
        "pursuit_command_service": None,
        "speech_service": None,
        "interaction_service": None,
        "harvest_service": None,
        "attention_service": None,
        "conversation_service": None,
        "place_object_service": None,
        "drop_item_service": None,
        "chest_service": None,
        "skill_tool_service": None,
        "quest_command_service": None,
        "guild_command_service": None,
        "shop_command_service": None,
        "trade_command_service": None,
        "post_service": None,
        "reply_service": None,
        "user_command_service": None,
        "notification_command_service": None,
        "sns_mode_session": None,
        "sns_page_session": None,
        "post_query_service": None,
        "sns_page_query_service": None,
        "reply_query_service": None,
        "notification_query_service": None,
        "item_repository": None,
        "monster_repository": None,
        "physical_map_repository": MagicMock(spec=PhysicalMapRepository),
        "player_status_repository": MagicMock(spec=PlayerStatusRepository),
        "monster_template_repository": None,
        "spot_repository": None,
        "item_spec_repository": None,
        "player_profile_repository": MagicMock(spec=PlayerProfileRepository),
    }


class TestBuildToolStackReturnType:
    """_build_tool_stack の戻り値（正常）"""

    def test_returns_tool_stack_result(self):
        """返り値は _ToolStackResult である"""
        deps = _minimal_tool_stack_deps()
        result = _build_tool_stack(**deps)
        assert isinstance(result, _ToolStackResult)

    def test_result_has_expected_attributes(self):
        """返り値は available_tools_provider, tool_command_mapper, tool_argument_resolver を持つ"""
        deps = _minimal_tool_stack_deps()
        result = _build_tool_stack(**deps)
        assert hasattr(result, "available_tools_provider")
        assert hasattr(result, "tool_command_mapper")
        assert hasattr(result, "tool_argument_resolver")
        assert isinstance(result.available_tools_provider, DefaultAvailableToolsProvider)
        assert isinstance(result.tool_command_mapper, ToolCommandMapper)
        assert isinstance(result.tool_argument_resolver, DefaultToolArgumentResolver)

    def test_result_is_unpackable(self):
        """返り値は unpacking で取得可能"""
        deps = _minimal_tool_stack_deps()
        result = _build_tool_stack(**deps)
        provider, mapper, resolver = result
        assert provider is result.available_tools_provider
        assert mapper is result.tool_command_mapper
        assert resolver is result.tool_argument_resolver


def _minimal_wiring_deps():
    """create_llm_agent_wiring に渡す最小限のモック依存を返す。"""
    from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
    from ai_rpg_world.application.world.services.world_query_service import (
        WorldQueryService,
    )
    from ai_rpg_world.application.world.services.movement_service import (
        MovementApplicationService,
    )

    uow = MagicMock(spec=UnitOfWorkFactory)
    uow.create.return_value = MagicMock()
    uow.create.return_value.__enter__ = MagicMock(return_value=MagicMock())
    uow.create.return_value.__exit__ = MagicMock(return_value=False)
    wq = MagicMock(spec=WorldQueryService)
    wq.get_player_current_state = MagicMock(return_value=None)
    mov = MagicMock(spec=MovementApplicationService)
    mov.move_to_destination = MagicMock()
    mov.cancel_movement = MagicMock()
    return {
        "player_status_repository": MagicMock(spec=PlayerStatusRepository),
        "physical_map_repository": MagicMock(spec=PhysicalMapRepository),
        "world_query_service": wq,
        "movement_service": mov,
        "player_profile_repository": MagicMock(spec=PlayerProfileRepository),
        "unit_of_work_factory": uow,
    }


class TestBuildToolStackIntegration:
    """create_llm_agent_wiring 経由での統合確認"""

    def test_wiring_uses_tool_stack_from_build(self):
        """create_llm_agent_wiring で _build_tool_stack 経由の mapper が使われる"""
        from ai_rpg_world.application.llm.wiring import create_llm_agent_wiring

        deps = _minimal_wiring_deps()
        result = create_llm_agent_wiring(**deps)
        orchestrator = result.llm_turn_trigger._turn_runner._orchestrator
        assert orchestrator._tool_command_mapper is not None
        assert orchestrator._tool_argument_resolver is not None
