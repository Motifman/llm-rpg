"""spot グラフのマップ品質検査を保証する。"""

from __future__ import annotations

from pathlib import Path

from ai_rpg_world.infrastructure.scenario.spot_map_validator import (
    KeySpotRequirement,
    MapValidationConfig,
    validate_spot_map,
)


SCENARIO_DIR = Path(__file__).resolve().parents[3] / "data" / "scenarios"


def _scenario(
    *,
    spots: list[dict],
    connections: list[dict],
    players: list[dict] | None = None,
) -> dict:
    return {
        "spots": spots,
        "connections": connections,
        "players": players or [{"id": "p1", "name": "P1", "spawn_spot": spots[0]["id"]}],
    }


def _spot(spot_id: str, *, x: float | None = None, y: float | None = None) -> dict:
    raw = {"id": spot_id, "name": spot_id, "description": spot_id}
    if x is not None and y is not None:
        raw["position"] = {"x": x, "y": y}
    return raw


def _edge(edge_id: str, a: str, b: str, *, travel_ticks: int = 1) -> dict:
    return {
        "id": edge_id,
        "from": a,
        "to": b,
        "name": edge_id,
        "travel_ticks": travel_ticks,
        "is_bidirectional": True,
    }


class TestSpotMapValidatorGraphStructure:
    """接続情報だけで閉路・関節点・到達不能を検査する。"""

    def test_triangle_has_cycle_rank_one_and_no_tree_warning(self) -> None:
        """三角形グラフは cycle_rank=1 になり、木構造警告を出さない。"""
        raw = _scenario(
            spots=[_spot("a"), _spot("b"), _spot("c")],
            connections=[
                _edge("ab", "a", "b"),
                _edge("bc", "b", "c"),
                _edge("ca", "c", "a"),
            ],
        )

        result = validate_spot_map(raw)

        assert result.ok is True
        assert result.metrics["cycle_rank"] == 1
        assert "TREE_GRAPH" not in {issue.code for issue in result.warnings}

    def test_tree_reports_cycle_rank_zero_and_articulation_spot(self) -> None:
        """木構造は cycle_rank=0 と関節点を warning として報告する。"""
        raw = _scenario(
            spots=[_spot("a"), _spot("b"), _spot("c")],
            connections=[_edge("ab", "a", "b"), _edge("bc", "b", "c")],
        )

        result = validate_spot_map(raw)

        assert result.ok is True
        assert result.metrics["cycle_rank"] == 0
        assert result.metrics["articulation_spots"] == ["b"]
        assert {"TREE_GRAPH", "ARTICULATION_SPOT"} <= {
            issue.code for issue in result.warnings
        }

    def test_unreachable_spot_is_warning_by_default_and_error_in_strict_mode(self) -> None:
        """到達不能 spot は既定では warning、strict では error になる。"""
        raw = _scenario(
            spots=[_spot("a"), _spot("b"), _spot("c")],
            connections=[_edge("ab", "a", "b")],
        )

        default_result = validate_spot_map(raw)
        strict_result = validate_spot_map(raw, MapValidationConfig(strict=True))

        assert default_result.ok is True
        assert "UNREACHABLE_SPOT" in {issue.code for issue in default_result.warnings}
        assert strict_result.ok is False
        assert "UNREACHABLE_SPOT" in {issue.code for issue in strict_result.errors}


class TestSpotMapValidatorKeySpots:
    """key_spot への辺除去・点除去 2 経路性を検査する。"""

    def test_key_spot_warns_when_single_edge_removal_breaks_route(self) -> None:
        """key_spot への唯一の橋を 1 本失うと到達不能になる場合に warning を出す。"""
        raw = _scenario(
            spots=[_spot("camp"), _spot("bridge"), _spot("signal")],
            connections=[
                _edge("camp_bridge", "camp", "bridge"),
                _edge("bridge_signal", "bridge", "signal"),
            ],
        )

        result = validate_spot_map(
            raw,
            MapValidationConfig(
                key_spots=(KeySpotRequirement("signal", severity="warning"),)
            ),
        )

        assert result.ok is True
        assert "KEY_SPOT_SINGLE_EDGE_ROUTE" in {
            issue.code for issue in result.warnings
        }

    def test_key_spot_can_escalate_node_cut_failure_to_error(self) -> None:
        """key_spot ごとの設定で、中間 spot 喪失時の単一路を error に昇格できる。"""
        raw = _scenario(
            spots=[
                _spot("camp"),
                _spot("fork"),
                _spot("north"),
                _spot("south"),
                _spot("signal"),
            ],
            connections=[
                _edge("camp_fork", "camp", "fork"),
                _edge("fork_north", "fork", "north"),
                _edge("north_signal", "north", "signal"),
                _edge("fork_south", "fork", "south"),
                _edge("south_signal", "south", "signal"),
            ],
        )

        result = validate_spot_map(
            raw,
            MapValidationConfig(
                key_spots=(KeySpotRequirement("signal", severity="error"),)
            ),
        )

        assert result.ok is False
        assert "KEY_SPOT_SINGLE_NODE_ROUTE" in {issue.code for issue in result.errors}


class TestSpotMapValidatorPositions:
    """座標が全 spot に揃った場合だけ距離依存の検査を行う。"""

    def test_travel_ticks_distance_mismatch_is_warning_only(self) -> None:
        """座標距離に対して travel_ticks が極端に短い接続は warning に留める。"""
        raw = _scenario(
            spots=[_spot("a", x=0, y=0), _spot("b", x=10, y=0)],
            connections=[_edge("ab", "a", "b", travel_ticks=1)],
        )

        result = validate_spot_map(raw, MapValidationConfig(distance_to_tick_ratio=1.0))

        assert result.ok is True
        assert "TRAVEL_TICKS_DISTANCE_MISMATCH" in {
            issue.code for issue in result.warnings
        }

    def test_partial_positions_skip_distance_checks_without_error(self) -> None:
        """一部 spot だけ position を持つ場合、距離依存検査の skip 理由が結果に残る。"""
        raw = _scenario(
            spots=[_spot("a", x=0, y=0), _spot("b")],
            connections=[_edge("ab", "a", "b", travel_ticks=1)],
        )

        result = validate_spot_map(raw, MapValidationConfig(distance_to_tick_ratio=1.0))

        assert result.ok is True
        assert result.metrics["positioned_spot_count"] == 1
        assert "TRAVEL_TICKS_DISTANCE_MISMATCH" not in {
            issue.code for issue in result.warnings
        }
        assert result.skipped_checks == [
            {
                "code": "TRAVEL_TICKS_DISTANCE_CHECK_SKIPPED",
                "reason": "position is not declared for every spot",
                "positioned_spot_count": 1,
                "spot_count": 2,
            }
        ]


class TestSpotMapValidatorExistingScenarios:
    """既存シナリオは position 無しでも error なしで検査できる。"""

    def test_survival_island_v3_without_positions_has_no_errors(self) -> None:
        """現行 v3coop は position 未導入のままでも error を出さず、距離検査 skip を明示する。"""
        import json

        raw = json.loads((SCENARIO_DIR / "survival_island_v3_coop.json").read_text())

        result = validate_spot_map(raw)

        assert result.ok is True
        assert result.errors == []
        assert result.skipped_checks[0]["code"] == "TRAVEL_TICKS_DISTANCE_CHECK_SKIPPED"
        assert result.skipped_checks[0]["positioned_spot_count"] == 0
