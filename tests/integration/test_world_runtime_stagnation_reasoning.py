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

    def test_episodic_off_で_reasoning_on_は_起動時に落ちる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """敵対的レビュー HIGH 1: LLM_EPISODIC_ENABLED を立て忘れたまま案A を ON に
        すると、従来は fail-fast も含む episodic ブロック丸ごとが skip され、熟考が
        一生焚かれない静かな失敗になっていた。episodic を前提にする案A の flag が
        ON なら、親 gate より前で LLM_EPISODIC_ENABLED を要求して落とす。"""
        monkeypatch.delenv("LLM_EPISODIC_ENABLED", raising=False)
        monkeypatch.setenv("BELIEF_CONSOLIDATION_ENABLED", "1")
        monkeypatch.setenv("GOAL_REFLECT_ENABLED", "1")
        monkeypatch.setenv("STAGNATION_PRESSURE_ENABLED", "1")
        monkeypatch.setenv("STAGNATION_REASONING_ENABLED", "1")
        with pytest.raises(ValueError, match="LLM_EPISODIC_ENABLED"):
            create_world_runtime(_SCENARIO_PATH)

    def test_episodic_off_で_pressure_on_は_起動時に落ちる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """HIGH 1 (同じ親 gate 穴の共有): STAGNATION_PRESSURE も episodic 前提なので、
        episodic OFF のまま ON にすると起動時に落ちる。"""
        monkeypatch.delenv("LLM_EPISODIC_ENABLED", raising=False)
        monkeypatch.setenv("BELIEF_CONSOLIDATION_ENABLED", "1")
        monkeypatch.setenv("GOAL_REFLECT_ENABLED", "1")
        monkeypatch.setenv("STAGNATION_PRESSURE_ENABLED", "1")
        monkeypatch.delenv("STAGNATION_REASONING_ENABLED", raising=False)
        with pytest.raises(ValueError, match="LLM_EPISODIC_ENABLED"):
            create_world_runtime(_SCENARIO_PATH)

    def test_episodic_off_で_goal_stagnation_evidence_on_は_起動時に落ちる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """HIGH 1 (同じ親 gate 穴の共有): GOAL_STAGNATION_EVIDENCE も episodic 前提。"""
        monkeypatch.delenv("LLM_EPISODIC_ENABLED", raising=False)
        monkeypatch.setenv("BELIEF_CONSOLIDATION_ENABLED", "1")
        monkeypatch.setenv("GOAL_REFLECT_ENABLED", "1")
        monkeypatch.setenv("GOAL_STAGNATION_EVIDENCE_ENABLED", "1")
        with pytest.raises(ValueError, match="LLM_EPISODIC_ENABLED"):
            create_world_runtime(_SCENARIO_PATH)


