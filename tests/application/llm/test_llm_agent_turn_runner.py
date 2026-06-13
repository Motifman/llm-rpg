"""LlmAgentTurnRunner のテスト（正常・割り込み・例外・境界）"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.contracts.interfaces import IPromptBuilder
from ai_rpg_world.application.llm.services.action_result_store import DefaultActionResultStore
from ai_rpg_world.application.llm.services.agent_orchestrator import LlmAgentOrchestrator
from ai_rpg_world.application.llm.services.llm_agent_turn_runner import LlmAgentTurnRunner
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from tests.application.llm.conftest import _create_tool_command_mapper
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_NO_OP
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry, ObservationOutput
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world.exceptions.base_exception import (
    WorldApplicationException,
    WorldSystemErrorException,
)
from ai_rpg_world.application.being.being_provisioning_service import (
    BeingProvisioningService,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
    InMemoryBeingRepository,
)


class _StubPromptBuilder(IPromptBuilder):
    def __init__(self, return_value: dict):
        self._return_value = return_value

    def build(self, player_id, action_instruction=None):
        return self._return_value


def _make_orchestrator(action_result_store):
    prompt_builder = _StubPromptBuilder(return_value={
        "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
        "tools": [{"type": "function", "function": {"name": TOOL_NAME_NO_OP, "description": "", "parameters": {}}}],
        "tool_choice": "required",
    })
    llm_client = StubLlmClient(tool_call_to_return={"name": TOOL_NAME_NO_OP, "arguments": {}})
    return LlmAgentOrchestrator(
        prompt_builder=prompt_builder,
        llm_client=llm_client,
        tool_command_mapper=_create_tool_command_mapper(movement_service=MagicMock()),
        action_result_store=action_result_store,
    )


class TestLlmAgentTurnRunnerRunTurn:
    """run_turn の正常・割り込みケース"""

    @pytest.fixture
    def action_result_store(self):
        return DefaultActionResultStore(max_entries_per_player=10)

    @pytest.fixture
    def orchestrator(self, action_result_store):
        return _make_orchestrator(action_result_store)

    @pytest.fixture
    def observation_buffer(self):
        return DefaultObservationContextBuffer()

    @pytest.fixture
    def world_query_service(self):
        return MagicMock()

    @pytest.fixture
    def movement_service(self):
        return MagicMock()

    @pytest.fixture
    def runner(
        self,
        observation_buffer,
        world_query_service,
        movement_service,
        action_result_store,
        orchestrator,
    ):
        return LlmAgentTurnRunner(
            observation_buffer=observation_buffer,
            world_query_service=world_query_service,
            movement_service=movement_service,
            action_result_store=action_result_store,
            orchestrator=orchestrator,
        )

    def test_run_turn_normal_delegates_to_orchestrator(self, runner, movement_service, action_result_store):
        """オーケストレータのみ実行。即時停止は ObservationEventHandler 側で行われる。"""
        player_id = PlayerId(1)

        result = runner.run_turn(player_id)

        assert isinstance(result, LlmCommandResultDto)
        movement_service.cancel_movement.assert_not_called()
        recent = action_result_store.get_recent(player_id, 5)
        assert len(recent) == 1

    def test_run_turn_with_observations_in_buffer_still_delegates_only(self, runner, observation_buffer, movement_service, action_result_store):
        """観測バッファに breaks_movement 観測があっても cancel は呼ばない（ObservationEventHandler 側で済んでいる）"""
        player_id = PlayerId(1)
        entry = ObservationEntry(
            occurred_at=datetime.now(),
            output=ObservationOutput(prose="戦闘不能になりました。", structured={"type": "player_downed"}, schedules_turn=True, breaks_movement=True),
        )
        observation_buffer.append(player_id, entry)

        result = runner.run_turn(player_id)

        assert isinstance(result, LlmCommandResultDto)
        movement_service.cancel_movement.assert_not_called()
        recent = action_result_store.get_recent(player_id, 5)
        assert len(recent) == 1

    def test_run_turn_player_id_not_player_id_raises(self, runner):
        """player_id が PlayerId でないとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            runner.run_turn(1)  # type: ignore[arg-type]

    def test_run_turn_proceeds_to_orchestrator(self, runner, movement_service, action_result_store):
        """オーケストレータのみ実行。"""
        player_id = PlayerId(1)

        result = runner.run_turn(player_id)

        assert isinstance(result, LlmCommandResultDto)
        movement_service.cancel_movement.assert_not_called()
        recent = action_result_store.get_recent(player_id, 5)
        assert len(recent) == 1


