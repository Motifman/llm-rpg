"""考えが出力の上限で切れて行動を返せなかった呼び出しを、考えを止めて 1 回だけ呼び直すことを保証する (#1924、design_decisions D1924)。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from tests.integration.test_world_runtime_current_runtime_contract import (
    _AuxBeingResolverStub,
    _ContractRuntime,
    _GatedReasonFirstRuntime,
    _TraceRecorderSpy,
)

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.contracts.llm_call_metrics import LlmCallMetrics
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.services.prompt_dataset_capture import PromptDatasetCaptureSink
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_ASSESS_SITUATION,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring

_EXPLORE = {"name": TOOL_NAME_SPOT_GRAPH_EXPLORE, "arguments": {}}
_ASSESS = {"name": TOOL_NAME_ASSESS_SITUATION, "arguments": {"inner_thought": "別の手を選ぶ。"}}


class _Cut:
    """考えが出力の上限を使い切り、行動を返さずに打ち切られた応答。"""


class _Stop:
    """考えずに文章だけを返し、上限には届かなかった応答。"""


class _Client:
    """返す応答を順に決められ、本物のクライアントと同じく計測に finish_reason と考えの段階を載せる。"""

    def __init__(self, responses: list[Any], *, configured_effort: str | None = "minimal") -> None:
        self._responses = list(responses)
        self._configured_effort = configured_effort
        self.calls: list[dict[str, Any]] = []

    def invoke(
        self,
        messages,
        tools,
        tool_choice="required",
        *,
        metrics_sink=None,
        reasoning_effort=None,
        prompt_capture_context=None,
        call_phase="one_step",
        session_id=None,
    ):
        self.calls.append(
            {
                "messages": copy.deepcopy(messages),
                "tools": copy.deepcopy(tools),
                "reasoning_effort": reasoning_effort,
                "call_phase": call_phase,
            }
        )
        response = self._responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        tool_call = None if isinstance(response, (_Cut, _Stop)) else copy.deepcopy(response)
        finish_reason = (
            "length" if isinstance(response, _Cut) else "stop" if isinstance(response, _Stop) else "tool_calls"
        )
        if metrics_sink is not None:
            metrics_sink.record(
                LlmCallMetrics(
                    model="stub",
                    wall_latency_ms=1,
                    prompt_tokens=10,
                    completion_tokens=4096 if isinstance(response, _Cut) else 10,
                    tps=0.0,
                    success=tool_call is not None,
                    error_code=None if tool_call is not None else "NO_TOOL_CALL",
                    reasoning_effort=reasoning_effort if reasoning_effort is not None else self._configured_effort,
                    phase=call_phase,
                    finish_reason=finish_reason,
                )
            )
        if prompt_capture_context is not None:
            prompt_capture_context.sink.record_call(
                context=prompt_capture_context.context,
                request_kwargs={"model": "stub", "messages": copy.deepcopy(messages), "tools": copy.deepcopy(tools)},
                response={"choices": [{"message": {}, "finish_reason": finish_reason}]},
                output=tool_call,
                metrics={"success": tool_call is not None, "finish_reason": finish_reason},
                error=None,
            )
        return tool_call


def _one_step_wiring(client: _Client, *, traced: bool = True) -> tuple[_WorldLlmWiring, _ContractRuntime]:
    runtime = _ContractRuntime()
    if traced:
        runtime.trace_recorder = _TraceRecorderSpy()
    wiring = _WorldLlmWiring(runtime=runtime, observation_buffer=runtime._obs_buffer, llm_client=client)
    wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = lambda player_id, arguments, runtime_context: (
        LlmCommandResultDto(success=True, message="探索した。")
    )
    return wiring, runtime


def _retries(runtime: Any) -> list[dict[str, Any]]:
    return [
        payload for kind, payload in runtime.trace_recorder.records if kind == TraceEventKind.LLM_OUTPUT_TRUNCATED_RETRY
    ]


class TestOneStepTurn:
    """1 段の呼び出しで、打ち切られた手番だけを考えを止めて呼び直すことを保証する。"""

    def test_cut_off_turn_is_retried_without_reasoning_and_its_action_runs(self) -> None:
        """打ち切られて行動が返らないと、同じメッセージとツールを考えを止めて (effort none) 1 回だけ送り、返った行動を実行する。"""
        client = _Client([_Cut(), _EXPLORE])
        wiring, runtime = _one_step_wiring(client)

        result = wiring.run_turn(PlayerId(1))

        assert result.success is True
        assert [call["reasoning_effort"] for call in client.calls] == [None, "none"]
        assert client.calls[1]["messages"] == client.calls[0]["messages"]
        assert client.calls[1]["tools"] == client.calls[0]["tools"]
        (retry,) = _retries(runtime)
        assert retry["phase"] == "one_step"
        assert retry["outcome"] == "tool_call"
        assert retry["returned_tool"] == TOOL_NAME_SPOT_GRAPH_EXPLORE
        assert retry["reasoning_effort"] == "minimal"
        assert retry["retry_finish_reason"] == "tool_calls"

    def test_retry_that_also_returns_no_action_is_not_retried_again(self) -> None:
        """呼び直しも行動を返さなければ、2 回目は呼び直さず、今までどおり NO_TOOL_CALL になる。"""
        client = _Client([_Cut(), _Cut()])
        wiring, runtime = _one_step_wiring(client)

        result = wiring.run_turn(PlayerId(1))

        assert result.error_code == "NO_TOOL_CALL"
        assert len(client.calls) == 2
        (retry,) = _retries(runtime)
        assert retry["outcome"] == "no_tool_call"
        assert retry["returned_tool"] is None

    def test_no_action_without_being_cut_off_is_not_retried(self) -> None:
        """上限に届かずに行動を返さなかった (考えずに迷った) 手番は、呼び直さない。"""
        client = _Client([_Stop()])
        wiring, runtime = _one_step_wiring(client)

        result = wiring.run_turn(PlayerId(1))

        assert result.error_code == "NO_TOOL_CALL"
        assert len(client.calls) == 1
        assert _retries(runtime) == []

    def test_cut_off_without_reasoning_is_not_retried(self) -> None:
        """考えを止めた呼び出しが上限で切れても、呼び直しは同じ呼び出しになるので、呼び直さない。"""
        client = _Client([_Cut()], configured_effort=None)
        wiring, runtime = _one_step_wiring(client)

        result = wiring.run_turn(PlayerId(1))

        assert result.error_code == "NO_TOOL_CALL"
        assert len(client.calls) == 1
        assert _retries(runtime) == []

    def test_retry_happens_even_without_a_trace_recorder(self) -> None:
        """trace の受け口が無くても、打ち切られた手番は呼び直す。呼び直すかを trace の有無に左右させない。"""
        client = _Client([_Cut(), _EXPLORE])
        wiring, _ = _one_step_wiring(client, traced=False)

        result = wiring.run_turn(PlayerId(1))

        assert result.success is True
        assert len(client.calls) == 2

    def test_retry_failing_with_an_exception_goes_the_failed_call_way(self) -> None:
        """呼び直しが例外で失敗したら、呼び出しの失敗として扱い、呼び直しの結果を invoke_exception で trace に残す。"""
        client = _Client([_Cut(), LlmApiCallException("down", error_code="LLM_API_CALL_FAILED")])
        wiring, runtime = _one_step_wiring(client)

        result = wiring.run_turn(PlayerId(1))

        assert result.success is False
        assert len(client.calls) == 2
        (retry,) = _retries(runtime)
        assert (retry["outcome"], retry["error_type"]) == ("invoke_exception", "LlmApiCallException")


def test_retried_call_is_kept_in_the_prompt_dataset_as_the_next_attempt(tmp_path: Path) -> None:
    """prompt dataset には、打ち切られた呼び出しと呼び直しの 2 行が残る。呼び直しは attempt_index 1 で、親は打ち切られた呼び出し。"""
    runtime = _ContractRuntime()
    runtime.trace_recorder = _TraceRecorderSpy()
    runtime.aux_being_resolver = _AuxBeingResolverStub()
    runtime.aux_being_default_world_id = WorldId(1)
    sink = PromptDatasetCaptureSink(run_dir=tmp_path, run_id="run-1924", run_metadata={"profile": "test"})
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        llm_client=_Client([_Cut(), _EXPLORE]),
        prompt_dataset_sink=sink,
    )
    wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = lambda player_id, arguments, runtime_context: (
        LlmCommandResultDto(success=True, message="探索した。")
    )

    wiring.run_turn(PlayerId(1))

    rows = [
        json.loads(line)
        for line in (tmp_path / "prompt_dataset" / "calls.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [row["attempt_index"] for row in rows] == [0, 1]
    assert rows[1]["parent_attempt_id"] == rows[0]["llm_call_id"]
    (retry,) = _retries(runtime)
    assert (retry["truncated_llm_call_id"], retry["retry_llm_call_id"]) == (
        rows[0]["llm_call_id"],
        rows[1]["llm_call_id"],
    )


class TestReasonFirstTurn:
    """reason-first の 2 段の呼び出しでも、打ち切られた段を考えを止めて呼び直すことを保証する。"""

    @staticmethod
    def _wiring(client: _Client) -> tuple[_WorldLlmWiring, _GatedReasonFirstRuntime]:
        runtime = _GatedReasonFirstRuntime()
        wiring = _WorldLlmWiring(runtime=runtime, observation_buffer=runtime._obs_buffer, llm_client=client)
        wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = lambda player_id, arguments, runtime_context: (
            LlmCommandResultDto(success=True, message="探索した。")
        )
        for _ in range(4):
            wiring.tool_call_loop_guard.record_and_check(
                PlayerId(1), TOOL_NAME_SPOT_GRAPH_INTERACT, {"target_label": "湧水の口"}
            )
        return wiring, runtime

    @pytest.mark.parametrize(
        ("responses", "phase", "expected_effort"),
        [
            ([_Cut(), _ASSESS, _EXPLORE], "assess_phase", [None, "none", None]),
            ([_ASSESS, _Cut(), _EXPLORE], "action_phase", [None, None, "none"]),
        ],
    )
    def test_cut_off_phase_is_retried_without_reasoning(
        self, responses: list[Any], phase: str, expected_effort: list[str | None]
    ) -> None:
        """評価の段も行動の段も、打ち切られた段だけを考えを止めて 1 回呼び直し、ターンは行動まで進む。"""
        client = _Client(responses)
        wiring, runtime = self._wiring(client)

        result = wiring.run_turn(PlayerId(1))

        assert result.success is True
        assert [call["reasoning_effort"] for call in client.calls] == expected_effort
        (retry,) = _retries(runtime)
        assert (retry["phase"], retry["outcome"]) == (phase, "tool_call")


class TestReasonFirstAssessRetries:
    """評価の段は評価の再試行 (2 周目) を持つので、打ち切りの呼び直しと組み合わさっても回数と番号が崩れないことを保証する。"""

    @staticmethod
    def _wiring(client: _Client, tmp_path: Path) -> tuple[_WorldLlmWiring, _GatedReasonFirstRuntime]:
        runtime = _GatedReasonFirstRuntime()
        runtime.aux_being_resolver = _AuxBeingResolverStub()
        runtime.aux_being_default_world_id = WorldId(1)
        wiring = _WorldLlmWiring(
            runtime=runtime,
            observation_buffer=runtime._obs_buffer,
            llm_client=client,
            prompt_dataset_sink=PromptDatasetCaptureSink(run_dir=tmp_path, run_id="run-1924", run_metadata={}),
        )
        wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = lambda player_id, arguments, runtime_context: (
            LlmCommandResultDto(success=True, message="探索した。")
        )
        for _ in range(4):
            wiring.tool_call_loop_guard.record_and_check(
                PlayerId(1), TOOL_NAME_SPOT_GRAPH_INTERACT, {"target_label": "湧水の口"}
            )
        return wiring, runtime

    @staticmethod
    def _assess_attempts(tmp_path: Path) -> list[int]:
        rows = [
            json.loads(line)
            for line in (tmp_path / "prompt_dataset" / "calls.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        return [row["attempt_index"] for row in rows if row["phase"] == "assess_phase"]

    def test_second_round_is_not_retried_again(self, tmp_path: Path) -> None:
        """評価の 1 周目で呼び直しても評価が成立せず、2 周目もまた打ち切られたら、評価の段では 2 回目の呼び直しをしない。"""
        client = _Client([_Cut(), _Cut(), _Cut()])
        wiring, runtime = self._wiring(client, tmp_path)

        result = wiring.run_turn(PlayerId(1))

        assert result.success is False
        assert [call["reasoning_effort"] for call in client.calls] == [None, "none", None]
        assert len(_retries(runtime)) == 1
        assert self._assess_attempts(tmp_path) == [0, 1, 2]

    def test_retry_failing_with_an_exception_does_not_reuse_the_attempt_number(self, tmp_path: Path) -> None:
        """評価の 1 周目の呼び直しが例外で落ちても、2 周目の呼び出しは次の番号になり、もう呼び直さない。"""
        client = _Client([_Cut(), LlmApiCallException("down", error_code="LLM_API_CALL_FAILED"), _Cut()])
        wiring, runtime = self._wiring(client, tmp_path)

        wiring.run_turn(PlayerId(1))

        assert [call["reasoning_effort"] for call in client.calls] == [None, "none", None]
        assert self._assess_attempts(tmp_path) == [0, 2]
