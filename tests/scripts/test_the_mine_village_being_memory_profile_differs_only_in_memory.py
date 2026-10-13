"""廃坑の山村の新しい記憶の profile が、古い記憶の部品を止め、新しい記憶だけを入れている。

新しい記憶 (#1621) を全部入りの run (mine_v1_006) と比べる。比べた古い profile は
#1631 で退役させたので、止めた部品と入れた部品をこの profile の上で直接見張る。
古い部品が黙って入ると、行動の違いを新しい記憶のせいと読めなくなる。
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

_BEING_MEMORY = "memory_jev_mine_v1_v41_thinking_capped_being_memory"

#: 全部入りの run (mine_v1_006) が入れていて、この profile が止める古い記憶の部品。
_OLD_MEMORY_PARTS_TURNED_OFF = frozenset({
    "BELIEF_ATTRIBUTION_ENABLED",
    "BELIEF_CONSOLIDATION_ENABLED",
    "BELIEF_CREATE_GATE_ENABLED",
    "BELIEF_EVIDENCE_ENABLED",
    "EPISODIC_RECALL_ENABLED",
    "LLM_AFTERGLOW_ENABLED",
    "LLM_EPISODIC_ENABLED",
    "LLM_EPISODIC_RECALL_HABITUATION_ENABLED",
    "LLM_EPISODIC_RECALL_SLOT_ENABLED",
    "LLM_EPISODIC_SUBJECTIVE_ENABLED",
    "MEMO_TOOLS_ENABLED",
    "RECALL_HIT_BOOST_ENABLED",
    "SEMANTIC_LLM_GIST_ENABLED",
})


def _load(name: str) -> dict:
    return json.loads((_PROFILES / f"{name}.json").read_text(encoding="utf-8"))


class TestTheBeingMemoryProfileSwapsOnlyTheMemory:
    """新しい記憶の profile が、古い記憶の部品を止め、新しい記憶を入れることを保証する。"""

    def test_old_memory_parts_are_off_and_learned_shows_nothing(self) -> None:
        """古い記憶の部品はすべて false で書かれ、【関連する学び】は 0 件。"""
        being = _load(_BEING_MEMORY)["runtime_config"]

        not_off = {key for key in _OLD_MEMORY_PARTS_TURNED_OFF if being.get(key) is not False}

        assert not_off == set()
        assert being["SEMANTIC_PASSIVE_TOP_K"] == 0

    def test_new_memory_is_on_with_the_compared_settings(self) -> None:
        """メモ帳が入り、常に入る目次は比べた設定 (10 件、一度に 3 件) で出る。"""
        being = _load(_BEING_MEMORY)["runtime_config"]

        assert {
            key: being[key]
            for key in (
                "BEING_MEMO_ENABLED",
                "BEING_EPISODE_INDEX_LIMIT",
                "BEING_EPISODE_RECALL_MAX_HANDLES",
            )
        } == {
            "BEING_MEMO_ENABLED": True,
            "BEING_EPISODE_INDEX_LIMIT": 10,
            "BEING_EPISODE_RECALL_MAX_HANDLES": 3,
        }

    def test_thinking_output_cap_and_short_term_summary_are_kept(self) -> None:
        """thinking、出力の上限、短期記憶の要約は、比べた全部入りの run と同じ値のまま。"""
        being = _load(_BEING_MEMORY)["runtime_config"]

        assert being["LLM_REASONING_EFFORT"] == "minimal"
        assert being["LLM_MAX_OUTPUT_TOKENS"] == 4096
        assert being["SHORT_TERM_MEMORY_KIND"] == "rolling_summary"

    def test_profile_resolves_with_new_memory_on_and_old_memory_off(self) -> None:
        """make experiment と同じ経路で解決すると起動時の検査に通り、新しいエピソードとメモ帳が入り、古いエピソードと古いメモは止まっている。"""
        being = _load(_BEING_MEMORY)

        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values=_runtime_config_mapping_from_source(being)
        )

        assert cfg.being_episode_index_limit == 10
        assert cfg.being_episode_recall_max_handles == 3
        assert cfg.being_memo_enabled is True
        assert cfg.memo_tools_enabled is False
        assert cfg.episodic_enabled is False
        assert cfg.semantic_passive_top_k == 0