class TestLlmAgentTurnRunnerRunTurnExceptions:
    """run_turn の例外・依存失敗ケース（WorldSystemErrorException に包む／そのまま伝播）"""

    @pytest.fixture
    def action_result_store(self):
        return DefaultActionResultStore(max_entries_per_player=10)

    @pytest.fixture
    def orchestrator(self, action_result_store):
        return _make_orchestrator(action_result_store)

    @pytest.fixture
    def observation_buffer(self):
        return DefaultObservationContextBuffer()

    @pytest.fixture
    def world_query_service(self):
        return MagicMock()

    @pytest.fixture
    def movement_service(self):
        return MagicMock()

    @pytest.fixture
    def runner(
        self,
        observation_buffer,
        world_query_service,
        movement_service,
        action_result_store,
        orchestrator,
    ):
        return LlmAgentTurnRunner(
            observation_buffer=observation_buffer,
            world_query_service=world_query_service,
            movement_service=movement_service,
            action_result_store=action_result_store,
            orchestrator=orchestrator,
        )

    def test_run_turn_orchestrator_raises_runtime_error_wraps_in_world_system_error(
        self, runner
    ):
        """orchestrator.run_turn が RuntimeError を投げたとき WorldSystemErrorException に包まれて伝播"""
        player_id = PlayerId(1)
        runner._orchestrator.run_turn = MagicMock(side_effect=RuntimeError("orchestrator failed"))

        with pytest.raises(WorldSystemErrorException) as exc_info:
            runner.run_turn(player_id)

        assert exc_info.value.original_exception is not None
        assert isinstance(exc_info.value.original_exception, RuntimeError)
        assert "orchestrator failed" in str(exc_info.value.original_exception)
        assert "run_turn" in str(exc_info.value)

    def test_run_turn_orchestrator_raises_world_application_exception_propagates(
        self, runner
    ):
        """orchestrator.run_turn が WorldApplicationException を投げたときそのまま伝播"""
        player_id = PlayerId(1)
        runner._orchestrator.run_turn = MagicMock(
            side_effect=WorldApplicationException("app error")
        )

        with pytest.raises(WorldApplicationException, match="app error"):
            runner.run_turn(player_id)


class TestLlmAgentTurnRunnerInit:
    """コンストラクタのバリデーション"""

    @pytest.fixture
    def action_result_store(self):
        return DefaultActionResultStore()

    @pytest.fixture
    def orchestrator(self, action_result_store):
        return _make_orchestrator(action_result_store)

    def test_init_observation_buffer_not_interface_raises(self, orchestrator):
        """observation_buffer が IObservationContextBuffer でないとき TypeError"""
        with pytest.raises(TypeError, match="observation_buffer must be IObservationContextBuffer"):
            LlmAgentTurnRunner(
                observation_buffer=None,  # type: ignore[arg-type]
                world_query_service=MagicMock(),
                movement_service=MagicMock(),
                action_result_store=DefaultActionResultStore(),
                orchestrator=orchestrator,
            )

    def test_init_world_query_service_not_callable_raises(self, orchestrator):
        """world_query_service に get_player_current_state が無いとき TypeError"""
        with pytest.raises(TypeError, match="world_query_service must have get_player_current_state"):
            LlmAgentTurnRunner(
                observation_buffer=DefaultObservationContextBuffer(),
                world_query_service=None,  # type: ignore[arg-type]
                movement_service=MagicMock(),
                action_result_store=DefaultActionResultStore(),
                orchestrator=orchestrator,
            )

    def test_init_movement_service_not_callable_raises(self, orchestrator):
        """movement_service に cancel_movement が無いとき TypeError"""
        with pytest.raises(TypeError, match="movement_service must have cancel_movement"):
            LlmAgentTurnRunner(
                observation_buffer=DefaultObservationContextBuffer(),
                world_query_service=MagicMock(),  # get_player_current_state は MagicMock が持つ
                movement_service=None,  # type: ignore[arg-type]
                action_result_store=DefaultActionResultStore(),
                orchestrator=orchestrator,
            )

    def test_init_action_result_store_not_interface_raises(self, orchestrator):
        """action_result_store が IActionResultStore でないとき TypeError"""
        with pytest.raises(TypeError, match="action_result_store must be IActionResultStore"):
            LlmAgentTurnRunner(
                observation_buffer=DefaultObservationContextBuffer(),
                world_query_service=MagicMock(),
                movement_service=MagicMock(),
                action_result_store=None,  # type: ignore[arg-type]
                orchestrator=orchestrator,
            )

    def test_init_orchestrator_not_type_raises(self):
        """orchestrator が LlmAgentOrchestrator でないとき TypeError"""
        with pytest.raises(TypeError, match="orchestrator must be LlmAgentOrchestrator"):
            LlmAgentTurnRunner(
                observation_buffer=DefaultObservationContextBuffer(),
                world_query_service=MagicMock(),
                movement_service=MagicMock(),
                action_result_store=DefaultActionResultStore(),
                orchestrator=None,  # type: ignore[arg-type]
            )