class TestStagnationReasoningEffortDecision:
    """reflect 注入 → ラッチ武装 → band==strong で effort=low。決定 (resolve) は
    ラッチを消費せず trace も出さない。実際の消費と AGENT_REASONING_ENGAGED trace
    は invoke 成功後の commit で起きる (敵対的レビュー HIGH 2)。"""

    def test_resolveは決定だけしラッチも消費せずtraceも出さない(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """band==strong で resolve は effort=low を返すが、ラッチはまだ armed のまま
        で trace も出ない (invoke 前に副作用を確定させない)。"""
        _enable_prereqs(monkeypatch)
        monkeypatch.setenv("STAGNATION_REASONING_ENABLED", "1")
        runtime = create_world_runtime(_SCENARIO_PATH)
        recorder = _CapturingRecorder()
        runtime.set_trace_recorder(recorder)
        being_id = _being_id(runtime, 1)
        assert being_id is not None
        for _ in range(3):  # band を strong (>=3) にする
            runtime._stagnation_pressure_store.increment_by_being(being_id)
        runtime._emit_reflect_observation(PlayerId(1), "同じ場所を空回りしている", "stalled")

        effort = runtime.resolve_turn_reasoning_effort(PlayerId(1))
        assert effort == "low"
        # まだ trace は出ない
        engaged = [
            p for (k, p) in recorder.events if k == TraceEventKind.AGENT_REASONING_ENGAGED
        ]
        assert engaged == []
        # ラッチも消費されていない (invoke 失敗時に次行動で再挑戦できる)
        assert runtime._stagnation_reasoning_latch.is_armed(PlayerId(1)) is True

    def test_commitでラッチ消費とtrace_engagedが起きる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """invoke 成功後の commit で初めてラッチが落ち、AGENT_REASONING_ENGAGED が出る。"""
        _enable_prereqs(monkeypatch)
        monkeypatch.setenv("STAGNATION_REASONING_ENABLED", "1")
        runtime = create_world_runtime(_SCENARIO_PATH)
        recorder = _CapturingRecorder()
        runtime.set_trace_recorder(recorder)
        being_id = _being_id(runtime, 1)
        for _ in range(3):
            runtime._stagnation_pressure_store.increment_by_being(being_id)
        runtime._emit_reflect_observation(PlayerId(1), "停滞", "stalled")
        effort = runtime.resolve_turn_reasoning_effort(PlayerId(1))
        assert effort == "low"

        runtime.commit_turn_reasoning_engaged(PlayerId(1), effort)

        engaged = [
            p for (k, p) in recorder.events if k == TraceEventKind.AGENT_REASONING_ENGAGED
        ]
        assert len(engaged) == 1
        assert engaged[0]["band"] == "strong"
        assert engaged[0]["effort"] == "low"
        assert engaged[0]["player_id"] == 1
        assert engaged[0]["trigger"] == "fresh_reflect"
        # commit 後はラッチが落ちる
        assert runtime._stagnation_reasoning_latch.is_armed(PlayerId(1)) is False

    def test_commitしなければ次行動で再挑戦できる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """invoke 失敗 (= commit されない) を模し、ラッチが armed のまま残ることで
        次行動でも resolve が effort=low を返す (熟考機会を焼失させない)。"""
        _enable_prereqs(monkeypatch)
        monkeypatch.setenv("STAGNATION_REASONING_ENABLED", "1")
        runtime = create_world_runtime(_SCENARIO_PATH)
        being_id = _being_id(runtime, 1)
        for _ in range(3):
            runtime._stagnation_pressure_store.increment_by_being(being_id)
        runtime._emit_reflect_observation(PlayerId(1), "停滞", "stalled")
        # commit を挟まず 2 回 resolve → どちらも low (再挑戦できる)
        assert runtime.resolve_turn_reasoning_effort(PlayerId(1)) == "low"
        assert runtime.resolve_turn_reasoning_effort(PlayerId(1)) == "low"

    def test_band_light_では_注入後でも_None_でラッチは畳まれる(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """band が strong 未満なら熟考しない。かつ古いラッチはここで畳んで残さない。"""
        _enable_prereqs(monkeypatch)
        monkeypatch.setenv("STAGNATION_REASONING_ENABLED", "1")
        runtime = create_world_runtime(_SCENARIO_PATH)
        being_id = _being_id(runtime, 1)
        runtime._stagnation_pressure_store.increment_by_being(being_id)  # count=1 (light)
        runtime._emit_reflect_observation(PlayerId(1), "停滞", "stalled")
        assert runtime.resolve_turn_reasoning_effort(PlayerId(1)) is None
        # 焚かない場合は古いフラグを残さない
        assert runtime._stagnation_reasoning_latch.is_armed(PlayerId(1)) is False

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

    def test_commitはラッチ未武装なら_traceを出さない(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """防御: ラッチが立っていない (consume False) 状態で commit を呼んでも、
        AGENT_REASONING_ENGAGED trace は出さない。二重 commit / 経路不整合で
        「熟考していないのに engaged」の偽陽性を出さないためのガード。"""
        _enable_prereqs(monkeypatch)
        monkeypatch.setenv("STAGNATION_REASONING_ENABLED", "1")
        runtime = create_world_runtime(_SCENARIO_PATH)
        recorder = _CapturingRecorder()
        runtime.set_trace_recorder(recorder)
        # arm せずにいきなり commit
        runtime.commit_turn_reasoning_engaged(PlayerId(1), "low")
        engaged = [
            p for (k, p) in recorder.events if k == TraceEventKind.AGENT_REASONING_ENGAGED
        ]
        assert engaged == []


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
