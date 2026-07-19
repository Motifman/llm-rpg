"""実験設定を明示して world_runtime 系テストを組むための helper。"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)


def runtime_config(**overrides: Any) -> ResolvedLlmRuntimeConfig:
    """テスト用既定値に差分だけを重ねた解決済み設定を返す。"""
    return ResolvedLlmRuntimeConfig.for_tests(**overrides)


def episodic_config(**overrides: Any) -> ResolvedLlmRuntimeConfig:
    """episodic stack を組むテストの最小設定。"""
    values: dict[str, Any] = {"episodic_enabled": True}
    values.update(overrides)
    return runtime_config(**values)


def belief_consolidation_config(**overrides: Any) -> ResolvedLlmRuntimeConfig:
    """belief consolidation coordinator まで組むテストの前提設定。"""
    values: dict[str, Any] = {
        "episodic_enabled": True,
        "semantic_search_enabled": True,
        "belief_evidence_enabled": True,
        "belief_consolidation_enabled": True,
    }
    values.update(overrides)
    return runtime_config(**values)