class TestLlmAgentTurnRunnerBeingProvisioningHook:
    """Phase 3 Step 6-mini: being_provisioning_service が turn 開始時に呼ばれる挙動。"""

    @pytest.fixture
    def action_result_store(self):
        return DefaultActionResultStore(max_entries_per_player=10)

    @pytest.fixture
    def orchestrator(self, action_result_store):
        return _make_orchestrator(action_result_store)

    @pytest.fixture
    def being_repo(self):
        return InMemoryBeingRepository()

    @pytest.fixture
    def provisioning_service(self, being_repo):
        return BeingProvisioningService(being_repo)

    @pytest.fixture
    def runner_with_provisioning(
        self,
        action_result_store,
        orchestrator,
        provisioning_service,
    ):
        return LlmAgentTurnRunner(
            observation_buffer=DefaultObservationContextBuffer(),
            world_query_service=MagicMock(),
            movement_service=MagicMock(),
            action_result_store=action_result_store,
            orchestrator=orchestrator,
            being_provisioning_service=provisioning_service,
        )

    def test_run_turn_で_Being_が_provision_される(
        self, runner_with_provisioning, being_repo
    ):
        """provisioning_service 注入時、run_turn 起動で Being が新規作成・attach される。"""
        runner_with_provisioning.run_turn(PlayerId(1))
        being = being_repo.find_by_id(BeingId("being_w1_p1"))
        assert being is not None
        assert being.is_attached is True

    def test_2_回_run_turn_しても_Being_は_idempotent(
        self, runner_with_provisioning, being_repo
    ):
        """同じ player に対し 2 回 run_turn しても Being は 1 つだけ (= idempotent)。"""
        runner_with_provisioning.run_turn(PlayerId(1))
        runner_with_provisioning.run_turn(PlayerId(1))
        # find_all_attached_to で 1 件のみ確認
        matches = being_repo.find_all_attached_to(WorldId(1), PlayerId(1))
        assert len(matches) == 1

    def test_provisioning_service_未注入なら_Being_は作られない(
        self,
        action_result_store,
        orchestrator,
        being_repo,
    ):
        """既存挙動: provisioning_service を渡さなければ Being は作られない (= 後方互換)。"""
        runner = LlmAgentTurnRunner(
            observation_buffer=DefaultObservationContextBuffer(),
            world_query_service=MagicMock(),
            movement_service=MagicMock(),
            action_result_store=action_result_store,
            orchestrator=orchestrator,
        )
        runner.run_turn(PlayerId(1))
        assert being_repo.find_by_id(BeingId("being_w1_p1")) is None

    def test_provisioning_失敗時も_turn_は続行される(
        self,
        action_result_store,
        orchestrator,
    ):
        """provisioning 例外は warning ログのみで turn を止めない (= 最小回帰)。"""
        broken_service = MagicMock()
        broken_service.ensure_attached.side_effect = RuntimeError("provisioning broke")
        runner = LlmAgentTurnRunner(
            observation_buffer=DefaultObservationContextBuffer(),
            world_query_service=MagicMock(),
            movement_service=MagicMock(),
            action_result_store=action_result_store,
            orchestrator=orchestrator,
            being_provisioning_service=broken_service,
        )
        # 例外が turn を止めないことを確認
        result = runner.run_turn(PlayerId(1))
        assert result is not None

    def test_provisioning_service_に_ensure_attached_が無いと_TypeError(
        self,
        action_result_store,
        orchestrator,
    ):
        """duck-typing で ensure_attached(callable) を確認。無ければ TypeError。"""
        with pytest.raises(TypeError, match="ensure_attached"):
            LlmAgentTurnRunner(
                observation_buffer=DefaultObservationContextBuffer(),
                world_query_service=MagicMock(),
                movement_service=MagicMock(),
                action_result_store=action_result_store,
                orchestrator=orchestrator,
                being_provisioning_service="not-a-service",
            )
