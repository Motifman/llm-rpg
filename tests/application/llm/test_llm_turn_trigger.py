"""DefaultLlmTurnTrigger のテスト（正常・境界・例外・初期化）"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.services.action_result_store import DefaultActionResultStore
from ai_rpg_world.application.llm.services.agent_orchestrator import LlmAgentOrchestrator
from ai_rpg_world.application.llm.services.llm_agent_turn_runner import LlmAgentTurnRunner
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.services.llm_turn_trigger import DefaultLlmTurnTrigger
from ai_rpg_world.application.llm.services.tool_command_mapper import ToolCommandMapper
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_NO_OP
from ai_rpg_world.application.llm.contracts.interfaces import IPromptBuilder
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world.exceptions.base_exception import WorldApplicationException
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _StubPromptBuilder(IPromptBuilder):
    def build(self, player_id, action_instruction=None):
        return {
            "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
            "tools": [{"type": "function", "function": {"name": TOOL_NAME_NO_OP, "description": "", "parameters": {}}}],
            "tool_choice": "required",
        }


def _make_runner():
    action_result_store = DefaultActionResultStore(max_entries_per_player=10)
    prompt_builder = _StubPromptBuilder()
    llm_client = StubLlmClient(tool_call_to_return={"name": TOOL_NAME_NO_OP, "arguments": {}})
    orchestrator = LlmAgentOrchestrator(
        prompt_builder=prompt_builder,
        llm_client=llm_client,
        tool_command_mapper=ToolCommandMapper(movement_service=MagicMock()),
        action_result_store=action_result_store,
    )
    return LlmAgentTurnRunner(
        observation_buffer=DefaultObservationContextBuffer(),
        world_query_service=MagicMock(get_player_current_state=lambda q: MagicMock(spec=PlayerCurrentStateDto, is_busy=False)),
        movement_service=MagicMock(),
        action_result_store=action_result_store,
        orchestrator=orchestrator,
    )


class TestDefaultLlmTurnTriggerScheduleAndRun:
    """schedule_turn と run_scheduled_turns の正常・境界ケース"""

    @pytest.fixture
    def trigger(self):
        return DefaultLlmTurnTrigger(_make_runner())

    def test_schedule_one_run_scheduled_turns_calls_run_turn_once(self, trigger):
        """1 プレイヤーをスケジュールして run_scheduled_turns で run_turn が 1 回呼ばれる"""
        runner = trigger._turn_runner
        spy = MagicMock(wraps=runner.run_turn)
        trigger._turn_runner.run_turn = spy

        trigger.schedule_turn(PlayerId(1))
        trigger.run_scheduled_turns()

        spy.assert_called_once_with(PlayerId(1))

    def test_schedule_two_players_run_scheduled_turns_calls_both(self, trigger):
        """2 プレイヤーをスケジュールすると両方 run_turn される"""
        runner = trigger._turn_runner
        spy = MagicMock(wraps=runner.run_turn)
        trigger._turn_runner.run_turn = spy

        trigger.schedule_turn(PlayerId(1))
        trigger.schedule_turn(PlayerId(2))
        trigger.run_scheduled_turns()

        assert spy.call_count == 2
        spy.assert_any_call(PlayerId(1))
        spy.assert_any_call(PlayerId(2))

    def test_schedule_same_player_twice_run_turn_once(self, trigger):
        """同一プレイヤーを複数回スケジュールしても run_turn は 1 回だけ"""
        runner = trigger._turn_runner
        spy = MagicMock(wraps=runner.run_turn)
        trigger._turn_runner.run_turn = spy

        trigger.schedule_turn(PlayerId(1))
        trigger.schedule_turn(PlayerId(1))
        trigger.run_scheduled_turns()

        spy.assert_called_once_with(PlayerId(1))

    def test_run_scheduled_turns_empty_no_op(self, trigger):
        """スケジュールなしで run_scheduled_turns は何も呼ばない"""
        spy = MagicMock()
        trigger._turn_runner.run_turn = spy

        trigger.run_scheduled_turns()

        spy.assert_not_called()

    def test_run_scheduled_turns_clears_pending(self, trigger):
        """run_scheduled_turns 後はキューが空になり、2 回目は no-op"""
        spy = MagicMock(wraps=trigger._turn_runner.run_turn)
        trigger._turn_runner.run_turn = spy

        trigger.schedule_turn(PlayerId(1))
        trigger.run_scheduled_turns()
        assert spy.call_count == 1
        trigger.run_scheduled_turns()
        assert spy.call_count == 1

    def test_should_reschedule_true_re_adds_to_pending(self, trigger):
        """run_turn が should_reschedule=True を返すと次 tick 用に _pending へ戻る"""
        trigger._turn_runner.run_turn = MagicMock(
            return_value=LlmCommandResultDto(
                success=False,
                message="NO_TOOL_CALL",
                error_code="NO_TOOL_CALL",
                should_reschedule=True,
            )
        )
        trigger.schedule_turn(PlayerId(1))
        trigger.run_scheduled_turns()
        assert 1 in trigger._pending

    def test_llm_api_exception_reschedulable_re_adds_to_pending(self):
        """LlmApiCallException が DTO に正規化され should_reschedule で trigger が再スケジュールする"""
        action_result_store = DefaultActionResultStore(max_entries_per_player=10)
        llm_client = StubLlmClient(
            exception_to_raise=LlmApiCallException("Rate limit", error_code="LLM_RATE_LIMIT")
        )
        orchestrator = LlmAgentOrchestrator(
            prompt_builder=_StubPromptBuilder(),
            llm_client=llm_client,
            tool_command_mapper=ToolCommandMapper(movement_service=MagicMock()),
            action_result_store=action_result_store,
        )
        runner = LlmAgentTurnRunner(
            observation_buffer=DefaultObservationContextBuffer(),
            world_query_service=MagicMock(
                get_player_current_state=lambda q: MagicMock(
                    spec=PlayerCurrentStateDto, is_busy=False
                )
            ),
            movement_service=MagicMock(),
            action_result_store=action_result_store,
            orchestrator=orchestrator,
        )
        trigger = DefaultLlmTurnTrigger(runner)
        trigger.schedule_turn(PlayerId(1))
        trigger.run_scheduled_turns()
        assert 1 in trigger._pending

    def test_schedule_turn_player_id_not_player_id_raises(self, trigger):
        """schedule_turn に PlayerId でない値を渡すと TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            trigger.schedule_turn(1)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            trigger.schedule_turn(None)  # type: ignore[arg-type]

    def test_was_no_op_does_not_continue(self, trigger):
        """world_no_op のときは継続せず pending に追加しない"""
        trigger._turn_runner.run_turn = MagicMock(
            return_value=LlmCommandResultDto(
                success=True,
                message="何もしませんでした。",
                was_no_op=True,
            )
        )
        trigger.schedule_turn(PlayerId(1))
        trigger.run_scheduled_turns()
        assert 1 not in trigger._pending

    def test_continues_until_max_turns_when_not_no_op(self, trigger):
        """world_no_op 以外で max_turns 未達なら継続する"""
        call_count = 0

        def side_effect(_pid):
            nonlocal call_count
            call_count += 1
            return LlmCommandResultDto(
                success=True,
                message="行動した",
                was_no_op=False,
            )

        trigger._turn_runner.run_turn = MagicMock(side_effect=side_effect)
        trigger.schedule_turn(PlayerId(1))
        trigger.run_scheduled_turns()
        assert 1 in trigger._pending
        assert call_count == 1
        trigger.run_scheduled_turns()
        assert call_count == 2

    def test_stops_at_max_turns(self):
        """max_turns に達したら継続しない"""
        runner = _make_runner()
        trigger = DefaultLlmTurnTrigger(runner, max_turns=2)
        trigger._turn_runner.run_turn = MagicMock(
            return_value=LlmCommandResultDto(
                success=True,
                message="行動した",
                was_no_op=False,
            )
        )
        trigger.schedule_turn(PlayerId(1))
        trigger.run_scheduled_turns()
        assert 1 in trigger._pending
        trigger.run_scheduled_turns()
        assert 1 not in trigger._pending
        assert trigger._turn_runner.run_turn.call_count == 2

    def test_should_reschedule_takes_precedence_over_max_turns(self, trigger):
        """should_reschedule のときは従来どおりエラー再試行として継続"""
        trigger._turn_runner.run_turn = MagicMock(
            return_value=LlmCommandResultDto(
                success=False,
                message="NO_TOOL_CALL",
                error_code="NO_TOOL_CALL",
                should_reschedule=True,
            )
        )
        trigger.schedule_turn(PlayerId(1))
        trigger.run_scheduled_turns()
        assert 1 in trigger._pending


