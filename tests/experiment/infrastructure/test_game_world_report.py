from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_rpg_world.experiment.infrastructure.game_world_report import game_world_report

_SUMMARY: dict[str, Any] = {
    "outcome": "ROUND_LIMIT_REACHED",
    "stop_reasons": None,
    "last_tick": 2,
    "finished_turns": 2,
    "discarded_choices": 0,
    "memory_writing_failures": {},
    "trace_failures": 0,
}
_GEN = {"person_id": "gen", "name": "ゲン"}


def _trace(tmp_path: Path, *rows: tuple[str, dict[str, Any]]) -> Path:
    path = tmp_path / "trace.jsonl"
    path.write_text("".join(json.dumps({"kind": k, "payload": p}, ensure_ascii=False) + "\n" for k, p in rows))
    return path


class TestGameWorldReport:
    """game_world_report が、新しい世界の trace から、人ごとのターンと断られた理由と飛ばした理由を report.md にまとめることを保証する。"""

    def test_refused_actions_are_counted_with_whose_and_why(self, tmp_path: Path) -> None:
        """ゲンが 2 回「北の坑道」へ行こうとして断られると、断られた行動の節に、ゲンの名前と理由が 2 回と出る。"""
        refused = {"person": _GEN, "route": {"succeeded": False}, "body": "「北の坑道」は選べない。"}
        trace = _trace(tmp_path, ("game_world.action_result", refused), ("game_world.action_result", refused))

        report = game_world_report(title="mine", trace_path=trace, summary=_SUMMARY, elapsed="00:01")

        assert "## refused actions" in report
        assert "- ゲン: 「北の坑道」は選べない。 x2" in report

    def test_turns_and_skips_are_summed_by_person(self, tmp_path: Path) -> None:
        """ゲンが 1 回動いて 1 回待ち、探している最中で 1 回飛ばされると、人ごとの表と飛ばした理由に出る。"""
        trace = _trace(
            tmp_path,
            ("game_world.turn_finished", {"person": _GEN, "outcome": "acted"}),
            ("game_world.turn_finished", {"person": _GEN, "outcome": "waited"}),
            (
                "game_world.round_opened",
                {"skipped": [{**_GEN, "reason": "in_the_middle_of_action_and_not_addressed"}]},
            ),
        )

        report = game_world_report(title="mine", trace_path=trace, summary=_SUMMARY, elapsed="00:01")

        assert "| ゲン | 1 | 1 | 0 |" in report
        assert "- ゲン: in_the_middle_of_action_and_not_addressed x1" in report

    def test_sections_without_rows_are_left_out(self, tmp_path: Path) -> None:
        """断られた行動も飛ばしたターンも無ければ、その節は出さない。"""
        report = game_world_report(title="mine", trace_path=_trace(tmp_path), summary=_SUMMARY, elapsed="00:01")

        assert "## refused actions" not in report and "## skipped turns" not in report

    def test_routine_misses_are_kept_out_of_the_missed_list(self, tmp_path: Path) -> None:
        """自分の行為 (own_act) で届かなかった知らせは別の行にまとめ、暗くて見えなかったサヨだけが届かなかった知らせの節に出る。"""
        stimulus = {
            "missed_by": [{**_GEN, "reason": "own_act"}, {"person_id": "sayo", "name": "サヨ", "reason": "too_dark"}]
        }
        trace = _trace(tmp_path, ("game_world.perception_delivered", {"stimuli": [stimulus]}))

        report = game_world_report(title="mine", trace_path=trace, summary=_SUMMARY, elapsed="00:01")

        assert "- サヨ: too_dark x1" in report
        assert "own_act" not in report.split("## missed perceptions")[1].split("(routine")[0]
        assert "(routine misses not listed above: own_act x1)" in report

    def test_writing_calls_are_split_by_component(self, tmp_path: Path) -> None:
        """書き起こしの呼び出しは部品ごとに、呼んだ数・落ちた数・費用を出し、費用の分からない呼び出しは数を添える。"""
        trace = _trace(
            tmp_path,
            ("game_world.aux_llm_call", {"call": {"component": "episode_writing", "success": True, "cost_usd": 0.002}}),
            ("game_world.aux_llm_call", {"call": {"component": "episode_writing", "success": False, "cost_usd": None}}),
        )

        report = game_world_report(title="mine", trace_path=trace, summary=_SUMMARY, elapsed="00:01")

        assert "| episode_writing | 2 | 1 | $0.0020 (1 unknown) |" in report

    def test_unreadable_trace_still_leaves_the_header(self, tmp_path: Path) -> None:
        """trace の行が壊れていても、止まった理由などの見出しは残し、まとめられなかったことを書く。"""
        trace = tmp_path / "trace.jsonl"
        trace.write_text("{broken\n", encoding="utf-8")

        report = game_world_report(title="mine", trace_path=trace, summary=_SUMMARY, elapsed="00:01")

        assert "- outcome: ROUND_LIMIT_REACHED" in report
        assert "could not summarize the trace" in report
