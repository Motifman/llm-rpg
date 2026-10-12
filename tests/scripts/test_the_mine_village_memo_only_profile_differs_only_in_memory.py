"""廃坑の山村のメモだけの profile が、全部入りの profile と記憶の部品だけで違っている。

メモだけで記憶が足りるかを全部入りと比べる (#1587)。thinking や出力の上限、
繰り返しの理由を問う判断のような記憶ではない設定が黙ってずれると、行動の違いを
記憶のせいと読めなくなる。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.run_scenario_experiment import (  # noqa: E402
    _runtime_config_mapping_from_source,
)

_PROFILES = _ROOT / "data" / "experiment_profiles"

_FULL = "memory_jev_mine_v1_v41_thinking_capped"
_MEMO_ONLY = "memory_jev_mine_v1_v41_thinking_capped_memo_only"

_MEMORY_PARTS_TURNED_OFF = frozenset({
    "BELIEF_ATTRIBUTION_ENABLED",
    "BELIEF_CONSOLIDATION_ENABLED",
    "BELIEF_CREATE_GATE_ENABLED",
    "BELIEF_EVIDENCE_ENABLED",
    "EPISODIC_RECALL_ENABLED",
    "ERROR_DRIVEN_REINTERPRETATION_ENABLED",
    "ERROR_GATED_ENCODING_ENABLED",
    "EXPECTATION_ARGUMENT_ENABLED",
    "EXPECTATION_SETTLEMENT_ENABLED",
    "GOAL_REFLECT_ENABLED",
    "GOAL_REVISION_ENABLED",
    "GOAL_STAGNATION_EVIDENCE_ENABLED",
    "GOAL_STORE_ENABLED",
    "LLM_AFTERGLOW_ENABLED",
    "LLM_EPISODIC_ENABLED",
    "LLM_EPISODIC_RECALL_HABITUATION_ENABLED",
    "LLM_EPISODIC_RECALL_SLOT_ENABLED",
    "LLM_EPISODIC_SUBJECTIVE_ENABLED",
    "MEMO_DISTILL_ENABLED",
    "PENDING_PREDICTION_ENABLED",
    "PREDICTION_CONTEXT_ID_ENABLED",
    "RECALL_HIT_BOOST_ENABLED",
    "SEMANTIC_LLM_GIST_ENABLED",
    "SITUATION_BELIEF_RECALL_ENABLED",
    "STAGNATION_PRESSURE_ENABLED",
    "STAGNATION_REASONING_ENABLED",
    "TYPED_JUDGMENT_GOAL_HINT_ENABLED",
    "UNCONSCIOUS_CONTEXT_ENABLED",
})


def _load(name: str) -> dict:
    return json.loads((_PROFILES / f"{name}.json").read_text(encoding="utf-8"))


class TestTheMemoOnlyProfileTurnsOffOnlyMemoryParts:
    """メモだけの profile と全部入りの差は、止めた記憶の部品だけ。"""

    def test_differences_are_exactly_the_memory_parts(self) -> None:
        """runtime_config の差は、止めた記憶の部品と、【関連する学び】の件数 (SEMANTIC_PASSIVE_TOP_K) だけ。"""
        memo_only = _load(_MEMO_ONLY)["runtime_config"]
        full = _load(_FULL)["runtime_config"]

        differing = {
            key for key in set(memo_only) | set(full) if memo_only.get(key) != full.get(key)
        }

        assert differing == _MEMORY_PARTS_TURNED_OFF | {"SEMANTIC_PASSIVE_TOP_K"}

    def test_memory_parts_are_off_and_semantic_recall_shows_nothing(self) -> None:
        """止めた記憶の部品はすべて false で、【関連する学び】は 0 件。"""
        memo_only = _load(_MEMO_ONLY)["runtime_config"]

        turned_on = {key for key in _MEMORY_PARTS_TURNED_OFF if memo_only[key] is not False}

        assert turned_on == set()
        assert memo_only["SEMANTIC_PASSIVE_TOP_K"] == 0

    def test_memo_and_short_term_summary_stay_on(self) -> None:
        """メモのツールと短期記憶の要約は残っている。"""
        memo_only = _load(_MEMO_ONLY)["runtime_config"]

        assert memo_only["MEMO_TOOLS_ENABLED"] is True
        assert memo_only["SHORT_TERM_MEMORY_KIND"] == "rolling_summary"

    def test_world_and_run_length_are_the_same(self) -> None:
        """世界、run の長さ、snapshot の保存は全部入りと同じ。"""
        memo_only = _load(_MEMO_ONLY)
        full = _load(_FULL)

        differing = {
            key for key in set(memo_only) | set(full) if memo_only.get(key) != full.get(key)
        }

        assert differing == {"profile", "description", "runtime_config"}

    def test_profile_resolves_with_memory_off_and_memo_on(self) -> None:
        """make experiment と同じ経路で解決すると起動時の検査に通り、エピソードは止まり、メモは残り、【関連する学び】は 0 件になる。"""
        memo_only = _load(_MEMO_ONLY)

        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values=_runtime_config_mapping_from_source(memo_only)
        )

        assert cfg.episodic_enabled is False
        assert cfg.memo_tools_enabled is True
        assert cfg.semantic_passive_top_k == 0
