"""供物競争 v2 の profile が、市場系 run と同じ土俵に立っている。

比較したいのは世界の構造 (協力の市場町 vs 敵対の供物競争) であって、
記憶や reasoning の条件ではない。runtime_config が market_town と 1 キーでも
黙ってずれると、行動の違いを構造のせいと読めなくなる。

run 長は揃える対象から外している。理由は `test_it_runs_long_enough_to_close_a_deal`
に書いた。
"""

from __future__ import annotations

import json
from pathlib import Path

_PROFILES = Path(__file__).resolve().parents[2] / "data" / "experiment_profiles"


def _load(name: str) -> dict:
    return json.loads((_PROFILES / f"{name}.json").read_text(encoding="utf-8"))


class TestTheProfilesShareTheirConditions:
    """market_town との差は scenario と run 長だけ。"""

    def test_runtime_config_is_identical(self) -> None:
        """runtime_config が market_town と完全に一致する。

        差の集合そのものを見るので、どちらか一方だけを変えると落ちる。
        """
        race = _load("offering_race_v2")["runtime_config"]
        town = _load("market_town")["runtime_config"]

        assert race == town

    def test_it_points_at_the_offering_race(self) -> None:
        """scenario は供物競争 v2 を指している。"""
        race = _load("offering_race_v2")

        assert race["scenario"] == "data/scenarios/offering_race_v2.json"

    def test_it_runs_long_enough_to_close_a_deal(self) -> None:
        """run 長は市場 run より長く、140 tick ある。

        80 tick の run では交渉が t51 に動き出し、価格の対案が出たのは t78
        だった。残り 2 tick で打ち切られたので、成立を見るには長さが足りない。
        条件を揃える対象は runtime_config (記憶・reasoning・呼び先) であって、
        run 長はここで意図的に外している。
        """
        race = _load("offering_race_v2")

        assert race["max_world_ticks"] == 140
        assert race["max_world_ticks"] > _load("market_town")["max_world_ticks"]
