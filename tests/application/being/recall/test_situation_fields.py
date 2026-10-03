"""状況の欄 (Situation) と、選択肢ごとの確率の上位を残す欄の選び方 (FieldSelection) が、想起の問い合わせ文とマスクを決める挙動を保証する。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from ai_rpg_world.application.being.recall.situation import (
    DEGRADED_ANSWER_INVALID,
    DEGRADED_ANSWER_MISSING,
    DEGRADED_JUDGMENT_UNAVAILABLE,
    RECALL_FIELDS_QUESTION,
    FieldSelection,
    RecallMask,
    Situation,
    SituationField,
    field_selection_from_answers,
    field_selection_questions,
)
from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services.typed_judgment_stub import (
    DeterministicTypedJudgmentPort,
)

ASKED = (
    SituationField.COUNTERPART,
    SituationField.OWN_STATE,
    SituationField.INTENT,
    SituationField.HAPPENING,
    SituationField.UNRESOLVED,
)


def _situation() -> Situation:
    return Situation(
        place=("干潟",),
        counterpart=("トム",),
        own_state=("足を怪我している",),
        intent=("浜の奥を調べる",),
        happening=("大型のカニに挟まれた",),
        unresolved=("トムが麦束を焼いてくれる",),
    )


class TestSituation:
    """Situation が欄の値を、空でない文字列の並びだけで持つことを保証する。"""

    @pytest.mark.parametrize("text", ["", "  "])
    def test_rejects_blank_text(self, text: str) -> None:
        """欄の値に空文字や空白だけの文字列を渡すと ValueError を投げる。空と「欄の値が無い」を区別するため。"""
        with pytest.raises(ValueError):
            Situation(place=(text,))

    def test_rejects_non_text_value(self) -> None:
        """欄の値に整数を渡すと TypeError を投げる。ゲームの ID を欄に入れさせない。"""
        with pytest.raises(TypeError):
            Situation(place=(20,))  # type: ignore[arg-type]

    def test_rejects_list_instead_of_tuple(self) -> None:
        """欄に list を渡すと TypeError を投げる。作ったあとで欄の値が書き換わらないようにする。"""
        with pytest.raises(TypeError):
            Situation(place=["干潟"])  # type: ignore[arg-type]

    def test_omitted_fields_have_no_values(self) -> None:
        """渡さなかった欄は値を持たない。"""
        assert Situation(place=("干潟",)).texts(SituationField.COUNTERPART) == ()


class TestRecallMask:
    """RecallMask の問い合わせ文が、残した欄の値だけから組まれることを保証する。"""

    def test_query_joins_only_kept_field_values_in_field_order(self) -> None:
        """問い合わせ文は残した欄の値だけを、欄の決まった順 (場所が先) に並べる。"""
        mask = RecallMask(frozenset({SituationField.HAPPENING, SituationField.PLACE}))

        assert mask.query(_situation()) == "干潟\n大型のカニに挟まれた"

    def test_query_joins_every_value_of_a_field(self) -> None:
        """1 つの欄が複数の値を持てば、すべてを並んだ順に改行でつなぐ。"""
        mask = RecallMask(frozenset({SituationField.HAPPENING}))

        assert mask.query(Situation(happening=("雨が降った", "火が消えた"))) == "雨が降った\n火が消えた"

    def test_query_is_empty_when_kept_fields_have_no_values(self) -> None:
        """残した欄がどれも値を持たなければ、問い合わせ文は空になる。"""
        mask = RecallMask(frozenset({SituationField.COUNTERPART}))

        assert mask.query(Situation(place=("干潟",))) == ""


class TestFieldSelectionQuestions:
    """欄の選び方を Jev に問う質問の形を保証する。"""

    def test_asks_one_question_with_every_field_except_place_as_options(self) -> None:
        """場所を除く 5 つの欄を選択肢にした 1 問だけを、本人の名前を添えて問う。欄どうしを比べさせるため。"""
        questions = field_selection_questions("アリス")

        assert list(questions) == [RECALL_FIELDS_QUESTION]
        question = questions[RECALL_FIELDS_QUESTION]
        assert isinstance(question, ChoiceQuestion)
        assert list(question.options) == [f.value for f in ASKED]
        assert "アリス" in question.instructions


def _ranked(probabilities: dict[SituationField, float]) -> dict:
    answers = dict(
        DeterministicTypedJudgmentPort().judge({}, field_selection_questions("アリス"))
    )
    answers[RECALL_FIELDS_QUESTION] = replace(
        answers[RECALL_FIELDS_QUESTION],
        probabilities={f.value: probabilities.get(f, 0.0) for f in ASKED},
    )
    return answers


class TestFieldSelectionFromAnswers:
    """選択肢ごとの確率の上位を残し、判断が得られないときは全部の欄に縮退する挙動を保証する。"""

    def test_keeps_the_top_two_fields_by_probability(self) -> None:
        """確率の上位 2 つの欄だけを残し、縮退の理由は無い。確率の大きさは問わない (閾値を持たない)。"""
        answers = _ranked(
            {
                SituationField.COUNTERPART: 0.10,
                SituationField.OWN_STATE: 0.31,
                SituationField.INTENT: 0.12,
                SituationField.HAPPENING: 0.30,
                SituationField.UNRESOLVED: 0.17,
            }
        )

        selection = field_selection_from_answers(answers)

        assert selection.kept == frozenset({SituationField.OWN_STATE, SituationField.HAPPENING})
        assert selection.degraded_reason is None

    def test_keep_sets_how_many_fields_remain(self) -> None:
        """残す数に 1 を渡すと、いちばん確率の高い欄だけを残す。"""
        answers = _ranked({SituationField.INTENT: 0.4, SituationField.HAPPENING: 0.3})

        selection = field_selection_from_answers(answers, keep=1)

        assert selection.kept == frozenset({SituationField.INTENT})

    def test_ties_are_broken_by_field_order(self) -> None:
        """同じ確率の欄は、欄の決まった順で先のものを残す。答えが毎回同じ欄に決まるようにするため。"""
        answers = _ranked({f: 0.2 for f in ASKED})

        selection = field_selection_from_answers(answers)

        assert selection.kept == frozenset({SituationField.COUNTERPART, SituationField.OWN_STATE})

    @pytest.mark.parametrize("keep", [0, 6, True])
    def test_rejects_keep_outside_one_to_five(self, keep: int) -> None:
        """残す数が 1〜5 の整数でなければ ValueError を投げる。"""
        with pytest.raises(ValueError):
            field_selection_from_answers(_ranked({}), keep=keep)

    def test_records_each_field_probability_and_whether_it_was_kept(self) -> None:
        """欄ごとの確率と、残したかどうかと、出所を trace に載せる。"""
        answers = _ranked({SituationField.INTENT: 0.5, SituationField.HAPPENING: 0.3})

        payload = field_selection_from_answers(answers).to_trace_payload()

        assert [j["field"] for j in payload["judgments"]] == [f.value for f in ASKED]
        judgments = {j["field"]: j for j in payload["judgments"]}
        assert judgments["やろうとしていること"] == {
            "field": "やろうとしていること",
            "probability": 0.5,
            "kept": True,
            "source": "stub",
        }
        assert judgments["相手"]["kept"] is False

    @pytest.mark.parametrize("broken", [None, float("nan")])
    def test_degrades_to_all_fields_when_a_probability_is_not_a_number(self, broken: object) -> None:
        """確率が数でないか NaN の欄があれば、並べずに全部の欄を残す縮退になる。NaN で上位が静かに変わらないように。"""
        answers = _ranked({SituationField.INTENT: 0.5})
        probabilities = dict(answers[RECALL_FIELDS_QUESTION].probabilities)
        probabilities["相手"] = broken
        answers[RECALL_FIELDS_QUESTION] = replace(
            answers[RECALL_FIELDS_QUESTION], probabilities=probabilities
        )

        selection = field_selection_from_answers(answers)

        assert selection.kept == frozenset(ASKED)
        assert selection.degraded_reason == DEGRADED_ANSWER_INVALID

    def test_degrades_to_all_fields_when_the_answer_is_missing(self) -> None:
        """答えが欠けていれば、場所以外の全部の欄を残し、欠けたことを理由に持つ。"""
        answers = _ranked({})
        del answers[RECALL_FIELDS_QUESTION]

        selection = field_selection_from_answers(answers)

        assert selection.kept == frozenset(ASKED)
        assert selection.degraded_reason == DEGRADED_ANSWER_MISSING

    def test_degrades_to_all_fields_when_a_probability_is_missing(self) -> None:
        """確率が欠けた欄があれば、ほかの欄の確率を使わずに全部の欄を残す縮退になる。"""
        answers = _ranked({SituationField.INTENT: 0.5})
        probabilities = dict(answers[RECALL_FIELDS_QUESTION].probabilities)
        del probabilities["相手"]
        answers[RECALL_FIELDS_QUESTION] = replace(
            answers[RECALL_FIELDS_QUESTION], probabilities=probabilities
        )

        selection = field_selection_from_answers(answers)

        assert selection.kept == frozenset(ASKED)
        assert selection.degraded_reason == DEGRADED_ANSWER_INVALID
        assert "相手" in selection.degraded_detail

    def test_unavailable_judgment_degrades_with_error_code(self) -> None:
        """Jev が答えなかったときの例外は、全部の欄を残す縮退に変わり、エラーコードを詳しい理由に持つ。"""
        exc = TypedJudgmentUnavailableException("timed out", error_code="TYPED_JUDGMENT_TIMEOUT")

        selection = FieldSelection.unavailable(exc)

        assert selection.kept == frozenset(ASKED)
        assert selection.degraded_reason == DEGRADED_JUDGMENT_UNAVAILABLE
        assert "TYPED_JUDGMENT_TIMEOUT" in selection.degraded_detail

    def test_rejects_place_in_kept_fields(self) -> None:
        """場所は Jev に問わないので、残す欄に場所を入れると ValueError を投げる。"""
        with pytest.raises(ValueError):
            FieldSelection(kept=frozenset({SituationField.PLACE}))


class TestFieldSelectionMasks:
    """1 つの選び方から、場所を残した検索と捨てた検索の 2 本が必ず作られることを保証する。"""

    def test_masks_are_with_place_first_then_without_place(self) -> None:
        """マスクは「選んだ欄 + 場所」と「選んだ欄だけ」の 2 本で、場所を残した方が先。"""
        selection = FieldSelection(kept=frozenset({SituationField.INTENT}))

        with_place, without_place = selection.masks()

        assert with_place.kept == frozenset({SituationField.INTENT, SituationField.PLACE})
        assert without_place.kept == frozenset({SituationField.INTENT})

    def test_degraded_selection_still_searches_with_and_without_place(self) -> None:
        """縮退した選び方も、全部の欄を残したマスクに場所の有無の 2 本の検索を作る。"""
        selection = FieldSelection.degraded(DEGRADED_JUDGMENT_UNAVAILABLE)

        with_place, without_place = selection.masks()

        assert with_place.kept == frozenset(SituationField)
        assert without_place.kept == frozenset(ASKED)
