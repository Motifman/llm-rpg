from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from ai_rpg_world.being.application.action_tools import ActionTools
from ai_rpg_world.being.application.rechoose_name import (
    NO_MATCH_OPTION,
    NameChoiceAnswer,
    NameChoiceJudging,
    NameChoiceQuestion,
    NameChoiceUnavailable,
    RechooseName,
)
from ai_rpg_world.being.contract import (
    ActionChoice,
    ActionChoices,
    ArgumentOutline,
    Candidate,
    OfferedBeingTools,
    PickOne,
)

SHRINES = {"東の祭壇": "供物を置く", "西の祠": None}


class _Judging(NameChoiceJudging):
    """決めた答えを返し、問われた材料と問いを覚える。"""

    def __init__(self, answer: NameChoiceAnswer | NameChoiceUnavailable) -> None:
        self._answer = answer
        self.asked: list[tuple[Mapping[str, Any], NameChoiceQuestion]] = []

    def choose(self, state: Mapping[str, Any], question: NameChoiceQuestion) -> NameChoiceAnswer:
        self.asked.append((state, question))
        if isinstance(self._answer, NameChoiceUnavailable):
            raise self._answer
        return self._answer


def _answer(value: str, probability: float, confidence: float | None) -> NameChoiceAnswer:
    return NameChoiceAnswer(
        value=value, probabilities={value: probability}, confidence=confidence, source="stub", latency_ms=3.0
    )


def _rechoose(judging: _Judging, written: str = "East Shrine") -> Any:
    return RechooseName(judging, min_confidence=0.85).rechoose(
        written, label="相手", candidates=SHRINES, parent=None, tool="interact", inner_thought="祭壇へ向かう"
    )


class TestRechooseName:
    """RechooseName が、古い run の選び直しと同じ決まりで、候補に当たらない名前を Jev に選び直させることを保証する。"""

    def test_confident_choice_replaces_the_name(self) -> None:
        """「East Shrine」に Jev が確率 0.93・確信 0.9 で「東の祭壇」を選ぶと、東の祭壇に置き換え、判断の値を残す。"""
        rechoice = _rechoose(_Judging(_answer("東の祭壇", 0.93, 0.9)))

        assert (rechoice.replaced_with, rechoice.accepted) == ("東の祭壇", True)
        assert (rechoice.original, rechoice.probability, rechoice.confidence) == ("East Shrine", 0.93, 0.9)
        assert (rechoice.tool, rechoice.argument, rechoice.min_confidence) == ("interact", "相手", 0.85)

    @pytest.mark.parametrize(("probability", "confidence"), [(0.84, 0.9), (0.93, 0.84)])
    def test_choice_below_the_threshold_is_not_taken(self, probability: float, confidence: float) -> None:
        """確率か確信のどちらかが下限 0.85 に届かなければ寄せない。選んだものは採らなかった判断として残す。"""
        rechoice = _rechoose(_Judging(_answer("東の祭壇", probability, confidence)))

        assert (rechoice.replaced_with, rechoice.accepted, rechoice.chosen) == (None, False, "東の祭壇")

    @pytest.mark.parametrize(("probability", "confidence"), [(0.85, 0.9), (0.93, 0.85), (0.85, None)])
    def test_choice_exactly_at_the_threshold_is_taken(self, probability: float, confidence: float | None) -> None:
        """確率と確信がちょうど下限 0.85 なら寄せる。確信の無い答えは確率だけで決める。"""
        rechoice = _rechoose(_Judging(_answer("東の祭壇", probability, confidence)))

        assert (rechoice.replaced_with, rechoice.accepted) == ("東の祭壇", True)

    def test_no_match_is_never_replaced(self) -> None:
        """Jev が「該当なし」を選べば、確信が高くても置き換えない。一番近いものに化けさせない。"""
        rechoice = _rechoose(_Judging(_answer(NO_MATCH_OPTION, 0.99, 0.99)))

        assert (rechoice.replaced_with, rechoice.accepted, rechoice.chosen) == (None, False, None)

    def test_question_always_offers_no_match_with_the_candidates(self) -> None:
        """問いの選択肢は、候補と、その説明と、「該当なし」。材料に書かれた名前・値の見出し・ツール・独白が入る。"""
        judging = _Judging(_answer("東の祭壇", 0.93, 0.9))

        _rechoose(judging)

        [(state, question)] = judging.asked
        assert question.options == {
            "東の祭壇": "供物を置く",
            "西の祠": None,
            NO_MATCH_OPTION: "一覧のどれにも当たらない",
        }
        assert state == {
            "written_name": "East Shrine",
            "argument": "相手",
            "tool": "interact",
            "candidates": {"東の祭壇": "供物を置く", "西の祠": None},
            "inner_thought": "祭壇へ向かう",
        }

    def test_parent_candidate_is_given_as_material(self) -> None:
        """候補の下の値を選び直すときは、どの候補の下かも材料に入れる。"""
        judging = _Judging(_answer("東の祭壇", 0.93, 0.9))

        RechooseName(judging, min_confidence=0.85).rechoose(
            "open", label="操作", candidates=SHRINES, parent="金庫", tool="interact", inner_thought=None
        )

        [(state, _)] = judging.asked
        assert state["under"] == "金庫" and "inner_thought" not in state

    def test_unavailable_judgment_keeps_the_name_and_its_reason(self) -> None:
        """判断が得られなければ置き換えず、得られなかった理由を残す。判断が無かったことを、判断の結果と同じ扱いにしない。"""
        rechoice = _rechoose(_Judging(NameChoiceUnavailable("timeout", code="JEV_TIMEOUT")))

        assert (rechoice.replaced_with, rechoice.accepted, rechoice.unavailable_reason) == (None, False, "JEV_TIMEOUT")

    def test_threshold_outside_zero_to_one_is_rejected(self) -> None:
        """下限が 0 以下か 1 を超えれば、組み立てのときに断る。"""
        with pytest.raises(ValueError):
            RechooseName(_Judging(_answer("東の祭壇", 0.9, 0.9)), min_confidence=0.0)


