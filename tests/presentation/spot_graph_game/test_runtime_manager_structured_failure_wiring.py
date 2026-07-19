"""U6 (STRUCTURED_FAILURE + salience): ``_WorldLlmWiring`` (runtime_manager.py)
が ``tool_call_loop_guard.record_and_check`` の戻り値
(``CrossTickFailureTrigger``) を受けて、being_id を解決し
``structured_failure_transcriber.record_if_triggered`` を呼ぶ配線を検証する。

loop_guard 自身は being_id を解決できない (Being 文脈を持たない service の
ため) ので、この配線が「発火 → 転記」の唯一の橋渡しになる。transcriber が
None (SALIENCE_STRUCTURED_FAILURE_ENABLED が OFF) のときは no-op であることも
合わせて確認する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.tool_call_loop_guard import (
    CrossTickFailureTrigger,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId


@pytest.fixture
def clean_runtime_env(monkeypatch):
    monkeypatch.delenv("LLM_EPISODIC_ENABLED", raising=False)
    yield


class _TriggerLoopGuardSpy:
    """record_and_check が常に固定の CrossTickFailureTrigger を返すスタブ。"""

    def __init__(self, events: list[str], trigger: CrossTickFailureTrigger | None) -> None:
        self.events = events
        self.trigger = trigger

    def record_and_check(self, player_id, tool_name, arguments, **kwargs):
        self.events.append("loop_guard")
        return self.trigger


class _AuxResolverStub:
    def __init__(self, being_id: BeingId | None) -> None:
        self._being_id = being_id
        self.calls: list[tuple[WorldId, PlayerId]] = []

    def resolve_being_id(self, world_id: WorldId, player_id: PlayerId) -> BeingId | None:
        self.calls.append((world_id, player_id))
        return self._being_id


class _StructuredFailureTranscriberSpy:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def record_if_triggered(self, being_id: BeingId, **kwargs):
        self.calls.append({"being_id": being_id, **kwargs})
        return None


def _make_wiring_and_runtime(events, *, trigger, transcriber, resolver):
    from tests.integration.test_world_runtime_current_runtime_contract import (
        _ContractRuntime,
        _wiring_for_contract_runtime,
    )

    runtime = _ContractRuntime(events)
    runtime.aux_being_resolver = resolver
    runtime.aux_being_default_world_id = WorldId(1)
    runtime._structured_failure_transcriber = transcriber
    wiring = _wiring_for_contract_runtime(runtime)
    wiring.tool_call_loop_guard = _TriggerLoopGuardSpy(events, trigger)
    return wiring


def _run_explore(wiring, player_id) -> LlmCommandResultDto:
    from tests.integration.test_world_runtime_current_runtime_contract import _phase_a

    def _handler(pid, args, ctx):
        return LlmCommandResultDto(success=True, message="ok")

    wiring._tool_handlers[TOOL_NAME_SPOT_GRAPH_EXPLORE] = _handler
    return wiring.run_phase_b(
        _phase_a(
            player_id,
            tool_call={"name": TOOL_NAME_SPOT_GRAPH_EXPLORE, "arguments": {}},
        )
    )


class TestStructuredFailureWiring:
    def test_calls_trigger_transcriber_wired_being(
        self, clean_runtime_env
    ) -> None:
        """trigger かつ transcriber配線済 なら being解決して転記を呼ぶ。"""
        events: list[str] = []
        player_id = PlayerId(1)
        being_id = BeingId("being-1")
        trigger = CrossTickFailureTrigger(
            tool_name=TOOL_NAME_SPOT_GRAPH_EXPLORE,
            error_code="SOME_ERROR",
            count=3,
            window=20,
        )
        resolver = _AuxResolverStub(being_id)
        transcriber = _StructuredFailureTranscriberSpy()
        wiring = _make_wiring_and_runtime(
            events, trigger=trigger, transcriber=transcriber, resolver=resolver
        )

        _run_explore(wiring, player_id)

        assert resolver.calls == [(WorldId(1), player_id)]
        assert transcriber.calls == [
            {
                "being_id": being_id,
                "tool_name": TOOL_NAME_SPOT_GRAPH_EXPLORE,
                "error_code": "SOME_ERROR",
                "count": 3,
            }
        ]

    def test_transcriber_unwired_flag_off_op(self, clean_runtime_env) -> None:
        """SALIENCE_STRUCTURED_FAILURE_ENABLED が OFF のとき
        (= _structured_failure_transcriber が None) は being 解決すら
        試みず no-op になる。"""
        events: list[str] = []
        player_id = PlayerId(1)
        trigger = CrossTickFailureTrigger(
            tool_name=TOOL_NAME_SPOT_GRAPH_EXPLORE,
            error_code="SOME_ERROR",
            count=3,
            window=20,
        )
        resolver = _AuxResolverStub(BeingId("being-1"))
        wiring = _make_wiring_and_runtime(
            events, trigger=trigger, transcriber=None, resolver=resolver
        )

        _run_explore(wiring, player_id)

        assert resolver.calls == []

    def test_trigger_none_transcriber_does_not_call(self, clean_runtime_env) -> None:
        """cross_tick_failure が未発火 (trigger=None) のときは、transcriber
        配線済みでも呼ばれない。"""
        events: list[str] = []
        player_id = PlayerId(1)
        transcriber = _StructuredFailureTranscriberSpy()
        resolver = _AuxResolverStub(BeingId("being-1"))
        wiring = _make_wiring_and_runtime(
            events, trigger=None, transcriber=transcriber, resolver=resolver
        )

        _run_explore(wiring, player_id)

        assert transcriber.calls == []

    def test_being_resolution_failure_does_not_call(self, clean_runtime_env) -> None:
        """resolver が None を返す (Being 未 attach) 場合、転記をスキップする。"""
        events: list[str] = []
        player_id = PlayerId(1)
        trigger = CrossTickFailureTrigger(
            tool_name=TOOL_NAME_SPOT_GRAPH_EXPLORE,
            error_code="SOME_ERROR",
            count=3,
            window=20,
        )
        resolver = _AuxResolverStub(None)
        transcriber = _StructuredFailureTranscriberSpy()
        wiring = _make_wiring_and_runtime(
            events, trigger=trigger, transcriber=transcriber, resolver=resolver
        )

        _run_explore(wiring, player_id)

        assert transcriber.calls == []
