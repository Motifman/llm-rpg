"""島シナリオ4本が個人結果・中立終了・生存圧を別々に宣言することを保証する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


_SCENARIOS = Path(__file__).resolve().parents[3] / "data" / "scenarios"
_EXPECTED_SCHEDULES = {
    "survival_island_v2.json": ((192, 288, 336), 384),
    "survival_island_v2_short.json": ((96, 144), 192),
    "survival_island_v3_coop.json": ((144, 192), 240),
    "survival_island_v4_coop.json": ((144, 192), 240),
}


@pytest.fixture(params=tuple(_EXPECTED_SCHEDULES))
def island_scenario(request: pytest.FixtureRequest) -> tuple[str, dict]:
    """4本を手列挙し、過去の時間割をそれぞれ照合できる形で返す。"""
    filename = str(request.param)
    raw = json.loads((_SCENARIOS / filename).read_text(encoding="utf-8"))
    return filename, raw


class TestIslandOutcomeDeclarations:
    """旧一体型設定を残さず、4本すべてを同じ宣言語彙へ移した状態を固定する。"""

    def test_legacy_outcome_resolution_is_absent(
        self, island_scenario: tuple[str, dict]
    ) -> None:
        """4本のどれにも廃止した outcome_resolution キーを残さない。"""
        _, raw = island_scenario
        assert "outcome_resolution" not in raw

    def test_rescue_and_stranded_schedule_is_preserved(
        self, island_scenario: tuple[str, dict]
    ) -> None:
        """救助機会と取り残し期限は移行前の各シナリオ固有値を維持する。"""
        filename, raw = island_scenario
        rescue_ticks = tuple(
            rule["trigger"]["tick"]
            for rule in raw["player_outcome_rules"]
            if rule["outcome"] == "RESCUED"
        )
        stranded_ticks = tuple(
            rule["trigger"]["tick"]
            for rule in raw["player_outcome_rules"]
            if rule["outcome"] == "STRANDED"
        )

        assert (rescue_ticks, stranded_ticks) == (
            _EXPECTED_SCHEDULES[filename][0],
            (_EXPECTED_SCHEDULES[filename][1],),
        )

    def test_rescue_rules_require_signal_and_summit(
        self, island_scenario: tuple[str, dict]
    ) -> None:
        """各救助機会は狼煙と山頂在席を対象者条件にし、一度だけ発火する。"""
        _, raw = island_scenario
        rescue_rules = [
            rule for rule in raw["player_outcome_rules"]
            if rule["outcome"] == "RESCUED"
        ]
        for rule in rescue_rules:
            assert rule["once"] is True
            assert rule["trigger"]["condition_type"] == "TICK_AT_LEAST"
            assert rule["player_conditions"] == [
                {"condition_type": "FLAG_SET", "flag_name": "signal_fire_lit"},
                {"condition_type": "PLAYER_AT_SPOT", "target_spot": "summit"},
            ]

    def test_stranded_rule_targets_every_unresolved_player(
        self, island_scenario: tuple[str, dict]
    ) -> None:
        """期限規則は対象条件を空にし、未確定者全員だけを取り残しへ確定する。"""
        _, raw = island_scenario
        stranded = next(
            rule for rule in raw["player_outcome_rules"]
            if rule["outcome"] == "STRANDED"
        )
        assert stranded["once"] is True
        assert stranded["player_conditions"] == []

    def test_neutral_end_and_needs_are_declared_separately(
        self, island_scenario: tuple[str, dict]
    ) -> None:
        """混合結果の終了と飢餓ダメージを個人結果規則へ混ぜず専用節に置く。"""
        _, raw = island_scenario
        assert raw["game_end_conditions"]["end"] == [
            {"type": "ALL_PLAYER_OUTCOMES_RESOLVED"}
        ]
        assert raw["needs"] == {"starvation_damage_per_tick": 2}