class TestMatchingNamesInAToolCall:
    """RechooseName.match_names が、ツールの引数のうち候補に当たらない名前だけを選び直し、問うた結果を順に返すことを保証する。"""

    def _tools(self) -> ActionTools:
        target = PickOne(
            name="target", label="相手", candidates=(Candidate(label="東の祭壇"), Candidate(label="西の祠"))
        )
        interact = ActionChoice(
            description="説明。",
            name="interact",
            label="操作する",
            outline=(ArgumentOutline(name="target", label="相手", required=True),),
            values=(target,),
        )
        return ActionTools(ActionChoices((interact,)), OfferedBeingTools(), lambda _: "誰か", recall_limit=3)

    def test_unmatched_name_is_replaced_and_its_rechoice_is_kept(self) -> None:
        """候補に無い「East Shrine」を東の祭壇に選び直すと、引数を置き換え、心の声を添えて問うた結果を 1 件返す。"""
        judging = _Judging(_answer("東の祭壇", 0.93, 0.9))

        matched = RechooseName(judging, min_confidence=0.85).match_names(
            self._tools(), tool_name="interact", arguments={"target": "East Shrine"}, inner_thought="祭壇へ向かう"
        )

        assert matched.arguments["target"] == "東の祭壇"
        assert [(r.original, r.replaced_with, r.tool) for r in matched.rechoices] == [
            ("East Shrine", "東の祭壇", "interact")
        ]
        assert judging.asked[0][0]["inner_thought"] == "祭壇へ向かう"

    def test_matching_name_is_not_asked_about(self) -> None:
        """候補に当たる名前は選び直しを問わず、引数はそのまま、問うた結果は無い。"""
        judging = _Judging(_answer("東の祭壇", 0.93, 0.9))

        matched = RechooseName(judging, min_confidence=0.85).match_names(
            self._tools(), tool_name="interact", arguments={"target": "西の祠"}, inner_thought=None
        )

        assert (matched.arguments["target"], matched.rechoices, judging.asked) == ("西の祠", (), [])
