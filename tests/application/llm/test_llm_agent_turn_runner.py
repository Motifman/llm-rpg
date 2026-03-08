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
from ai_rpg_world.application.llm.services.tool_command_mapper import ToolCommandMapper
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
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


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
        tool_command_mapper=ToolCommandMapper(movement_service=MagicMock()),
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

    def test_run_turn_normal_no_observations(self, runner, world_query_service, movement_service, action_result_store):
        """観測が無い場合は割り込みせずオーケストレータのみ実行"""
        player_id = PlayerId(1)
        world_query_service.get_player_current_state.return_value = MagicMock(
            spec=PlayerCurrentStateDto,
            is_busy=False,
            has_active_path=False,
        )

        result = runner.run_turn(player_id)

        assert isinstance(result, LlmCommandResultDto)
        movement_service.cancel_movement.assert_not_called()
        recent = action_result_store.get_recent(player_id, 5)
        assert len(recent) == 1
        assert "中断" not in recent[0].action_summary

    def test_run_turn_normal_not_busy(self, runner, observation_buffer, world_query_service, movement_service, action_result_store):
        """is_busy が False の場合は割り込みしない"""
        player_id = PlayerId(1)
        entry = ObservationEntry(
            occurred_at=datetime.now(),
            output=ObservationOutput(prose="戦闘不能になりました。", structured={"type": "player_downed"}, causes_interrupt=True),
        )
        observation_buffer.append(player_id, entry)
        world_query_service.get_player_current_state.return_value = MagicMock(
            spec=PlayerCurrentStateDto,
            is_busy=False,
            has_active_path=False,
        )

        result = runner.run_turn(player_id)

        assert isinstance(result, LlmCommandResultDto)
        movement_service.cancel_movement.assert_not_called()
        recent = action_result_store.get_recent(player_id, 5)
        assert len(recent) == 1

    def test_run_turn_normal_no_interrupting_observation(self, runner, observation_buffer, world_query_service, movement_service, action_result_store):
        """観測が causes_interrupt=False のみの場合は割り込みしない"""
        player_id = PlayerId(1)
        entry = ObservationEntry(
            occurred_at=datetime.now(),
            output=ObservationOutput(prose="天気が変わった。", structured={"type": "weather"}, observation_category="environment", causes_interrupt=False),
        )
        observation_buffer.append(player_id, entry)
        world_query_service.get_player_current_state.return_value = MagicMock(
            spec=PlayerCurrentStateDto,
            is_busy=True,
            has_active_path=True,
        )

        result = runner.run_turn(player_id)

        movement_service.cancel_movement.assert_not_called()
        recent = action_result_store.get_recent(player_id, 5)
        assert len(recent) == 1

    def test_run_turn_with_interrupt_and_active_path_calls_cancel_and_appends(
        self,
        runner,
        observation_buffer,
        world_query_service,
        movement_service,
        action_result_store,
    ):
        """移動経路ありかつ割り込み観測ありのとき cancel_movement と append が呼ばれる"""
        player_id = PlayerId(1)
        entry = ObservationEntry(
            occurred_at=datetime.now(),
            output=ObservationOutput(prose="戦闘不能になりました。", structured={"type": "player_downed"}, causes_interrupt=True),
        )
        observation_buffer.append(player_id, entry)
        world_query_service.get_player_current_state.return_value = MagicMock(
            spec=PlayerCurrentStateDto,
            is_busy=True,
            has_active_path=True,
        )

        result = runner.run_turn(player_id)

        assert isinstance(result, LlmCommandResultDto)
        movement_service.cancel_movement.assert_called_once()
        call_args = movement_service.cancel_movement.call_args[0][0]
        assert call_args.player_id == 1
        recent = action_result_store.get_recent(player_id, 5)
        assert len(recent) == 2
        assert any("移動" in e.action_summary and "中断" in e.action_summary for e in recent)
        assert any("以下の観測により移動を中断" in e.result_summary for e in recent)

    def test_run_turn_with_interrupt_and_only_busy_does_not_cancel(
        self,
        runner,
        observation_buffer,
        world_query_service,
        movement_service,
        action_result_store,
    ):
        """busy でも移動経路がなければ割り込みで cancel_movement しない"""
        player_id = PlayerId(1)
        entry = ObservationEntry(
            occurred_at=datetime.now(),
            output=ObservationOutput(prose="戦闘不能になりました。", structured={"type": "player_downed"}, causes_interrupt=True),
        )
        observation_buffer.append(player_id, entry)
        world_query_service.get_player_current_state.return_value = MagicMock(
            spec=PlayerCurrentStateDto,
            is_busy=True,
            has_active_path=False,
        )

        result = runner.run_turn(player_id)

        assert isinstance(result, LlmCommandResultDto)
        movement_service.cancel_movement.assert_not_called()
        recent = action_result_store.get_recent(player_id, 5)
        assert len(recent) == 1
        assert all("移動が中断" not in e.action_summary for e in recent)

    def test_run_turn_with_interrupt_and_active_path_calls_cancel_and_appends(self, runner, observation_buffer, world_query_service, movement_service, action_result_store):
        """is_busy が False でも has_active_path=True なら割り込み時に cancel_movement する"""
        player_id = PlayerId(1)
        entry = ObservationEntry(
            occurred_at=datetime.now(),
            output=ObservationOutput(prose="戦闘不能になりました。", structured={"type": "player_downed"}, causes_interrupt=True),
        )
        observation_buffer.append(player_id, entry)
        world_query_service.get_player_current_state.return_value = MagicMock(
            spec=PlayerCurrentStateDto,
            is_busy=False,
            has_active_path=True,
        )

        runner.run_turn(player_id)

        movement_service.cancel_movement.assert_called_once()

    def test_run_turn_player_id_not_player_id_raises(self, runner):
        """player_id が PlayerId でないとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            runner.run_turn(1)  # type: ignore[arg-type]

    def test_run_turn_when_current_state_none_proceeds_to_orchestrator(
        self, runner, world_query_service, movement_service, action_result_store
    ):
        """get_player_current_state が None（未配置）のときは割り込みせずオーケストレータのみ実行"""
        player_id = PlayerId(1)
        world_query_service.get_player_current_state.return_value = None

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
        self, runner, world_query_service
    ):
        """orchestrator.run_turn が RuntimeError を投げたとき WorldSystemErrorException に包まれて伝播"""
        player_id = PlayerId(1)
        world_query_service.get_player_current_state.return_value = MagicMock(
            spec=PlayerCurrentStateDto, is_busy=False
        )
        runner._orchestrator.run_turn = MagicMock(side_effect=RuntimeError("orchestrator failed"))

        with pytest.raises(WorldSystemErrorException) as exc_info:
            runner.run_turn(player_id)

        assert exc_info.value.original_exception is not None
        assert isinstance(exc_info.value.original_exception, RuntimeError)
        assert "orchestrator failed" in str(exc_info.value.original_exception)
        assert "run_turn" in str(exc_info.value)

    def test_run_turn_orchestrator_raises_world_application_exception_propagates(
        self, runner, world_query_service
    ):
        """orchestrator.run_turn が WorldApplicationException を投げたときそのまま伝播"""
        player_id = PlayerId(1)
        world_query_service.get_player_current_state.return_value = MagicMock(
            spec=PlayerCurrentStateDto, is_busy=False
        )
        runner._orchestrator.run_turn = MagicMock(
            side_effect=WorldApplicationException("app error")
        )

        with pytest.raises(WorldApplicationException, match="app error"):
            runner.run_turn(player_id)

    def test_run_turn_get_observations_raises_wraps_in_world_system_error(
        self, runner, observation_buffer, world_query_service
    ):
        """observation_buffer.get_observations が例外を投げたとき WorldSystemErrorException に包まれる"""
        player_id = PlayerId(1)
        observation_buffer.get_observations = MagicMock(side_effect=RuntimeError("buffer failed"))
        world_query_service.get_player_current_state.return_value = MagicMock(
            spec=PlayerCurrentStateDto, is_busy=False
        )

        with pytest.raises(WorldSystemErrorException) as exc_info:
            runner.run_turn(player_id)

        assert exc_info.value.original_exception is not None
        assert isinstance(exc_info.value.original_exception, RuntimeError)

    def test_run_turn_world_query_service_raises_wraps_in_world_system_error(
        self, runner, world_query_service
    ):
        """world_query_service.get_player_current_state が例外を投げたとき WorldSystemErrorException に包まれる"""
        player_id = PlayerId(1)
        world_query_service.get_player_current_state.side_effect = RuntimeError("query failed")

        with pytest.raises(WorldSystemErrorException) as exc_info:
            runner.run_turn(player_id)

        assert exc_info.value.original_exception is not None
        assert isinstance(exc_info.value.original_exception, RuntimeError)

    def test_run_turn_cancel_movement_raises_wraps_in_world_system_error(
        self,
        runner,
        observation_buffer,
        world_query_service,
        movement_service,
        action_result_store,
    ):
        """割り込み時に cancel_movement が例外を投げたとき WorldSystemErrorException に包まれる"""
        player_id = PlayerId(1)
        entry = ObservationEntry(
            occurred_at=datetime.now(),
            output=ObservationOutput(
                prose="戦闘不能になりました。",
                structured={"type": "player_downed"},
                causes_interrupt=True,
            ),
        )
        observation_buffer.append(player_id, entry)
        world_query_service.get_player_current_state.return_value = MagicMock(
            spec=PlayerCurrentStateDto,
            is_busy=True,
            has_active_path=True,
        )
        movement_service.cancel_movement.side_effect = RuntimeError("cancel failed")

        with pytest.raises(WorldSystemErrorException) as exc_info:
            runner.run_turn(player_id)

        movement_service.cancel_movement.assert_called_once()
        assert exc_info.value.original_exception is not None
        assert isinstance(exc_info.value.original_exception, RuntimeError)
        # append は cancel の後なので呼ばれない
        recent = action_result_store.get_recent(player_id, 5)
        assert len(recent) == 0

    def test_run_turn_action_result_store_append_raises_wraps_in_world_system_error(
        self,
        runner,
        observation_buffer,
        world_query_service,
        movement_service,
        action_result_store,
    ):
        """割り込み時に action_result_store.append が例外を投げたとき WorldSystemErrorException に包まれる"""
        player_id = PlayerId(1)
        entry = ObservationEntry(
            occurred_at=datetime.now(),
            output=ObservationOutput(
                prose="戦闘不能になりました。",
                structured={"type": "player_downed"},
                causes_interrupt=True,
            ),
        )
        observation_buffer.append(player_id, entry)
        world_query_service.get_player_current_state.return_value = MagicMock(
            spec=PlayerCurrentStateDto,
            is_busy=True,
            has_active_path=True,
        )
        movement_service.cancel_movement.return_value = MagicMock(success=True)
        action_result_store.append = MagicMock(side_effect=RuntimeError("append failed"))

        with pytest.raises(WorldSystemErrorException) as exc_info:
            runner.run_turn(player_id)

        movement_service.cancel_movement.assert_called_once()
        action_result_store.append.assert_called_once()
        assert exc_info.value.original_exception is not None
        assert isinstance(exc_info.value.original_exception, RuntimeError)


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
