"""build_episodic_viewer.py / build_timeline_viewer.py の基本検証 (Phase 3)。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_episodic_viewer import aggregate_episodes, render_html as render_episodic
from scripts.build_timeline_viewer import build_cells, extract_players, render_html as render_timeline


def _make_events() -> list:
    return [
        {"kind": "episodic_chunk_written", "tick": 3, "player_id": 1, "payload": {
            "episode_id": "ep-1", "boundary_reason": "category_shift",
            "cues": ["action:x", "outcome:success"],
            "recall_text_snippet": "ada が漁った",
            "action_count": 3, "observation_count": 10,
        }},
        {"kind": "episodic_subjective_filled", "tick": 6, "player_id": 1, "payload": {
            "episode_id": "ep-1", "latency_ms": 1200,
            "recall_text_snippet": "あの時 ada は浜辺で…",
        }},
        {"kind": "episodic_recall", "tick": 9, "player_id": 2, "payload": {
            "candidate_count": 1,
            "candidates": [{"episode_id": "ep-1", "recall_text_snippet": "snip"}],
        }},
        {"kind": "action", "tick": 1, "player_id": 1, "payload": {
            "tool": "spot_graph_explore", "arguments": {"inner_thought": "see around"},
        }},
        {"kind": "observation", "tick": 2, "player_id": 1, "payload": {"prose": "hi"}},
        {"kind": "position_change", "tick": 0, "player_id": 1, "payload": {
            "spot_name": "beach", "player_name": "ada",
        }},
    ]


class TestEpisodicAggregation:
    """`aggregate_episodes` が chunk / subjective / recall を 1 episode に集約する。"""

    def test_chunk_は_episode_object_に_なる(self) -> None:
        episodes = aggregate_episodes(_make_events())
        assert len(episodes) == 1
        ep = episodes[0]
        assert ep.episode_id == "ep-1"
        assert ep.player_id == 1
        assert ep.written_tick == 3
        assert ep.boundary_reason == "category_shift"

    def test_subjective_fill_が_episode_に_乗る(self) -> None:
        episodes = aggregate_episodes(_make_events())
        ep = episodes[0]
        assert ep.subjective_latency_ms == 1200
        assert "ada は浜辺で" in (ep.subjective_snippet or "")

    def test_recall_history_が_episode_に_乗る(self) -> None:
        episodes = aggregate_episodes(_make_events())
        ep = episodes[0]
        assert len(ep.recalled_in) == 1
        rec = ep.recalled_in[0]
        assert rec["tick"] == 9
        assert rec["player_id"] == 2

    def test_unknown_episode_の_recall_は_skip(self) -> None:
        events = [
            {"kind": "episodic_recall", "tick": 1, "player_id": 1, "payload": {
                "candidates": [{"episode_id": "missing"}],
            }},
        ]
        episodes = aggregate_episodes(events)
        # 該当 chunk が無いので空
        assert episodes == []


class TestEpisodicRender:
    """`render_episodic` が valid な HTML を生成する。"""

    def test_html_に_player_tab_と_episode_card_が_出る(self) -> None:
        episodes = aggregate_episodes(_make_events())
        html_text = render_episodic(episodes, "test-run")
        assert "<!DOCTYPE html>" in html_text
        assert "test-run" in html_text
        assert "ep-1" in html_text or "ep-1"[:8] in html_text
        assert "category_shift" in html_text
        # recall pill が出る
        assert "by P2" in html_text


class TestTimelineExtract:
    """`extract_players` / `build_cells` の基本動作。"""

    def test_player_id_と_name_を_抽出(self) -> None:
        players = extract_players(_make_events())
        assert len(players) == 2  # player 1 と 2
        names = {p["id"]: p["name"] for p in players}
        assert names[1] == "ada"
        # player 2 は name 情報無し → fallback
        assert names[2].startswith("P")

    def test_event_kind_を_cell_に_展開(self) -> None:
        cells = build_cells(_make_events())
        # player 1 は action / observation / position_change / chunk_written = 4 cells
        # subjective_filled は cell に乗らない (詳細 viewer の役目)
        assert 1 in cells
        kinds_p1 = [c["kind"] for c in cells[1]]
        assert "action" in kinds_p1
        assert "observation" in kinds_p1
        assert "position_change" in kinds_p1
        assert "episodic_chunk_written" in kinds_p1


class TestTimelineRender:
    """`render_timeline` が valid な HTML を生成する。"""

    def test_html_に_player_row_と_tick_header_が_出る(self) -> None:
        html_text = render_timeline(_make_events(), "test-run")
        assert "<!DOCTYPE html>" in html_text
        assert "test-run" in html_text
        assert "player-label" in html_text
        assert "tick-header" in html_text
        # 色 swatch 凡例が出る
        assert "legend" in html_text
        # 各 event の cell が出る
        assert 'data-kind="action"' in html_text
        assert 'data-kind="observation"' in html_text
