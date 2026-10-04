"""ゲームの runtime が、予期の清算が有効なときだけ、信念をまとめる LLM に外れの時系列の読み方を渡す配線を保証する (#1509)。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime

_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)


def _consolidation_system_prompt(*, expectation_settlement_enabled: bool) -> str:
    config = ResolvedLlmRuntimeConfig.for_tests(
        episodic_enabled=True,
        semantic_search_enabled=True,
        belief_consolidation_enabled=True,
        typed_judgment_provider="stub",
        expectation_settlement_enabled=expectation_settlement_enabled,
    )
    runtime = create_world_runtime(_SCENARIO, config=config)
    coordinator = runtime._episodic_stack.belief_consolidation_coordinator
    assert coordinator is not None
    return coordinator._system_prompt


@pytest.mark.parametrize(("enabled", "present"), [(True, True), (False, False)])
def test_what_happened_section_follows_expectation_settlement(
    enabled: bool, present: bool
) -> None:
    """予期の清算が有効な run では信念をまとめる LLM のシステムプロンプトに外れの時系列の節が入り、無効な run では入らない。"""
    prompt = _consolidation_system_prompt(expectation_settlement_enabled=enabled)

    assert ("【外れた予期から学ぶ】" in prompt) is present