class TestDefaultLlmTurnTriggerRunScheduledTurnsExceptions:
    """run_scheduled_turns のプレイヤー単位例外隔離"""

    @pytest.fixture
    def trigger(self):
        return DefaultLlmTurnTrigger(_make_runner())

    def test_run_turn_raises_isolated_second_player_still_runs(self, trigger):
        """1 人目の run_turn が例外を投げても隔離され、2 人目は実行される"""
        call_count = 0
        def side_effect(pid):
            nonlocal call_count
            call_count += 1
            if pid.value == 1:
                raise RuntimeError("run_turn failed")
            return LlmCommandResultDto(success=True, message="ok")

        trigger._turn_runner.run_turn = MagicMock(side_effect=side_effect)
        trigger.schedule_turn(PlayerId(1))
        trigger.schedule_turn(PlayerId(2))

        trigger.run_scheduled_turns()

        assert call_count == 2
        trigger._turn_runner.run_turn.assert_any_call(PlayerId(1))
        trigger._turn_runner.run_turn.assert_any_call(PlayerId(2))

    def test_run_turn_raises_isolated_does_not_propagate(self, trigger):
        """run_turn が例外を投げても run_scheduled_turns は伝播しない"""
        trigger._turn_runner.run_turn = MagicMock(
            side_effect=WorldApplicationException("app error")
        )
        trigger.schedule_turn(PlayerId(1))

        trigger.run_scheduled_turns()


class TestDefaultLlmTurnTriggerInit:
    """コンストラクタのバリデーション"""

    def test_turn_runner_not_llm_agent_turn_runner_raises(self):
        """turn_runner が LlmAgentTurnRunner でないとき TypeError"""
        with pytest.raises(TypeError, match="turn_runner must be LlmAgentTurnRunner"):
            DefaultLlmTurnTrigger(None)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="turn_runner must be LlmAgentTurnRunner"):
            DefaultLlmTurnTrigger(MagicMock())

    def test_max_turns_invalid_raises_value_error(self):
        """max_turns が 1 未満のとき ValueError"""
        with pytest.raises(ValueError, match="max_turns must be a positive int"):
            DefaultLlmTurnTrigger(_make_runner(), max_turns=0)
        with pytest.raises(ValueError, match="max_turns must be a positive int"):
            DefaultLlmTurnTrigger(_make_runner(), max_turns=-1)

    def test_max_turns_default_is_5(self):
        """max_turns 省略時は 5"""
        trigger = DefaultLlmTurnTrigger(_make_runner())
        assert trigger._max_turns == 5
