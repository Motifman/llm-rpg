"""廃坑の山村の新しい記憶の profile が、メモだけの profile とメモとエピソードの設定だけで違っている。

新しい記憶 (#1621) を全部入りの run (mine_v1_006) と比べる。古い部品を止めた状態は
メモだけの profile で検査済みなので、そこからの差を見張る。thinking や出力の上限が
黙ってずれると、行動の違いを記憶のせいと読めなくなる。
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

_MEMO_ONLY = "memory_jev_mine_v1_v41_thinking_capped_memo_only"
_BEING_MEMORY = "memory_jev_mine_v1_v41_thinking_capped_being_memory"


def _load(name: str) -> dict:
    return json.loads((_PROFILES / f"{name}.json").read_text(encoding="utf-8"))


class TestTheBeingMemoryProfileSwapsOnlyTheMemory:
    """新しい記憶の profile とメモだけの profile の差は、古いメモを止めて新しい記憶を入れる設定だけ。"""

    def test_runtime_config_differs_only_in_memo_and_episode_keys(self) -> None:
        """runtime_config の差は、古いメモを止め、メモ帳とエピソードの書き起こしと目次 (呼び出された順、10 件、一度に 3 件) を入れる 6 キーだけ。"""
        being = _load(_BEING_MEMORY)["runtime_config"]
        memo_only = _load(_MEMO_ONLY)["runtime_config"]

        differing = {
            key: (being.get(key), memo_only.get(key))
            for key in set(being) | set(memo_only)
            if being.get(key) != memo_only.get(key)
        }

        assert differing == {
            "MEMO_TOOLS_ENABLED": (False, True),
            "BEING_MEMO_ENABLED": (True, None),
            "BEING_EPISODE_WRITING_ENABLED": (True, None),
            "BEING_EPISODE_INDEX_ORDER": ("recalled_rises_to_top", None),
            "BEING_EPISODE_INDEX_LIMIT": (10, None),
            "BEING_EPISODE_RECALL_MAX_HANDLES": (3, None),
        }

    def test_world_and_run_length_are_the_same(self) -> None:
        """世界、run の長さ、snapshot の保存はメモだけの profile と同じ。"""
        being = _load(_BEING_MEMORY)
        memo_only = _load(_MEMO_ONLY)

        differing = {
            key for key in set(being) | set(memo_only) if being.get(key) != memo_only.get(key)
        }

        assert differing == {"profile", "description", "runtime_config"}

    def test_profile_resolves_with_new_memory_on_and_old_memory_off(self) -> None:
        """make experiment と同じ経路で解決すると起動時の検査に通り、新しいエピソードとメモ帳が入り、古いエピソードと古いメモは止まっている。"""
        being = _load(_BEING_MEMORY)

        cfg = ResolvedLlmRuntimeConfig.from_mapping(
            values=_runtime_config_mapping_from_source(being)
        )

        assert cfg.being_episode_writing_enabled is True
        assert cfg.being_episode_index_order == "recalled_rises_to_top"
        assert cfg.being_episode_index_limit == 10
        assert cfg.being_episode_recall_max_handles == 3
        assert cfg.being_memo_enabled is True
        assert cfg.memo_tools_enabled is False
        assert cfg.episodic_enabled is False
        assert cfg.semantic_passive_top_k == 0
