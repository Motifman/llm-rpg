"""hint を出した後、当人が本当に memo_done を呼んだかを数える。

hint の件数だけでは、当たっていたのか外していたのかが分からない。hint の後に
当人が memo_done を呼んだ割合が、hint の適合率の代理になる。

重なり由来の hint と判断由来の hint は別に数える。混ぜると、意味判定に替えた
効果が薄まって見えない。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "trace-analysis"
    / "extract_metrics.py"
)
_spec = importlib.util.spec_from_file_location("extract_metrics", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
extract_metrics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(extract_metrics)


def _hint(tick: int, memo_id: str, source: str = "judgment") -> dict[str, Any]:
    return {
        "kind": "memo_hint",
        "tick": tick,
        "player_id": 1,
        "payload": {"memo_id": memo_id, "hint_source": source, "similarity": 0.9},
    }


def _done(tick: int, memo_id: str) -> dict[str, Any]:
    return {
        "kind": "memo_done",
        "tick": tick,
        "player_id": 1,
        "payload": {"memo_id": memo_id},
    }


def _judgment(**payload: Any) -> dict[str, Any]:
    base = {
        "question": "memo_completed",
        "memo_id": "m1",
        "probability": 0.9,
        "min_confidence": 0.7,
        "accepted": True,
        "unavailable_reason": None,
    }
    base.update(payload)
    return {"kind": "typed_judgment", "tick": 1, "player_id": 1, "payload": base}


def _metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    return extract_metrics._extract_memo_completion_hint(events)


class TestTheHintFollowThroughIsMeasured:
    """hint の後に memo_done が来た割合が出ることを保証する。"""

    def test_a_hint_followed_by_its_memo_done_counts_as_followed(self) -> None:
        """同じ memo が後で完了されたら、追従した 1 件になる。"""
        metrics = _metrics([_hint(3, "m1"), _done(5, "m1")])

        assert metrics["hints"] == 1
        assert metrics["followed_through"] == 1
        assert metrics["follow_through_rate"] == 1.0

    def test_a_memo_done_before_the_hint_does_not_count(self) -> None:
        """hint より前の完了は追従ではない。因果の向きを守る。"""
        metrics = _metrics([_done(2, "m1"), _hint(3, "m1")])

        assert metrics["followed_through"] == 0

    def test_a_memo_done_for_another_memo_does_not_count(self) -> None:
        """別の memo の完了は数えない (**正の対照**)。"""
        metrics = _metrics([_hint(3, "m1"), _done(5, "m2")])

        assert metrics["followed_through"] == 0

    def test_hints_are_counted_apart_by_their_source(self) -> None:
        """重なり由来と判断由来を別に数える。混ぜると効果が見えない。"""
        metrics = _metrics(
            [
                _hint(1, "m1", source="judgment"),
                _done(2, "m1"),
                _hint(3, "m2", source="overlap"),
            ]
        )

        assert metrics["hints_by_source"] == {"judgment": 1, "overlap": 1}
        assert metrics["followed_through_by_source"] == {"judgment": 1, "overlap": 0}

    def test_a_run_without_hints_reports_no_rate(self) -> None:
        """hint が 0 件の run では率を出さない。0 除算で 0% と嘘をつかない。"""
        metrics = _metrics([_judgment()])

        assert metrics["hints"] == 0
        assert metrics["follow_through_rate"] is None


class TestTheJudgmentBreakdownIsReported:
    """問うた件数と採否の内訳が出ることを保証する。"""

    def test_accepted_and_rejected_are_counted_apart(self) -> None:
        """採用と確率不足を別々に数える。"""
        metrics = _metrics([_judgment(), _judgment(accepted=False, probability=0.2)])

        assert metrics["asked"] == 2
        assert metrics["accepted"] == 1
        assert metrics["below_threshold"] == 1

    def test_a_fallback_is_counted_apart(self) -> None:
        """重なり判定へ縮退した件数は別に数える。接続を直す話になるので。"""
        metrics = _metrics(
            [
                _judgment(
                    accepted=False,
                    memo_id=None,
                    probability=None,
                    unavailable_reason="TYPED_JUDGMENT_RATE_LIMITED",
                )
            ]
        )

        assert metrics["unavailable"] == 1
        assert metrics["below_threshold"] == 0

    def test_other_questions_are_not_counted(self) -> None:
        """別の用途の判断は数えない (**正の対照**)。"""
        metrics = _metrics([_judgment(question="action_name_rescue")])

        assert metrics["asked"] == 0
