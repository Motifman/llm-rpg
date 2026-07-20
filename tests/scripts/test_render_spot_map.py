"""scripts/render_spot_map.py の地図 HTML 生成を保証する。"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.render_spot_map import main, render_spot_map_html


SCENARIO_DIR = Path(__file__).resolve().parents[2] / "data" / "scenarios"


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


def _spot(spot_id: str, *, name: str | None = None, x: float | None = None, y: float | None = None) -> dict:
    raw = {"id": spot_id, "name": name or spot_id, "description": spot_id}
    if x is not None and y is not None:
        raw["position"] = {"x": x, "y": y}
    return raw


def _edge(edge_id: str, source: str, target: str, *, travel_ticks: int = 1, bidirectional: bool = True) -> dict:
    return {
        "id": edge_id,
        "from": source,
        "to": target,
        "name": edge_id,
        "travel_ticks": travel_ticks,
        "is_bidirectional": bidirectional,
    }


class TestRenderSpotMapHtml:
    """scenario JSON から座標駆動の地図 HTML を生成する挙動を保証する。"""

    def test_positioned_spots_are_rendered_as_svg_with_north_up_y_axis(self) -> None:
        """position 付き spot は SVG ノードになり、地理 y が大きいほど画面上側に描かれる。"""
        raw = _scenario(
            spots=[
                _spot("south", name="南の浜", x=0, y=0),
                _spot("north", name="北の森", x=0, y=10),
            ],
            connections=[_edge("path", "south", "north", travel_ticks=3)],
        )

        html = render_spot_map_html(raw, title="toy")

        assert 'data-spot-id="south"' in html
        assert 'data-spot-id="north"' in html
        assert 'data-screen-y="24.0"' in html
        assert 'data-screen-y="424.0"' in html
        assert "travel_ticks: 3" in html

    def test_unpositioned_spots_are_listed_in_separate_area(self) -> None:
        """position 未設定 spot は欠落せず、未配置一覧と件数として HTML に残る。"""
        raw = _scenario(
            spots=[_spot("camp", x=0, y=0), _spot("unknown", name="未踏の洞穴")],
            connections=[_edge("camp_unknown", "camp", "unknown")],
        )

        html = render_spot_map_html(raw, title="partial")

        assert "未配置 spot: 1 / 2" in html
        assert "未踏の洞穴" in html
        assert 'data-unpositioned-spot-id="unknown"' in html

    def test_one_way_connection_uses_arrow_marker(self) -> None:
        """is_bidirectional=false の接続は矢印で向きを表示する。"""
        raw = _scenario(
            spots=[_spot("a", x=0, y=0), _spot("b", x=10, y=0)],
            connections=[_edge("slide", "a", "b", bidirectional=False)],
        )

        html = render_spot_map_html(raw, title="one-way")

        assert 'data-connection-id="slide"' in html
        assert 'marker-end="url(#arrow-one-way)"' in html

    def test_key_and_unreachable_spots_have_visible_classes(self) -> None:
        """key_spot と到達不能 spot は class と凡例で色分けできる形にする。"""
        raw = _scenario(
            spots=[
                _spot("camp", x=0, y=0),
                _spot("signal", x=10, y=0),
                _spot("isolated", x=20, y=0),
            ],
            connections=[_edge("camp_signal", "camp", "signal")],
            players=[{"id": "p1", "name": "P1", "spawn_spot": "camp"}],
        )

        html = render_spot_map_html(raw, title="marked", key_spots=("signal",))

        assert 'class="spot-node key-spot"' in html
        assert 'class="spot-node unreachable-spot"' in html
        assert "重要地点" in html
        assert "到達不能" in html


def test_cli_writes_html_file_for_positionless_scenario(tmp_path: Path) -> None:
    """CLI は position 無し scenario でも未配置一覧つき HTML を出力して終了コード 0 を返す。"""
    scenario_path = tmp_path / "scenario.json"
    output_path = tmp_path / "map.html"
    scenario_path.write_text(
        json.dumps(
            _scenario(
                spots=[_spot("camp", name="浜辺"), _spot("forest", name="森")],
                connections=[_edge("path", "camp", "forest")],
            )
        ),
        encoding="utf-8",
    )

    exit_code = main([str(scenario_path), "--output", str(output_path)])

    assert exit_code == 0
    html = output_path.read_text(encoding="utf-8")
    assert "未配置 spot: 2 / 2" in html
    assert "浜辺" in html


def test_survival_island_v3_without_positions_renders_unpositioned_list(tmp_path: Path) -> None:
    """現行 v3coop は position 無しでも破綻せず、全 spot を未配置一覧に出す。"""
    output_path = tmp_path / "v3coop_map.html"
    scenario_path = SCENARIO_DIR / "survival_island_v3_coop.json"

    exit_code = main([str(scenario_path), "--output", str(output_path)])

    assert exit_code == 0
    html = output_path.read_text(encoding="utf-8")
    assert "未配置 spot: 25 / 25" in html
    assert "shipwreck_beach" in html
