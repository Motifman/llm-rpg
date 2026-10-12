"""TargetItemNameRescue が、名前の重なりで当たらなかった品名を、相手の所持品から意味で選び直す挙動を保証する。

対象名の救済 (target_label_rescue.py) と同じ形。「該当なし」を必ず選択肢に入れ、確率と確信の
両方が下限に届いたときだけ採る。判断が得られなかったときは、採らず「どれでもない」とも言わない。
Issue #1641、design_decisions D1641。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services._argument_resolvers.target_item_name_rescue import (
    NO_MATCH_OPTION,
    QUESTION_NAME,
    TargetItemNameRescue,
)
from ai_rpg_world.application.llm.services.typed_judgment_stub import DeterministicTypedJudgmentPort

_CANDIDATES = {"昇降機の起動鍵": "鉄でできた太い鍵。", "燃料の缶": "燃料の入った缶。"}


class _FixedPort(ITypedJudgmentPort):
    def __init__(self, choice: str, probability: float = 0.95, confidence: float | None = 0.9) -> None:
        self.choice, self.probability, self.confidence = choice, probability, confidence
        self.calls: list[tuple[Any, Mapping[str, Any]]] = []

    def judge(self, state, questions):
        self.calls.append((state, dict(questions)))
        return {
            name: JudgmentResult(
                value=self.choice, probabilities={self.choice: self.probability},
                confidence=self.confidence, source=JudgmentSource.JEV, latency_ms=7.0,
            )
            for name in questions
        }


class _FailingPort(ITypedJudgmentPort):
    def judge(self, state, questions):
        raise TypedJudgmentUnavailableException("down", error_code="TYPED_JUDGMENT_TRANSPORT_FAILED")


def _rescue(port: ITypedJudgmentPort, written: str = "鉄の鍵"):
    return TargetItemNameRescue(port=port, min_confidence=0.85).rescue(
        written, candidates=_CANDIDATES, action_name="pickpocket",
    )


class TestChoosingACandidate:
    """候補を選んだ答えの採否。"""

    def test_a_confident_choice_is_accepted(self) -> None:
        """確率 0.95・確信 0.9 で「昇降機の起動鍵」を選べば、採る。"""
        answer = _rescue(_FixedPort("昇降機の起動鍵"))

        assert (answer.chosen, answer.accepted) == ("昇降機の起動鍵", True)

    def test_a_choice_below_the_threshold_is_not_accepted(self) -> None:
        """確信が下限 0.85 に届かなければ、選んだ候補を採らない。"""
        answer = _rescue(_FixedPort("昇降機の起動鍵", confidence=0.6))

        assert (answer.chosen, answer.accepted, answer.confident_no_match) == ("昇降機の起動鍵", False, False)

    def test_the_payload_records_what_was_written_and_what_replaced_it(self) -> None:
        """trace の値に、書かれた名前・置き換えた名前・確率・確信・下限が入る。"""
        answer = _rescue(_FixedPort("昇降機の起動鍵"))

        assert {k: answer.payload[k] for k in ("original", "replaced_with", "probability", "confidence", "min_confidence", "source")} == {
            "original": "鉄の鍵", "replaced_with": "昇降機の起動鍵", "probability": 0.95,
            "confidence": 0.9, "min_confidence": 0.85, "source": "jev",
        }


class TestNoCandidate:
    """「どれでもない」と答えたときと、答えが得られなかったとき。"""

    def test_a_confident_no_match_says_so(self) -> None:
        """確信をもって「該当なし」を選べば、候補を選ばず「どれでもない」と確かに言える。"""
        answer = _rescue(_FixedPort(NO_MATCH_OPTION))

        assert (answer.chosen, answer.accepted, answer.confident_no_match) == (None, False, True)

    def test_an_unconfident_no_match_is_not_certain(self) -> None:
        """「該当なし」でも確信が足りなければ、「どれでもない」とは言い切らない。"""
        answer = _rescue(_FixedPort(NO_MATCH_OPTION, probability=0.5, confidence=0.5))

        assert (answer.chosen, answer.confident_no_match) == (None, False)

    def test_an_unavailable_judge_neither_chooses_nor_denies(self) -> None:
        """判断器に届かなければ、候補を選ばず「どれでもない」とも言わず、理由を trace の値に残す。"""
        answer = _rescue(_FailingPort())

        assert (answer.accepted, answer.confident_no_match) == (False, False)
        assert answer.payload["unavailable_reason"] == "TYPED_JUDGMENT_TRANSPORT_FAILED"

    def test_the_stub_judge_neither_chooses_nor_denies(self) -> None:
        """実 API を呼ばない stub の判断は確率が均等なので、候補を採らず「どれでもない」とも言わない。"""
        answer = _rescue(DeterministicTypedJudgmentPort())

        assert (answer.accepted, answer.confident_no_match) == (False, False)


class TestWhatTheJudgeIsAsked:
    """判断器に渡す問い。"""

    def test_the_question_offers_the_held_items_and_no_match(self) -> None:
        """選択肢は相手の所持品の名前と説明、それに「該当なし」で、状態に書かれた名前と操作名が入る。"""
        port = _FixedPort(NO_MATCH_OPTION)

        _rescue(port)

        [(state, questions)] = port.calls
        assert (state["written_item_name"], state["action_name"]) == ("鉄の鍵", "pickpocket")
        assert set(questions[QUESTION_NAME].options) == {*_CANDIDATES, NO_MATCH_OPTION}
        assert questions[QUESTION_NAME].options["昇降機の起動鍵"] == "鉄でできた太い鍵。"
