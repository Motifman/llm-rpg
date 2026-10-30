"""供物競争 v2 の profile が、市場系 run と同じ土俵に立っている。

比較したいのは世界の構造 (協力の市場町 vs 敵対の供物競争) であって、
記憶や reasoning の条件ではない。runtime_config が market_town と 1 キーでも
黙ってずれると、行動の違いを構造のせいと読めなくなる。

run 長は揃える対象から外している。理由は `test_it_runs_longer_than_the_market_run`
に書いた。
"""

from __future__ import annotations

import json
from pathlib import Path

_PROFILES = Path(__file__).resolve().parents[2] / "data" / "experiment_profiles"


_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str) -> dict:
    return json.loads((_PROFILES / f"{name}.json").read_text(encoding="utf-8"))


def _scenario(relative_path: str) -> dict:
    return json.loads((_ROOT / relative_path).read_text(encoding="utf-8"))


class TestTheProfilesShareTheirConditions:
    """market_town との差は scenario と run 長だけ。"""

    def test_runtime_config_is_identical(self) -> None:
        """runtime_config が market_town と完全に一致する。

        差の集合そのものを見るので、どちらか一方だけを変えると落ちる。
        """
        race = _load("offering_race_v2")["runtime_config"]
        town = _load("market_town")["runtime_config"]

        assert race == town

    def test_only_the_named_conditions_differ(self) -> None:
        """トップレベルで market_town と違うのは、名前・説明・世界・run 長だけ。

        差の集合そのものを固定する。`snapshot_save` が黙って消えると
        `bool(config_source.get(...))` が false へ落ちるだけで警告が出ない。
        """
        race = _load("offering_race_v2")
        town = _load("market_town")

        differing = {key for key in set(race) | set(town) if race.get(key) != town.get(key)}

        assert differing == {
            "profile",
            "description",
            "scenario",
            "max_world_ticks",
        }

    def test_it_points_at_the_offering_race(self) -> None:
        """scenario は供物競争 v2 を指している。"""
        race = _load("offering_race_v2")

        assert race["scenario"] == "data/scenarios/offering_race_v2.json"

    def test_it_runs_longer_than_the_market_run(self) -> None:
        """run 長が市場 run より長い。

        80 tick の run では交渉が t51 に動き出し、価格の対案が出たのは t78
        だった。残り 2 tick で打ち切られたので、成立を見るには長さが足りない。
        条件を揃える対象は runtime_config (記憶・reasoning・呼び先) であって、
        run 長はここで意図的に外している。

        **値そのものは固定しない** (人間の判断で動く)。実際の run 長が世界の
        刻限と揃っていることは `TestTheProfileDoesNotCutTheWorldShort` が見る。
        """
        race = _load("offering_race_v2")

        assert race["max_world_ticks"] > _load("market_town")["max_world_ticks"]


class TestTheProfileDoesNotCutTheWorldShort:
    """profile の run 長と、シナリオが自分で持つ刻限が食い違わない。"""

    def test_the_loop_cap_matches_the_scenario_deadline(self) -> None:
        """`max_world_ticks` が、シナリオの `TICK_LIMIT` と同じ値になっている。

        **`max_world_ticks` はループの上限でしかない。** run は毎 tick
        `check_game_end()` を見て、シナリオ側の `TICK_LIMIT` に当たった時点で
        終わる。profile だけ 140 に伸ばしても世界は t80 で終わり、エージェントに
        見える残り時間も `TICK_LIMIT` から作られるので 80 のままだった。
        **値を書いたのに何も起きない**形の静かな失敗で、実際に一度これで
        run 長を伸ばしたつもりになった。

        揃っていないと 2 方向に壊れる。profile が短いと判定 tick に届かず
        勝敗が付かない。profile が長いと余りが空回りする。
        """
        scenario = _scenario(_load("offering_race_v2")["scenario"])
        deadline = next(c["tick_limit"] for c in scenario["game_end_conditions"]["lose"] if c["type"] == "TICK_LIMIT")

        assert _load("offering_race_v2")["max_world_ticks"] == deadline
