"""`scripts/analyze_conversation_mixing.py` の集計ロジック検証。

実験 #25 trace からの post-hoc 集計に使う script。fake trace.jsonl を
作って:
- speech action / observation の抽出
- player 別カウント
- 連続発言 run 検出
- 反応 lag 計算
- 同 tick の crosstalk
を確認する。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.analyze_conversation_mixing import (
    consecutive_runs,
    count_by_player,
    crosstalk_count,
    extract_speech_actions,
    extract_speech_observations,
    reply_lags,
    summarize,
)


def _action(tick: int, pid: int, tool: str = "speech_speak") -> dict:
    return {
        "kind": "action", "tick": tick, "player_id": pid,
        "payload": {"tool": tool, "arguments": {}},
    }


def _observation(tick: int, pid: int, category: str = "speech") -> dict:
    return {
        "kind": "observation", "tick": tick, "player_id": pid,
        "payload": {"observation_category": category, "prose": ""},
    }


class TestExtractors:
    """kind / category フィルタが正しく動く。"""

    def test_speech_actions_だけ_抽出(self) -> None:
        evs = [
            _action(1, 1),
            _action(2, 2, tool="spot_graph_move"),  # 別 tool
            {"kind": "tick_start", "tick": 1},      # 別 kind
        ]
        out = extract_speech_actions(evs)
        assert len(out) == 1

    def test_speech_observations_だけ_抽出(self) -> None:
        evs = [
            _observation(1, 1),
            _observation(2, 2, category="environment"),  # 別 category
            _action(1, 1),                                # 別 kind
        ]
        out = extract_speech_observations(evs)
        assert len(out) == 1


class TestCounts:
    """player 別 / tick 別カウント。"""

    def test_count_by_player(self) -> None:
        evs = [_action(1, 1), _action(2, 1), _action(3, 2)]
        assert count_by_player(evs) == {1: 2, 2: 1}


class TestConsecutiveRuns:
    """同 player が連続 tick で発言した run を検出する。"""

    def test_連続_3_tick_の_run_を_検出(self) -> None:
        evs = [_action(1, 1), _action(2, 1), _action(3, 1)]
        out = consecutive_runs(evs)
        assert out[1] == [3]

    def test_間_1_tick_空いたら_別_run(self) -> None:
        evs = [_action(1, 1), _action(2, 1), _action(5, 1), _action(6, 1)]
        out = consecutive_runs(evs)
        assert sorted(out[1]) == [2, 2]

    def test_単発_は_run_扱いしない(self) -> None:
        evs = [_action(1, 1), _action(5, 1)]
        out = consecutive_runs(evs)
        assert out[1] == []


class TestReplyLags:
    """speech observation → 同 recipient の次 speech_speak action までの delta tick。"""

    def test_観測_tick_の_直後_に_発言したら_lag_0(self) -> None:
        obs = [_observation(5, 1)]
        acts = [_action(5, 1)]
        assert reply_lags(obs, acts) == [0]

    def test_観測_tick_より_前_の_action_は_使わない(self) -> None:
        obs = [_observation(5, 1)]
        acts = [_action(3, 1), _action(8, 1)]
        # 5 以降の最初 = 8
        assert reply_lags(obs, acts) == [3]

    def test_recipient_の_action_が_無ければ_lag_は_出ない(self) -> None:
        obs = [_observation(5, 1)]
        acts = [_action(6, 2)]
        assert reply_lags(obs, acts) == []


class TestCrosstalk:
    """同 tick に 2 人以上が speak した tick を検出。"""

    def test_2_人以上_同_tick_発言で_count(self) -> None:
        acts = [_action(1, 1), _action(1, 2), _action(1, 3), _action(2, 1)]
        out = crosstalk_count(acts)
        assert out == {1: 3}

    def test_単独_発言_tick_は_含めない(self) -> None:
        acts = [_action(1, 1), _action(2, 2)]
        assert crosstalk_count(acts) == {}


class TestSummarizeEndToEnd:
    """summarize() が trace.jsonl から期待形の dict を返す。"""

    def test_fake_trace_から_全指標が_出る(self, tmp_path: Path) -> None:
        events = [
            _action(1, 1), _action(2, 1), _action(3, 1),  # run len=3 for p1
            _observation(1, 2),                             # p2 listens
            _action(4, 2),                                  # p2 replies tick 4, lag 3
            _action(5, 1), _action(5, 2),                   # crosstalk @ tick 5
        ]
        trace_path = tmp_path / "trace.jsonl"
        with trace_path.open("w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

        summary = summarize([trace_path])
        assert summary["total_speech_actions"] == 6
        assert summary["total_speech_observations"] == 1
        assert summary["speech_actions_by_player"] == {1: 4, 2: 2}
        assert summary["consecutive_runs_by_player"][1]["max_run"] == 3
        assert summary["reply_lag_ticks"]["count"] == 1
        assert summary["reply_lag_ticks"]["max"] == 3
        assert summary["crosstalk_ticks"]["tick_count_with_2plus_speakers"] == 1

    def test_壊れた_jsonl_行は_skip(self, tmp_path: Path) -> None:
        trace_path = tmp_path / "broken.jsonl"
        trace_path.write_text("not json\n" + json.dumps(_action(1, 1)) + "\n")
        summary = summarize([trace_path])
        assert summary["total_speech_actions"] == 1
