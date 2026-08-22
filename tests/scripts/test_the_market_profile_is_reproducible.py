"""市場 run の設定が、シナリオごとリポジトリに残っている。

市場 run はこれまで**スクラッチパッドの一時 JSON** で回していた。CLAUDE.md の
「実験に意味を持つ設定は profile に集約する」から外れていて、しかも**その
一時ファイルが消えて run が 1 度空振りした** — `make` が即座に失敗したのに、
完了の通知だけ見て結果を待っていた。

profile にすると、run の条件が commit に残る。**同じ条件でもう一度回せるか**が
再現性の最低線で、それはファイルが消えないところに在ることから始まる。

**元にした profile は書き換えない。** `station_drill_thinking` は別の実験が
使っていて、そこを触ると 2 つの実験の条件が同時に動く。
"""

from __future__ import annotations

import json
from pathlib import Path

_PROFILES = Path(__file__).resolve().parents[2] / "data" / "experiment_profiles"
_MARKET = "market_town"
_ORIGIN = "station_drill_thinking"


def _profile(name: str) -> dict:
    return json.loads((_PROFILES / f"{name}.json").read_text(encoding="utf-8"))


class TestTheMarketRunCanBeRepeated:
    """市場 run の条件が profile に残っていて、そのまま回せる。"""

    def test_it_points_at_the_board_scenario(self) -> None:
        """価格形成を見るシナリオ (掲示板のある市場町) を指している。"""
        assert _profile(_MARKET)["scenario"] == (
            "data/scenarios/market_town_v3_board.json"
        )

    def test_it_runs_for_eighty_ticks(self) -> None:
        """80 手番。これまでの市場 run と同じ長さで、比較できる。"""
        assert _profile(_MARKET)["max_world_ticks"] == 80

    def test_it_captures_the_prompts(self) -> None:
        """プロンプトを保存する。

        値付けの理由は独白とプロンプトの両方を突き合わせないと読めない。
        保存を落とすと、run が終わってからでは取り返せない。
        """
        runtime_config = _profile(_MARKET)["runtime_config"]

        assert runtime_config["PROMPT_DATASET_CAPTURE_ENABLED"] is True
        assert runtime_config["PROMPT_DATASET_CAPTURE_FAILURE_POLICY"] == "warn"

    def test_it_names_the_provider_it_routes_to(self) -> None:
        """呼び先の provider を明示する。

        **同じモデルでも provider で単価が 5 倍違い、しかも run の途中で
        変わった。** 書いていないと、あとから費用を run に結びつけられない。
        """
        assert _profile(_MARKET)["runtime_config"]["OPENROUTER_PROVIDER"]


class TestItDoesNotDisturbTheProfileItCameFrom:
    """元にした profile の条件を動かさない。"""

    def test_the_origin_still_points_at_its_own_scenario(self) -> None:
        """`station_drill_thinking` は自分のシナリオを指したままになっている。

        **別の実験が使っている。** 市場 run のためにここを書き換えると、
        2 つの実験の条件が同時に動く。
        """
        origin = _profile(_ORIGIN)

        assert origin["scenario"] == "data/scenarios/station_drill.json"
        assert origin["max_world_ticks"] == 50

    def test_only_the_named_conditions_differ(self) -> None:
        """元の profile との違いは、シナリオ・長さ・呼び先の 3 つだけ。

        **差を数え上げて固定する。** 記憶の設定などが黙ってずれると、市場 run
        と station_drill の結果を同じ土俵で読めなくなる。ここが落ちたら、
        増えた差が意図したものかを確かめてから足す。
        """
        market = _profile(_MARKET)["runtime_config"]
        origin = _profile(_ORIGIN)["runtime_config"]

        differing = {
            key
            for key in set(market) | set(origin)
            if market.get(key) != origin.get(key)
        }

        # LLM_WALL_TIME_CAP_SECONDS: 既定 95 秒だと、落ちる呼び出しが 95 秒
        # フルに待ってから失われる (timeout は仕様上リトライしない)。
        # 実測で run 時間の 16% がこの待ちだったので 30 秒へ下げた。
        # 世界の条件ではなく呼び先の都合なので、記憶や reasoning の比較
        # 可能性には影響しない。
        assert differing == {"OPENROUTER_PROVIDER", "LLM_WALL_TIME_CAP_SECONDS"}
