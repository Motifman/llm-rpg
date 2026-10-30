"""救えた数と救えなかった数を、対で数える。

採用件数だけを出すと「効いた」と読める。同じ run の
``INTERACTION_ACTION_NOT_FOUND`` と並べないと、置き換えが増えたのか失敗が
減ったのかが分からない。

採らなかった理由も分ける。確信不足なら閾値を動かす話で、判断を得られなかった
のなら接続を直す話になる。同じ数に混ぜると、次に何をするかが決まらない。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_MODULE_PATH = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "trace-analysis" / "extract_metrics.py"
_spec = importlib.util.spec_from_file_location("extract_metrics", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
extract_metrics = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(extract_metrics)


def _judgment(**payload: Any) -> dict[str, Any]:
    base = {
        "question": "action_name_rescue",
        "original": "gather",
        "chosen": "reap_wheat",
        "probability": 0.9,
        "min_confidence": 0.7,
        "accepted": True,
        "unavailable_reason": None,
    }
    base.update(payload)
    return {"kind": "typed_judgment", "tick": 1, "player_id": 1, "payload": base}


def _not_found() -> dict[str, Any]:
    return {
        "kind": "action_result",
        "tick": 1,
        "player_id": 1,
        "payload": {"error_code": "INTERACTION_ACTION_NOT_FOUND"},
    }


def _metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    return extract_metrics._extract_action_name_rescue(events)


class TestTheRescueCountsAreReportedWithTheirOutcome:
    """発火・採否・未達の内訳と、残った失敗が対で出ることを保証する。"""

    def test_accepted_and_rejected_are_counted_apart(self) -> None:
        """採用と確信不足が別々に数えられる。"""
        metrics = _metrics(
            [
                _judgment(),
                _judgment(accepted=False, probability=0.4),
            ]
        )

        assert metrics["asked"] == 2
        assert metrics["accepted"] == 1
        assert metrics["below_threshold"] == 1

    def test_a_no_match_answer_is_counted_apart_from_low_confidence(self) -> None:
        """「該当なし」は確信不足と別に数える。世界に無い行為だったという記録。"""
        metrics = _metrics([_judgment(accepted=False, chosen=None)])

        assert metrics["no_match"] == 1
        assert metrics["below_threshold"] == 0

    def test_an_unavailable_judgment_is_counted_apart(self) -> None:
        """判断を得られなかった件数は別に数える。接続を直す話になるので。"""
        metrics = _metrics([_judgment(accepted=False, unavailable_reason="TYPED_JUDGMENT_RATE_LIMITED")])

        assert metrics["unavailable"] == 1
        assert metrics["below_threshold"] == 0
        assert metrics["no_match"] == 0

    def test_the_remaining_failures_are_counted_alongside(self) -> None:
        """救えなかった結果として残った失敗も同じ表に出る。"""
        metrics = _metrics([_judgment(), _not_found(), _not_found()])

        assert metrics["accepted"] == 1
        assert metrics["interaction_action_not_found"] == 2

    def test_other_questions_are_not_counted(self) -> None:
        """別の用途の判断は数えない (**正の対照**)。"""
        metrics = _metrics([_judgment(question="memo_completed")])

        assert metrics["asked"] == 0

    def test_a_run_without_judgments_reports_zeros(self) -> None:
        """判断を引かなかった run は 0 件で、確率の代表値は None になる。"""
        metrics = _metrics([_not_found()])

        assert metrics["asked"] == 0
        assert metrics["interaction_action_not_found"] == 1
        assert metrics["probability_p50"] is None

    def test_the_probability_spread_is_reported(self) -> None:
        """確率の代表値が出る。閾値を動かす判断に使う。"""
        metrics = _metrics(
            [
                _judgment(probability=0.5, accepted=False),
                _judgment(probability=0.9),
                _judgment(probability=0.95),
            ]
        )

        assert metrics["probability_p50"] == 0.9
