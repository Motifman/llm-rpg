"""供物競争の profile が、市場系 run と同じ土俵に立っている。

比較したいのは世界の構造 (協力の市場町 vs 敵対の供物競争) であって、
記憶や reasoning の条件ではない。runtime_config が market_town と 1 キーでも
黙ってずれると、行動の違いを構造のせいと読めなくなる。
"""

from __future__ import annotations

import json
from pathlib import Path

_PROFILES = Path(__file__).resolve().parents[2] / "data" / "experiment_profiles"


def _load(name: str) -> dict:
    return json.loads((_PROFILES / f"{name}.json").read_text(encoding="utf-8"))


class TestTheProfilesShareTheirConditions:
    """market_town との差は scenario だけ。"""

    def test_runtime_config_is_identical(self) -> None:
        """runtime_config が market_town と完全に一致する。

        差の集合そのものを見るので、どちらか一方だけを変えると落ちる。
        """
        race = _load("offering_race")["runtime_config"]
        town = _load("market_town")["runtime_config"]

        assert race == town

    def test_only_the_world_differs(self) -> None:
        """scenario は供物競争を指し、run 長は市場 run と同じ 80 tick。"""
        race = _load("offering_race")

        assert race["scenario"] == "data/scenarios/offering_race_v1.json"
        assert race["max_world_ticks"] == _load("market_town")["max_world_ticks"]
