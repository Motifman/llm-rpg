"""ゲームの runtime が、外れの材料に時系列が付く run でだけ信念をまとめる LLM に読み方を渡し、受け取る側に時系列の上限を渡す配線を保証する (#1509)。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.being.expectation.belief_material import (
    MAX_WHAT_HAPPENED_CHARS,
    ExpectationBeliefMaterialReceiver,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)


def _runtime(*, expectation_settlement_enabled: bool, belief_evidence_enabled: bool) -> Any:
    config = ResolvedLlmRuntimeConfig.for_tests(
        episodic_enabled=True,
        semantic_search_enabled=True,
        belief_consolidation_enabled=True,
        belief_evidence_enabled=belief_evidence_enabled,
        typed_judgment_provider="stub",
        expectation_settlement_enabled=expectation_settlement_enabled,
    )
    return create_world_runtime(_SCENARIO, config=config)


def _consolidation_system_prompt(runtime: Any) -> str:
    coordinator = runtime._episodic_stack.belief_consolidation_coordinator
    assert coordinator is not None
    return coordinator._system_prompt


@pytest.mark.parametrize(
    ("settlement", "evidence", "present"),
    [(True, True, True), (False, True, False), (True, False, False)],
    ids=["both_on", "settlement_off", "belief_evidence_off"],
)
def test_what_happened_section_needs_settlement_and_belief_evidence(
    settlement: bool, evidence: bool, present: bool
) -> None:
    """予期の清算と信念の証拠の両方が有効な run だけ、信念をまとめる LLM のシステムプロンプトに外れの時系列の節が入る。どちらかが無効なら材料に時系列が付かないので入らない。"""
    runtime = _runtime(expectation_settlement_enabled=settlement, belief_evidence_enabled=evidence)

    prompt = _consolidation_system_prompt(runtime)

    assert ("【外れた予期から学ぶ】" in prompt) is present


def test_runtime_receiver_uses_the_production_limit() -> None:
    """runtime が登録する信念の材料の受け取る側は、時系列の上限に MAX_WHAT_HAPPENED_CHARS を使う。"""
    runtime = _runtime(expectation_settlement_enabled=True, belief_evidence_enabled=True)

    (receiver,) = [
        r
        for r in runtime._expectation_dispatcher._receivers
        if isinstance(r, ExpectationBeliefMaterialReceiver)
    ]

    assert receiver._max_what_happened_chars == MAX_WHAT_HAPPENED_CHARS
