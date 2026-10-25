"""決定論 stub が、閾値を超えない「迷っている答え」を返す。

## なぜ値を固定するのか

stub は実 API を呼ばずに配線を確かめるために置く。ここで適当な値を返すと、
smoke run の結果が説明できなくなる。

呼び出し側の閾値は「確信があるときだけ採る」ために置く。そのため stub は
どちらにも寄らない答えを返し、**どの用途も閾値を超えず現行の振る舞いのまま
通る**ことを値の側から保証する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    JudgmentSource,
    NoulQuestion,
    ScoreQuestion,
)
from ai_rpg_world.application.llm.services.typed_judgment_stub import (
    DeterministicTypedJudgmentPort,
)


class TestTheStubAnswersWithoutLeaningEitherWay:
    """既定の答えが、どの用途の閾値も超えない側に寄ることを保証する。"""

    def test_a_noul_is_undecided_and_carries_no_confidence(self) -> None:
        """Noul は 0.5 を返し、confidence は None になる (Jev の Noul 応答と同じ形)。"""
        answers = DeterministicTypedJudgmentPort().judge(
            {"text": "麦を刈った"},
            {"done": NoulQuestion(instructions="memo は果たされたか")},
        )

        assert answers["done"].value == 0.5
        assert answers["done"].confidence is None
        assert answers["done"].probabilities == {}

    def test_a_choice_spreads_its_probability_evenly(self) -> None:
        """Choice は一様分布を返し、confidence は 1/選択肢数 になる。"""
        answers = DeterministicTypedJudgmentPort().judge(
            {"written": "gather"},
            {
                "rescue": ChoiceQuestion(
                    instructions="どの操作を意図したか",
                    options={"reap_wheat": "麦を刈る", "water_field": "水をやる"},
                )
            },
        )

        assert answers["rescue"].probabilities == {
            "reap_wheat": 0.5,
            "water_field": 0.5,
        }
        assert answers["rescue"].confidence == 0.5

    def test_a_score_lands_on_the_middle_level(self) -> None:
        """Score は段階の中央を返す。"""
        answers = DeterministicTypedJudgmentPort().judge(
            {"text": "落ち着いている"},
            {
                "urgency": ScoreQuestion(
                    instructions="切迫度",
                    levels=["落ち着いている", "気にかかる", "急を要する"],
                )
            },
        )

        assert answers["urgency"].value == 1.0

    def test_every_answer_is_labelled_as_coming_from_the_stub(self) -> None:
        """source が stub になり、実 API の結果と trace 上で区別できる。"""
        answers = DeterministicTypedJudgmentPort().judge(
            "麦を刈った", {"done": NoulQuestion(instructions="果たされたか")}
        )

        assert answers["done"].source is JudgmentSource.STUB
        assert answers["done"].latency_ms >= 0.0

    def test_the_question_names_come_back_unchanged(self) -> None:
        """渡した質問の名前が、そのまま答えのキーになる。"""
        answers = DeterministicTypedJudgmentPort().judge(
            "x",
            {
                "memo_0": NoulQuestion(instructions="a"),
                "memo_1": NoulQuestion(instructions="b"),
            },
        )

        assert set(answers) == {"memo_0", "memo_1"}


class TestTheStubCanBePinnedToAnAnswer:
    """テストが答えを固定できること、固定できない値は拒むことを保証する。"""

    def test_a_pinned_noul_is_returned_as_given(self) -> None:
        """answers に渡した Noul の値がそのまま返る。"""
        answers = DeterministicTypedJudgmentPort({"done": 0.93}).judge(
            "x", {"done": NoulQuestion(instructions="果たされたか")}
        )

        assert answers["done"].value == 0.93

    def test_a_pinned_choice_is_returned_as_given(self) -> None:
        """answers に渡した選択肢名がそのまま選ばれる。"""
        answers = DeterministicTypedJudgmentPort({"rescue": "water_field"}).judge(
            "x",
            {
                "rescue": ChoiceQuestion(
                    instructions="どれか",
                    options={"reap_wheat": None, "water_field": None},
                )
            },
        )

        assert answers["rescue"].value == "water_field"

    def test_a_pinned_choice_outside_the_options_is_rejected(self) -> None:
        """選択肢に無い名前を固定しようとすると ValueError になる。

        世界に無い操作を stub が作れると、配線テストが実際には起こり得ない
        経路を緑にしてしまう。
        """
        with pytest.raises(ValueError):
            DeterministicTypedJudgmentPort({"rescue": "gather"}).judge(
                "x",
                {"rescue": ChoiceQuestion(instructions="どれか", options={"reap_wheat": None})},
            )

    def test_a_pinned_score_level_name_is_accepted(self) -> None:
        """段階の名前で固定すると、その段階の番号が返る。"""
        answers = DeterministicTypedJudgmentPort({"urgency": "急を要する"}).judge(
            "x",
            {
                "urgency": ScoreQuestion(
                    instructions="切迫度",
                    levels=["落ち着いている", "気にかかる", "急を要する"],
                )
            },
        )

        assert answers["urgency"].value == 2.0

    def test_a_choice_without_options_is_rejected(self) -> None:
        """選択肢が空の Choice は ValueError になる (問えない質問を黙って通さない)。"""
        with pytest.raises(ValueError):
            DeterministicTypedJudgmentPort().judge("x", {"rescue": ChoiceQuestion(instructions="どれか", options={})})
