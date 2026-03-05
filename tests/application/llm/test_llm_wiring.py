"""create_llm_agent_wiring のテスト（正常・境界・例外）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.llm.contracts.interfaces import ILlmTurnTrigger
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.wiring import create_llm_agent_wiring
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)
from ai_rpg_world.application.world.services.world_query_service import (
    WorldQueryService,
)
from ai_rpg_world.application.world.services.movement_service import (
    MovementApplicationService,
)
from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
from ai_rpg_world.domain.player.repository.player_profile_repository import (
    PlayerProfileRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)
from ai_rpg_world.infrastructure.events.observation_event_handler_registry import (
    ObservationEventHandlerRegistry,
)


def _minimal_wiring_deps():
    """create_llm_agent_wiring に渡す最小限のモック依存を返す。"""
    uow_factory = MagicMock(spec=UnitOfWorkFactory)
    uow_factory.create.return_value = MagicMock()
    uow_factory.create.return_value.__enter__ = MagicMock(return_value=MagicMock())
    uow_factory.create.return_value.__exit__ = MagicMock(return_value=False)
    world_query = MagicMock(spec=WorldQueryService)
    world_query.get_player_current_state = MagicMock(return_value=None)
    movement = MagicMock(spec=MovementApplicationService)
    movement.move_to_destination = MagicMock()
    movement.cancel_movement = MagicMock()
    return {
        "player_status_repository": MagicMock(spec=PlayerStatusRepository),
        "physical_map_repository": MagicMock(spec=PhysicalMapRepository),
        "world_query_service": world_query,
        "movement_service": movement,
        "player_profile_repository": MagicMock(spec=PlayerProfileRepository),
        "unit_of_work_factory": uow_factory,
    }


class TestCreateLlmAgentWiringReturnValues:
    """create_llm_agent_wiring の戻り値（正常）"""

    def test_returns_tuple_of_registry_and_trigger(self):
        """(ObservationEventHandlerRegistry, ILlmTurnTrigger) のタプルを返す"""
        deps = _minimal_wiring_deps()
        result = create_llm_agent_wiring(**deps)
        assert isinstance(result, tuple)
        assert len(result) == 2
        registry, trigger = result
        assert isinstance(registry, ObservationEventHandlerRegistry)
        assert isinstance(trigger, ILlmTurnTrigger)

    def test_registry_has_register_handlers(self):
        """返された Registry は register_handlers メソッドを持つ"""
        deps = _minimal_wiring_deps()
        registry, _ = create_llm_agent_wiring(**deps)
        assert hasattr(registry, "register_handlers")
        assert callable(registry.register_handlers)

    def test_trigger_has_schedule_turn_and_run_scheduled_turns(self):
        """返された Trigger は schedule_turn と run_scheduled_turns を持つ"""
        deps = _minimal_wiring_deps()
        _, trigger = create_llm_agent_wiring(**deps)
        assert hasattr(trigger, "schedule_turn")
        assert callable(trigger.schedule_turn)
        assert hasattr(trigger, "run_scheduled_turns")
        assert callable(trigger.run_scheduled_turns)

    def test_run_scheduled_turns_empty_does_not_raise(self):
        """スケジュール済みがいない状態で run_scheduled_turns を呼んでも例外が出ない"""
        deps = _minimal_wiring_deps()
        _, trigger = create_llm_agent_wiring(**deps)
        trigger.run_scheduled_turns()

    def test_accepts_optional_llm_client(self):
        """llm_client を渡した場合、そのクライアントが使われる（戻り値の型は同じ）"""
        deps = _minimal_wiring_deps()
        deps["llm_client"] = StubLlmClient()
        registry, trigger = create_llm_agent_wiring(**deps)
        assert isinstance(registry, ObservationEventHandlerRegistry)
        assert isinstance(trigger, ILlmTurnTrigger)

    def test_accepts_optional_observation_buffer(self):
        """observation_buffer を渡した場合、そのバッファが使われる"""
        custom_buffer = MagicMock(spec=IObservationContextBuffer)
        deps = _minimal_wiring_deps()
        deps["observation_buffer"] = custom_buffer
        registry, _ = create_llm_agent_wiring(**deps)
        assert registry._handler._buffer is custom_buffer


class TestCreateLlmAgentWiringRequiredParams:
    """必須引数が None のときに TypeError を出す"""

    @pytest.fixture
    def deps(self):
        return _minimal_wiring_deps()

    def test_player_status_repository_none_raises_type_error(self, deps):
        """player_status_repository が None のとき TypeError"""
        deps["player_status_repository"] = None
        with pytest.raises(TypeError, match="player_status_repository must not be None"):
            create_llm_agent_wiring(**deps)

    def test_physical_map_repository_none_raises_type_error(self, deps):
        """physical_map_repository が None のとき TypeError"""
        deps["physical_map_repository"] = None
        with pytest.raises(TypeError, match="physical_map_repository must not be None"):
            create_llm_agent_wiring(**deps)

    def test_world_query_service_none_raises_type_error(self, deps):
        """world_query_service が None のとき TypeError"""
        deps["world_query_service"] = None
        with pytest.raises(TypeError, match="world_query_service must not be None"):
            create_llm_agent_wiring(**deps)

    def test_movement_service_none_raises_type_error(self, deps):
        """movement_service が None のとき TypeError"""
        deps["movement_service"] = None
        with pytest.raises(TypeError, match="movement_service must not be None"):
            create_llm_agent_wiring(**deps)

    def test_player_profile_repository_none_raises_type_error(self, deps):
        """player_profile_repository が None のとき TypeError"""
        deps["player_profile_repository"] = None
        with pytest.raises(TypeError, match="player_profile_repository must not be None"):
            create_llm_agent_wiring(**deps)

    def test_unit_of_work_factory_none_raises_type_error(self, deps):
        """unit_of_work_factory が None のとき TypeError"""
        deps["unit_of_work_factory"] = None
        with pytest.raises(TypeError, match="unit_of_work_factory must not be None"):
            create_llm_agent_wiring(**deps)


class TestCreateLlmAgentWiringEnvClient:
    """環境変数 LLM_CLIENT によるクライアント切り替え（llm_client 未指定時）"""

    def test_default_uses_stub_client_when_llm_client_not_passed(self, monkeypatch):
        """llm_client を渡さず LLM_CLIENT 未設定時は StubLlmClient が使われ run_scheduled_turns が動く"""
        monkeypatch.delenv("LLM_CLIENT", raising=False)
        deps = _minimal_wiring_deps()
        registry, trigger = create_llm_agent_wiring(**deps)
        trigger.run_scheduled_turns()

    def test_env_stub_uses_stub_client(self, monkeypatch):
        """LLM_CLIENT=stub のとき StubLlmClient が使われる"""
        monkeypatch.setenv("LLM_CLIENT", "stub")
        deps = _minimal_wiring_deps()
        registry, trigger = create_llm_agent_wiring(**deps)
        trigger.run_scheduled_turns()
