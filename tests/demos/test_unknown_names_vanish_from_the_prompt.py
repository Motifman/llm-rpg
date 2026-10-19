"""名前を知らない相手の名前が、実際に送るプロンプトのどこにも出ないことを総当たりで見張る (#1581)。

互いを紹介されない人たちを同じ場所から始め、全員をでたらめに行動させる。どの行動も、
名前を知らない相手の目の前で起きる。手番ごとに、実際に送る本文 (【現在選べる対象引数】を
含む) とツールの定義を見て、手番の人が名前を知らない相手の名前を探す。聞いた言葉
(「」の中) に出る名前は、そのまま聞こえてよいので数えない。

ツールや観測を足せば自動で対象になる。名前を伏せる処理を足し忘れたら、ここで落ちる。

見張るのは、画面と記録が ``PlayerAcquaintances.call_name`` (誰の名前を知っているか) に
従っていること。``call_name`` と名前を知る判定そのものの正しさは、
``tests/application/being/test_player_acquaintances_names.py`` が見る。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from scripts.fuzz_scenario_with_random_agents import FuzzResult, run_random_agents

from ai_rpg_world.application.being.player_acquaintances import PlayerAcquaintances
from ai_rpg_world.application.world_graph.spot_graph_current_state_builder import (
    SpotGraphCurrentStateBuilder,
)

_REPO = Path(__file__).resolve().parents[2]
_SEEDS = range(4)
_TICKS = 12


def _everyone_starts_together(tmp_path: Path, source: Path, spot: str) -> Path:
    """全員の初期位置を 1 か所にしたシナリオを書き出す。ファイル名は metadata.id と揃える。"""
    raw: dict[str, Any] = json.loads(source.read_text(encoding="utf-8"))
    for player in raw["players"]:
        player["spawn_spot"] = spot
    path = tmp_path / f"{raw['metadata']['id']}.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture(
    params=[
        ("data/scenarios/mine_village_v1.json", "north_shaft_head"),
        ("tests/fixtures/scenarios/two_teams_unaware.json", "camp_west"),
    ],
    ids=["mine_village", "two_teams"],
)
def scenario(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    source, spot = request.param
    return _everyone_starts_together(tmp_path, _REPO / source, spot)


def _run(scenario: Path) -> list[FuzzResult]:
    return [run_random_agents(scenario, seed=seed, max_world_ticks=_TICKS) for seed in _SEEDS]


def _stranger_findings(results: list[FuzzResult]) -> list[str]:
    return [
        f"seed={r.seed} tick={f.tick} {f.detail}"
        for r in results
        for f in r.findings
        if f.kind == "stranger_name"
    ]


def _unidentified_turns(results: list[FuzzResult]) -> list[str]:
    return [f.detail for r in results for f in r.findings if f.kind == "check"]


@pytest.mark.slow
class TestUnknownNamesVanish:
    """名前を知らない相手の名前が、手番の人に送るプロンプトのどこにも出ないことを保証する。"""

    def test_no_turn_shows_the_name_of_someone_not_yet_named(self, scenario: Path) -> None:
        """全員が同じ場所から始めてでたらめに行動しても、手番の人が名前を知らない相手の名前は、本文にもツールの定義にも出ない。見た目は出ている。"""
        results = _run(scenario)

        assert _unidentified_turns(results) == []
        assert _stranger_findings(results) == []
        assert sum(r.strangers_seen for r in results) > 0

    def test_check_catches_names_shown_in_the_list(
        self, scenario: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """正の対照: 同じ場所の人の一覧 (と、それを鍵にする対象の候補) の呼び方を実名に戻すと、stranger_name の所見が出る。出なければ、上の試験は何も見ていない。"""
        monkeypatch.setattr(
            SpotGraphCurrentStateBuilder,
            "_name_seen_by",
            lambda self, viewer_id, other_id: self._entity_name_resolver(other_id),
        )

        # 正の対照は既知の漏れの検出だけを見る。組み合わせの探索量は通常の試験に残す。
        result = run_random_agents(scenario, seed=0, max_world_ticks=2)

        assert _stranger_findings([result]) != []

    def test_check_catches_names_left_in_observations(
        self, scenario: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """正の対照: 記録に入る観測で名前を見た目に置き換える処理を外すと、stranger_name の所見が出る。"""
        monkeypatch.setattr(
            PlayerAcquaintances, "_renamed_for", lambda self, recipient, output: output
        )

        # 観測が生成され、後続のプロンプトへ届くところまで 2 tick 回す。
        result = run_random_agents(scenario, seed=0, max_world_ticks=2)

        assert _stranger_findings([result]) != []
