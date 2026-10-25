"""実験設定を明示して world_runtime 系テストを組むための helper。"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)


def runtime_config(**overrides: Any) -> ResolvedLlmRuntimeConfig:
    """テスト用既定値に差分だけを重ねた解決済み設定を返す。"""
    return ResolvedLlmRuntimeConfig.for_tests(**overrides)
