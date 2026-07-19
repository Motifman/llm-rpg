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

    def test_speech_actions(self) -> None:
        """speech actions だけ 抽出。"""
        evs = [
            _action(1, 1),
            _action(2, 2, tool="spot_graph_move"),  # 別 tool
            {"kind": "tick_start", "tick": 1},      # 別 kind
        ]
        out = extract_speech_actions(evs)
        assert len(out) == 1

    def test_speech_observations(self) -> None:
        """speech observations だけ 抽出。"""
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

    def test_three_tick_run(self) -> None:
        """連続 3tick の run を検出。"""
        evs = [_action(1, 1), _action(2, 1), _action(3, 1)]
        out = consecutive_runs(evs)
        assert out[1] == [3]

    def test_one_tick_empty_different_run(self) -> None:
        """間 1 tick 空いたら 別 run。"""
        evs = [_action(1, 1), _action(2, 1), _action(5, 1), _action(6, 1)]
        out = consecutive_runs(evs)
        assert sorted(out[1]) == [2, 2]

    def test_run(self) -> None:
        """単発は run 扱いしない。"""
        evs = [_action(1, 1), _action(5, 1)]
        out = consecutive_runs(evs)
        assert out[1] == []


class TestReplyLags:
    """speech observation → 同 recipient の次 speech_speak action までの delta tick。"""

    def test_observation_tick_after_lag_zero(self) -> None:
        """観測 tick の直後に発言したら lag0。"""
        obs = [_observation(5, 1)]
        acts = [_action(5, 1)]
        assert reply_lags(obs, acts) == [0]

    def test_observation_tick_before_action(self) -> None:
        """観測 tick より前の action は使わない。"""
        obs = [_observation(5, 1)]
        acts = [_action(3, 1), _action(8, 1)]
        # 5 以降の最初 = 8
        assert reply_lags(obs, acts) == [3]

    def test_recipient_action_lag_not_rendered(self) -> None:
        """recipient の action が無ければ lag は出ない。"""
        obs = [_observation(5, 1)]
        acts = [_action(6, 2)]
        assert reply_lags(obs, acts) == []

    def test_observation_after_action_all_lag_not_rendered(
        self,
    ) -> None:
        """二分探索の境界: observation tick が全 action tick より後 (= lo が
        len に到達) の場合に lag を記録しない (code-review HIGH 対応)。"""
        obs = [_observation(10, 1)]
        acts = [_action(3, 1), _action(7, 1)]
        assert reply_lags(obs, acts) == []

    def test_same_observation_and_action_tick_has_zero_lag(self) -> None:
        """同 tick で発言した場合の境界 (=== tick が二分探索の左端に来る)。"""
        obs = [_observation(5, 1)]
        acts = [_action(5, 1), _action(10, 1)]
        # 5 と 10 のうち 5 以上の最小は 5 → lag 0
        assert reply_lags(obs, acts) == [0]


class TestCrosstalk:
    """同 tick に 2 人以上が speak した tick を検出。"""

    def test_two_more_tick_count(self) -> None:
        """2 人以上 同 tick 発言で count。"""
        acts = [_action(1, 1), _action(1, 2), _action(1, 3), _action(2, 1)]
        out = crosstalk_count(acts)
        assert out == {1: 3}

    def test_excludes_tick(self) -> None:
        """単独発言 tick は含めない。"""
        acts = [_action(1, 1), _action(2, 2)]
        assert crosstalk_count(acts) == {}


class TestSummarizeEndToEnd:
    """summarize() が trace.jsonl から期待形の dict を返す。"""

    def test_fake_trace_all_rendered(self, tmp_path: Path) -> None:
        """faketrace から全指標が出る。"""
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

    def test_jsonl_line_skip(self, tmp_path: Path) -> None:
        """壊れた jsonl 行は skip。"""
        trace_path = tmp_path / "broken.jsonl"
        trace_path.write_text("not json\n" + json.dumps(_action(1, 1)) + "\n")
        summary = summarize([trace_path])
        assert summary["total_speech_actions"] == 1
