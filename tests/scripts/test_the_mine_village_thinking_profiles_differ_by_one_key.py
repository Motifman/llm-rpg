"""廃坑の山村の thinking 比較の profile が、比べたい条件だけで違っている。

thinking あり / なしの比較で、記憶や判断の設定が 1 キーでも黙ってずれると、
行動の違いを thinking のせいと読めなくなる。
"""

from __future__ import annotations

import json
from pathlib import Path

_PROFILES = Path(__file__).resolve().parents[2] / "data" / "experiment_profiles"


def _load(name: str) -> dict:
    return json.loads((_PROFILES / f"{name}.json").read_text(encoding="utf-8"))


def _differing_runtime_keys(a: dict, b: dict) -> dict[str, tuple[object, object]]:
    ra = a["runtime_config"]
    rb = b["runtime_config"]
    return {
        key: (ra.get(key), rb.get(key))
        for key in set(ra) | set(rb)
        if ra.get(key) != rb.get(key)
    }


def _differing_top_level_keys(a: dict, b: dict) -> set[str]:
    return {key for key in set(a) | set(b) if a.get(key) != b.get(key)}


class TestTheThinkingProfileDiffersOnlyInReasoning:
    """memory_jev_mine_v1_v41_thinking と _loop の差は reasoning effort だけ。"""

    def test_only_reasoning_effort_differs_in_runtime_config(self) -> None:
        """runtime_config の差は LLM_REASONING_EFFORT の none と minimal だけ。"""
        thinking = _load("memory_jev_mine_v1_v41_thinking")
        loop = _load("memory_jev_mine_v1_v41_loop")

        differing = _differing_runtime_keys(thinking, loop)

        assert differing == {"LLM_REASONING_EFFORT": ("minimal", "none")}

    def test_only_name_and_description_differ_at_top_level(self) -> None:
        """トップレベルで違うのは名前と説明だけ。世界・run 長・snapshot はそろっている。"""
        thinking = _load("memory_jev_mine_v1_v41_thinking")
        loop = _load("memory_jev_mine_v1_v41_loop")

        differing = _differing_top_level_keys(thinking, loop)

        assert differing == {"profile", "description", "runtime_config"}


class TestTheLoopProfileAddsOnlyLoopDiagnosis:
    """memory_jev_mine_v1_v41_loop と土台の差は、繰り返しの理由を問う判断だけ。"""

    def test_only_loop_diagnosis_differs_in_runtime_config(self) -> None:
        """土台 (mine_v1_002〜004 の設定) に TYPED_JUDGMENT_LOOP_DIAGNOSIS_ENABLED を足しただけ。"""
        loop = _load("memory_jev_mine_v1_v41_loop")
        base = _load("memory_jev_mine_v1_v41")

        differing = _differing_runtime_keys(loop, base)

        assert differing == {"TYPED_JUDGMENT_LOOP_DIAGNOSIS_ENABLED": (True, None)}

    def test_all_three_point_at_the_mine_village(self) -> None:
        """3 つとも廃坑の山村を 40 tick、snapshot ありで回す。"""
        names = (
            "memory_jev_mine_v1_v41",
            "memory_jev_mine_v1_v41_loop",
            "memory_jev_mine_v1_v41_thinking",
        )

        settings = {
            (
                _load(n)["scenario"],
                _load(n)["max_world_ticks"],
                _load(n)["snapshot_save"],
            )
            for n in names
        }

        assert settings == {("data/scenarios/mine_village_v1.json", 40, True)}
