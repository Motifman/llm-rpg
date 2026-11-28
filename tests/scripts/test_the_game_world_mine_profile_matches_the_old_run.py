"""新しい世界の廃坑の山村の profile が、比べる古い run と同じ LLM と記憶の設定で動く (#2235)。

設定が黙ってずれると、新しい世界と古い世界の違いを、世界の作り直しのせいと読めなくなる。
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.run_scenario_experiment import _runtime_config_mapping_from_source

from ai_rpg_world.experiment.infrastructure.game_world_play_settings import GameWorldPlaySettings

_PROFILES = Path(__file__).resolve().parents[2] / "data" / "experiment_profiles"
_NEW = "game_world_mine_v2_v41_thinking_capped"
_OLD = "memory_jev_mine_v1_v41_thinking_capped_being_memory"
_SHARED_KEYS = (
    "LLM_CLIENT",
    "LLM_MODEL",
    "OPENAI_API_BASE",
    "OPENROUTER_PROVIDER",
    "LLM_REASONING_EFFORT",
    "LLM_MAX_OUTPUT_TOKENS",
    "LLM_TURN_PARALLEL_WORKERS",
    "BEING_EPISODE_INDEX_LIMIT",
    "BEING_EPISODE_RECALL_MAX_HANDLES",
    "SCENARIO_RANDOM_SEED",
)


def _load(name: str) -> dict:
    return json.loads((_PROFILES / f"{name}.json").read_text(encoding="utf-8"))


class TestTheGameWorldMineProfile:
    """新しい世界の廃坑の山村の profile が、古い run とそろえた設定のまま新しい世界に読まれることを保証する。"""

    def test_llm_and_memory_settings_match_the_old_run(self) -> None:
        """モデル・provider・思考の強さ・出力の上限・同時に呼ぶ数・目次の件数・呼び出しの件数・乱数の種が古い profile と同じ。"""
        new = _load(_NEW)["runtime_config"]
        old = _load(_OLD)["runtime_config"]

        assert {key: new[key] for key in _SHARED_KEYS} == {key: old[key] for key in _SHARED_KEYS}

    def test_the_game_world_reads_every_key_with_a_real_llm(self) -> None:
        """新しい世界の設定が知らない鍵を 1 つも含まず、LiteLLM で 2 人ずつ考える設定として読まれる。"""
        source = _load(_NEW)

        settings = GameWorldPlaySettings.from_runtime_config(_runtime_config_mapping_from_source(source))

        assert source["world"] == "game_world"
        assert settings.llm_client == "litellm"
        assert settings.turn_parallel_workers == 2
        assert settings.llm_values["LLM_MODEL"] == "openrouter/deepseek/deepseek-v4.1-flash"
