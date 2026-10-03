"""信念を作る前の判断が profile から固着 coordinator まで届くことを保証する (#1453)。

配線はキーワード引数の受け渡しで繋がっているので、途中で取りこぼすと gate が
組まれないまま run が進む。LLM と Jev は呼ばない (stub)。
"""

from __future__ import annotations

from pathlib import Path

from ai_rpg_world.application.llm.services.belief_create_gate import BeliefCreateGate
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from tests.runtime_config_helpers import belief_consolidation_config

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "forbidden_library_demo.json"
)


class TestWorldRuntimeBeliefCreateGateWiring:
    """gate の有無と設定値が coordinator に届くことを保証する。"""

    def test_an_enabled_gate_reaches_the_coordinator_with_its_settings(self) -> None:
        """有効にすると coordinator に gate が組まれ、K と閾値は profile の値になる。"""
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=belief_consolidation_config(
                typed_judgment_provider="stub",
                belief_create_gate_enabled=True,
                belief_candidate_top_k=4,
                belief_create_gate_min_confidence=0.7,
            ),
        )

        coordinator = runtime._episodic_stack.belief_consolidation_coordinator
        gate = coordinator._create_gate
        assert isinstance(gate, BeliefCreateGate)
        assert gate._top_k == 4
        assert gate._min_confidence == 0.7

    def test_the_gate_is_absent_unless_enabled(self) -> None:
        """有効にしなければ、判断の provider があっても gate は組まれない。"""
        runtime = create_world_runtime(
            _SCENARIO_PATH,
            config=belief_consolidation_config(typed_judgment_provider="stub"),
        )

        coordinator = runtime._episodic_stack.belief_consolidation_coordinator
        assert coordinator._create_gate is None
