"""案A (band-gated thinking): world_runtime を通した実配線を固定する。

停滞 (stalled/misaligned) の reflect 注入が熟考ラッチを arm し、band==strong の
局面での次行動判断 (``resolve_turn_reasoning_effort``) が effort="low" を返して
``AGENT_REASONING_ENGAGED`` trace を出すこと、および前提 flag 欠如時に
``create_world_runtime`` が fail-fast することを確認する。LLM は呼ばない。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "single_relic_contention_demo.json"
)


def _enable_prereqs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
    monkeypatch.setenv("SEMANTIC_SEARCH_ENABLED", "1")
    monkeypatch.setenv("BELIEF_CONSOLIDATION_ENABLED", "1")
    monkeypatch.setenv("GOAL_REFLECT_ENABLED", "1")
    monkeypatch.setenv("STAGNATION_PRESSURE_ENABLED", "1")


def _being_id(runtime, player_id: int):
    return runtime._aux_being_resolver.resolve_being_id(
        runtime._aux_being_default_world_id, PlayerId(player_id)
    )


class _CapturingRecorder:
    def __init__(self) -> None:
        self.events: list = []

    def record(self, kind, **payload):
        self.events.append((kind, payload))

    def close(self) -> None:
        pass


class TestStagnationReasoningFailFast:
    """前提 flag が欠けたまま案A を ON にすると起動時に落ちる (静かな失敗を弾く)。"""

    def test_pressure_off_で_reasoning_on_は_起動時に落ちる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.setenv("BELIEF_CONSOLIDATION_ENABLED", "1")
        monkeypatch.setenv("GOAL_REFLECT_ENABLED", "1")
        monkeypatch.delenv("STAGNATION_PRESSURE_ENABLED", raising=False)
        monkeypatch.setenv("STAGNATION_REASONING_ENABLED", "1")
        with pytest.raises(ValueError, match="STAGNATION_PRESSURE_ENABLED"):
            create_world_runtime(_SCENARIO_PATH)

    def test_goal_reflect_off_で_reasoning_on_は_起動時に落ちる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_EPISODIC_ENABLED", "1")
        monkeypatch.setenv("BELIEF_CONSOLIDATION_ENABLED", "1")
        monkeypatch.delenv("GOAL_REFLECT_ENABLED", raising=False)
        # pressure を ON にして「pressure 欠如」分岐を回避し、reflect 欠如分岐に
        # 到達させる。案A の fail-fast は coordinator 構築より前 (flag 解決層) で
        # 走るので、reflect を必要とする案A 側の check が先に立つ。
        monkeypatch.setenv("STAGNATION_PRESSURE_ENABLED", "1")
        monkeypatch.setenv("STAGNATION_REASONING_ENABLED", "1")
        with pytest.raises(ValueError, match="GOAL_REFLECT_ENABLED"):
            create_world_runtime(_SCENARIO_PATH)


class TestStagnationReasoningEffortDecision:
    """reflect 注入 → ラッチ武装 → band==strong で effort=low + trace。"""

    def test_stalled注入後_band_strong_で_effort_low_と_trace(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_prereqs(monkeypatch)
        monkeypatch.setenv("STAGNATION_REASONING_ENABLED", "1")
        runtime = create_world_runtime(_SCENARIO_PATH)
        recorder = _CapturingRecorder()
        runtime.set_trace_recorder(recorder)
        being_id = _being_id(runtime, 1)
        assert being_id is not None
        for _ in range(3):  # band を strong (>=3) にする
            runtime._stagnation_pressure_store.increment_by_being(being_id)
        # 停滞の気づきが注入された = ラッチ武装
        runtime._emit_reflect_observation(PlayerId(1), "同じ場所を空回りしている", "stalled")

        effort = runtime.resolve_turn_reasoning_effort(PlayerId(1))
        assert effort == "low"
        engaged = [
            p for (k, p) in recorder.events if k == TraceEventKind.AGENT_REASONING_ENGAGED
        ]
        assert len(engaged) == 1
        assert engaged[0]["band"] == "strong"
        assert engaged[0]["effort"] == "low"
        assert engaged[0]["player_id"] == 1
        assert engaged[0]["trigger"] == "fresh_reflect"

    def test_consume_は一発_二度目は_None(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """武装は 1 行動で消費される。次行動 (再武装なし) では焚かない。"""
        _enable_prereqs(monkeypatch)
        monkeypatch.setenv("STAGNATION_REASONING_ENABLED", "1")
        runtime = create_world_runtime(_SCENARIO_PATH)
        being_id = _being_id(runtime, 1)
        for _ in range(3):
            runtime._stagnation_pressure_store.increment_by_being(being_id)
        runtime._emit_reflect_observation(PlayerId(1), "停滞", "stalled")
        assert runtime.resolve_turn_reasoning_effort(PlayerId(1)) == "low"
        assert runtime.resolve_turn_reasoning_effort(PlayerId(1)) is None

    def test_band_light_では_注入後でも_None(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """band が strong 未満なら reflect 注入直後でも熟考しない。"""
        _enable_prereqs(monkeypatch)
        monkeypatch.setenv("STAGNATION_REASONING_ENABLED", "1")
        runtime = create_world_runtime(_SCENARIO_PATH)
        being_id = _being_id(runtime, 1)
        runtime._stagnation_pressure_store.increment_by_being(being_id)  # count=1 (light)
        runtime._emit_reflect_observation(PlayerId(1), "停滞", "stalled")
        assert runtime.resolve_turn_reasoning_effort(PlayerId(1)) is None

    def test_achieved注入では武装しない(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """achieved (前進) の気づきでは熟考ラッチを立てない。"""
        _enable_prereqs(monkeypatch)
        monkeypatch.setenv("STAGNATION_REASONING_ENABLED", "1")
        runtime = create_world_runtime(_SCENARIO_PATH)
        being_id = _being_id(runtime, 1)
        for _ in range(3):
            runtime._stagnation_pressure_store.increment_by_being(being_id)
        runtime._emit_reflect_observation(PlayerId(1), "もう果たした", "achieved")
        assert runtime.resolve_turn_reasoning_effort(PlayerId(1)) is None


class TestStagnationReasoningOffByDefault:
    """flag OFF のとき、ラッチは構築されず effort は常に None (既存挙動不変)。"""

    def test_flag_off_なら_latch_none_で_effort_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_prereqs(monkeypatch)
        monkeypatch.delenv("STAGNATION_REASONING_ENABLED", raising=False)
        runtime = create_world_runtime(_SCENARIO_PATH)
        assert runtime._stagnation_reasoning_latch is None
        being_id = _being_id(runtime, 1)
        for _ in range(3):
            runtime._stagnation_pressure_store.increment_by_being(being_id)
        runtime._emit_reflect_observation(PlayerId(1), "停滞", "stalled")
        assert runtime.resolve_turn_reasoning_effort(PlayerId(1)) is None
