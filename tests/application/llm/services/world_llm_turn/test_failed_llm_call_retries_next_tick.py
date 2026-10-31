"""LLM の呼び出しが失敗した人に、次の tick に手番を回し、続けて失敗したら上限で打ち切って trace に残すことを保証する (Issue #1595)。

`var/runs/mine_v1_005` では、95 秒の上限で止まった `litellm.Timeout` のあと、ミオは
T32 から T38 まで動かなかった。失敗した手番のあと、本人を起こす観測が届くか、
待ち時間のタイマーが切れるまで眠っていた。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import litellm
import pytest
from tests.support.trace_recorders import CollectingTraceRecorder

from ai_rpg_world.application.llm.services.world_llm_turn.turn_trigger import (
    MAX_CONSECUTIVE_LLM_FAILURES,
)
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring

_SCENARIO = Path(__file__).resolve().parents[5] / "data" / "scenarios" / "mine_village_v1.json"
_HARU = PlayerId(1)

_TIMEOUT = "timeout"
_NO_TOOL = "no_tool"
_WAIT = "wait"


class _ScriptedClient:
    """呼ばれた順に、時間切れ・ツールなし・wait を返す。台本が尽きたら wait を返す。"""

    def __init__(self, script: list[str]) -> None:
        self._script = list(script)
        self.calls = 0

    def invoke(self, messages: Any, tools: Any, tool_choice: str = "required", **kwargs: Any):
        self.calls += 1
        step = self._script.pop(0) if self._script else _WAIT
        if step == _TIMEOUT:
            raise litellm.Timeout(message="Request timed out", model="stub", llm_provider="openrouter")
        if step == _NO_TOOL:
            return None
        return {"name": "wait", "arguments": {"inner_thought": "様子を見る"}}


def _wiring(script: list[str]) -> tuple[_WorldLlmWiring, _ScriptedClient, CollectingTraceRecorder]:
    runtime = create_world_runtime(_SCENARIO)
    recorder = CollectingTraceRecorder()
    runtime.set_trace_recorder(recorder)
    client = _ScriptedClient(script)
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        llm_client=client,
    )
    return wiring, client, recorder


def _run_ticks(wiring: _WorldLlmWiring, n: int) -> None:
    """tick を進めずに手番の wave だけを n 回回す。観測で起こされる経路を混ぜない。"""
    for _ in range(n):
        wiring.llm_turn_trigger.run_scheduled_turns()


def _retry_events(recorder: CollectingTraceRecorder) -> list[dict[str, Any]]:
    return [e.payload for e in recorder.of_kind(TraceEventKind.LLM_FAILURE_RETRY)]


class TestFailedCallGetsTheNextTick:
    """呼び出しが失敗した人は、次の wave で手番が回ること。"""

    def test_timeout_puts_the_player_back_for_the_next_tick(self) -> None:
        """呼び出しが litellm.Timeout で失敗すると、その人は次の wave の pending に入り、次の wave でもう一度呼び出される。"""
        wiring, client, _ = _wiring([_TIMEOUT])
        wiring.llm_turn_trigger.schedule_turn(_HARU)

        _run_ticks(wiring, 2)

        assert client.calls == 2

    def test_successful_turn_does_not_put_the_player_back(self) -> None:
        """正の対照: 呼び出しが成功して wait を選んだ人は、次の wave の pending に入らない。"""
        wiring, client, _ = _wiring([_WAIT])
        wiring.llm_turn_trigger.schedule_turn(_HARU)

        _run_ticks(wiring, 2)

        assert client.calls == 1

    def test_no_tool_call_is_not_retried_by_this_rule(self) -> None:
        """呼び出しは成功したがツールを返さなかった手番は、失敗の再試行の対象にせず、trace にも残さない。"""
        wiring, client, recorder = _wiring([_NO_TOOL])
        wiring.llm_turn_trigger.schedule_turn(_HARU)

        _run_ticks(wiring, 2)

        assert client.calls == 1
        assert _retry_events(recorder) == []

    def test_retry_is_recorded_with_the_streak(self) -> None:
        """次の wave に回した失敗は、連続の回数・上限・回したことを trace の llm_failure_retry に 1 件残す。"""
        wiring, _, recorder = _wiring([_TIMEOUT])
        wiring.llm_turn_trigger.schedule_turn(_HARU)

        _run_ticks(wiring, 1)

        assert _retry_events(recorder) == [
            {
                "consecutive_failures": 1,
                "max_consecutive_failures": MAX_CONSECUTIVE_LLM_FAILURES,
                "rescheduled": True,
                "error_code": "LLM_API_FAILED",
            }
        ]


class TestConsecutiveFailuresStopAtTheLimit:
    """同じ人が続けて失敗するときは、上限で次の wave に回すのをやめ、trace に残すこと。"""

    def test_limit_is_three(self) -> None:
        """上限は 3 回。mine_v1_005 の失敗率 4/118 では、偶然 3 回続く確率は 1/25,000 程度で、続くなら一時的な遅れではない。"""
        assert MAX_CONSECUTIVE_LLM_FAILURES == 3

    def test_third_consecutive_failure_is_not_rescheduled(self) -> None:
        """3 回続けて失敗すると、3 回目のあとは次の wave に回さない。4 回目の呼び出しは起きない。"""
        wiring, client, _ = _wiring([_TIMEOUT] * 5)
        wiring.llm_turn_trigger.schedule_turn(_HARU)

        _run_ticks(wiring, 5)

        assert client.calls == MAX_CONSECUTIVE_LLM_FAILURES

    def test_reaching_the_limit_is_recorded(self) -> None:
        """上限に達した失敗は、rescheduled=False で trace に残る。それまでの失敗は rescheduled=True。"""
        wiring, _, recorder = _wiring([_TIMEOUT] * 5)
        wiring.llm_turn_trigger.schedule_turn(_HARU)

        _run_ticks(wiring, 5)

        assert [(e["consecutive_failures"], e["rescheduled"]) for e in _retry_events(recorder)] == [
            (1, True),
            (2, True),
            (3, False),
        ]

    def test_success_between_failures_resets_the_streak(self) -> None:
        """失敗・失敗・成功・失敗・失敗の順では、成功で連続が切れるので、最後の失敗も次の wave に回る。"""
        wiring, client, recorder = _wiring([_TIMEOUT, _TIMEOUT, _WAIT, _TIMEOUT, _TIMEOUT])
        wiring.llm_turn_trigger.schedule_turn(_HARU)

        _run_ticks(wiring, 3)
        wiring.llm_turn_trigger.schedule_turn(_HARU)
        _run_ticks(wiring, 3)

        assert client.calls == 6
        assert [e["consecutive_failures"] for e in _retry_events(recorder)] == [1, 2, 1, 2]

    def test_streak_starts_over_after_the_limit(self) -> None:
        """上限で打ち切ったあと、観測などで起こされて再び失敗したら、連続を 1 から数え直して次の wave に回す。"""
        wiring, _, recorder = _wiring([_TIMEOUT] * 4)
        wiring.llm_turn_trigger.schedule_turn(_HARU)
        _run_ticks(wiring, 3)

        wiring.llm_turn_trigger.schedule_turn(_HARU)
        _run_ticks(wiring, 1)

        assert _retry_events(recorder)[-1]["consecutive_failures"] == 1
        assert _retry_events(recorder)[-1]["rescheduled"] is True


@pytest.mark.parametrize("workers", [2])
def test_parallel_wave_also_retries_the_failed_player(workers: int) -> None:
    """並列の経路 (Phase A を同時に回す) で 2 人のうち 1 人が時間切れになると、その 1 人だけが次の wave でもう一度呼び出される。"""
    wiring, client, recorder = _wiring([_TIMEOUT, _WAIT, _WAIT])
    wiring.runtime._runtime_config = _with_workers(wiring.runtime._runtime_config, workers)
    wiring.llm_turn_trigger.schedule_turn(_HARU)
    wiring.llm_turn_trigger.schedule_turn(PlayerId(2))

    _run_ticks(wiring, 2)

    assert client.calls == 3
    retried = [e.player_id for e in recorder.of_kind(TraceEventKind.LLM_FAILURE_RETRY)]
    assert len(retried) == 1 and retried[0] in (1, 2)


def _with_workers(cfg: Any, workers: int) -> Any:
    from dataclasses import replace

    return replace(cfg, llm_turn_parallel_workers=workers)
