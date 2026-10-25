"""memo の完了 hint を、文字の重なりでなく意味で出す。

## 文字の重なりでは 2 方向に外れる

現行は memo と action / result の共通部分文字列の割合が 0.6 以上で hint を出す。

- **言い換えられた memo を拾えない**: 「夕食の材料を集める」と書いて麦を
  刈り取っても、文字が重ならないので hint が出ない
- **失敗した行動でも誤検出する**: 「水を汲む」と書いて井戸で汲もうとし、桶が
  無くて汲めなかった場合も、文字が重なるので hint が出る (重なり 0.75)

Noul なら意味で判定できる。

## 1 回の呼び出しにまとめる

未完了 memo ごとに問うが、リクエストは 1 回にする。質問ごとに割ると state を
送り直すので、Noul 3 問で input tokens が 2.3 倍になる (実測 630 → 1,476)。

## 判断を得られなかったときは黙って諦めない

ポートが落ちたら現行の重なりの割合へ縮退する。ただし縮退したことを残す。
残さないと、hint が減った run を見て「意味判定が厳しすぎる」と誤読する。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Union

import pytest

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    NoulQuestion,
    Question,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services.memo_completion_hint_service import (
    MemoCompletionHintService,
    PendingTodo,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

_BEING = BeingId("being_w1_p1")


def _todos(contents: Sequence[str]) -> list[PendingTodo]:
    return [PendingTodo(id=f"memo-{i}", content=content, handle=f"m_{i}") for i, content in enumerate(contents)]


class _RecordingPort(ITypedJudgmentPort):
    """問われた内容を記録し、memo ごとに決めた確率を返す。"""

    def __init__(
        self,
        probabilities_by_content: Mapping[str, float] | None = None,
        *,
        raises: bool = False,
    ) -> None:
        self.calls: list[tuple[Any, Mapping[str, Question]]] = []
        self._by_content = dict(probabilities_by_content or {})
        self._raises = raises

    def judge(
        self,
        state: str | Mapping[str, Any] | Sequence[Any],
        questions: Mapping[str, Question],
    ) -> Mapping[str, JudgmentResult]:
        self.calls.append((state, questions))
        if self._raises:
            raise TypedJudgmentUnavailableException("down", error_code="TYPED_JUDGMENT_RATE_LIMITED")
        answers = {}
        for name, question in questions.items():
            assert isinstance(question, NoulQuestion)
            probability = 0.0
            for content, value in self._by_content.items():
                if content in question.instructions:
                    probability = value
                    break
            answers[name] = JudgmentResult(
                value=probability,
                probabilities={},
                confidence=None,
                source=JudgmentSource.JEV,
                latency_ms=88.0,
            )
        return answers


def _service(
    contents: Sequence[str],
    port: ITypedJudgmentPort | None,
    *,
    min_probability: float = 0.7,
) -> tuple[MemoCompletionHintService, list[PendingTodo]]:
    todos = _todos(contents)
    service = MemoCompletionHintService(
        pending_todos=lambda being_id: todos,
        judgment_port=port,
        min_probability=min_probability,
    )
    return service, todos


class TestMeaningCatchesWhatCharacterOverlapMisses:
    """言い換えを拾い、語の重なりだけの誤検出を止めることを保証する。"""

    def test_a_paraphrased_memo_is_hinted(self) -> None:
        """文字が重ならない言い換えでも、意味で達成と判断されれば hint が出る。"""
        service, _ = _service(["夕食の材料を集める"], _RecordingPort({"夕食の材料を集める": 0.88}))

        detection = service.detect(_BEING, "麦畑で麦を刈り取った", "小麦 3 束を得た")

        assert detection.hint is not None
        assert detection.hint.memo.content == "夕食の材料を集める"

    def test_a_paraphrased_memo_is_missed_by_character_overlap(self) -> None:
        """同じ場面を現行の重なり判定に掛けると hint が出ない (**現行との差**)。"""
        service, _ = _service(["夕食の材料を集める"], None)

        detection = service.detect(_BEING, "麦畑で麦を刈り取った", "小麦 3 束を得た")

        assert detection.hint is None

    def test_a_failed_attempt_is_not_hinted(self) -> None:
        """語が重なっても、達成していない行動では hint が出ない。"""
        service, _ = _service(["水を汲む"], _RecordingPort({"水を汲む": 0.05}))

        detection = service.detect(_BEING, "井戸で水を汲もうとした", "桶が見つからない")

        assert detection.hint is None

    def test_the_same_failure_would_have_fired_without_judgment(self) -> None:
        """同じ場面を現行の重なり判定に掛けると hint が出る (**現行との差**)。

        memo の文字が行動文にそのまま出るので、汲めていないのに達成扱いになる。
        """
        service, _ = _service(["水を汲む"], None)

        detection = service.detect(_BEING, "井戸で水を汲もうとした", "桶が見つからない")

        assert detection.hint is not None


class TestEveryUnfinishedMemoIsAskedInOneRequest:
    """未完了 memo をまとめて 1 回で問うことを保証する。"""

    def test_three_memos_are_asked_in_one_call(self) -> None:
        """memo 3 件でも呼び出しは 1 回で、質問は 3 件になる。"""
        port = _RecordingPort()
        service, _ = _service(["a を する", "b を する", "c を する"], port)

        service.detect(_BEING, "何かした", "何か起きた")

        assert len(port.calls) == 1
        _state, questions = port.calls[0]
        assert len(questions) == 3

    def test_no_unfinished_memo_means_no_call(self) -> None:
        """未完了 memo が 0 件ならポートを呼ばない。空の問い合わせに課金しない。"""
        port = _RecordingPort()
        service, _ = _service([], port)

        detection = service.detect(_BEING, "何かした", "何か起きた")

        assert port.calls == []
        assert detection.hint is None

    def test_an_empty_action_and_result_means_no_call(self) -> None:
        """行動も結果も空なら問わない。判断の材料が無い。"""
        port = _RecordingPort()
        service, _ = _service(["a を する"], port)

        service.detect(_BEING, "", "")

        assert port.calls == []

    def test_the_state_carries_the_action_and_result(self) -> None:
        """state に行動と結果が入る。"""
        port = _RecordingPort()
        service, _ = _service(["a を する"], port)

        service.detect(_BEING, "麦を刈り取った", "小麦を得た")

        state, _questions = port.calls[0]
        assert state["action"] == "麦を刈り取った"
        assert state["result"] == "小麦を得た"

    def test_the_state_carries_no_memo_ids(self) -> None:
        """state に memo の内部 ID を入れない (設計原則 1)。"""
        port = _RecordingPort()
        service, _ = _service(["a を する"], port)

        service.detect(_BEING, "麦を刈り取った", "小麦を得た")

        state, _questions = port.calls[0]
        assert "memo-0" not in repr(state)

    def test_each_question_names_its_own_memo(self) -> None:
        """質問ごとに、その memo の本文が入る。"""
        port = _RecordingPort()
        service, _ = _service(["鎌を研ぐ", "水を汲む"], port)

        service.detect(_BEING, "何かした", "何か起きた")

        _state, questions = port.calls[0]
        asked = [q.instructions for q in questions.values()]
        assert any("鎌を研ぐ" in text for text in asked)
        assert any("水を汲む" in text for text in asked)


class TestOnlyAConfidentJudgmentBecomesAHint:
    """確率が閾値以上のときだけ hint になることを保証する。"""

    def test_a_probability_below_the_threshold_does_not_hint(self) -> None:
        """閾値未満の確率では hint が出ない。"""
        service, _ = _service(["鎌を研ぐ"], _RecordingPort({"鎌を研ぐ": 0.6}))

        detection = service.detect(_BEING, "鎌を研いだ", "刃が鋭くなった")

        assert detection.hint is None

    def test_the_most_likely_memo_wins(self) -> None:
        """閾値を超えた memo が複数あれば、確率が最も高いものを選ぶ。"""
        service, _ = _service(
            ["鎌を研ぐ", "小麦を集める"],
            _RecordingPort({"鎌を研ぐ": 0.75, "小麦を集める": 0.93}),
        )

        detection = service.detect(_BEING, "麦を刈った", "小麦を得た")

        assert detection.hint is not None
        assert detection.hint.memo.content == "小麦を集める"

    def test_every_judgment_is_reported_with_its_verdict(self) -> None:
        """採否に関わらず、問うた memo すべての判断が返る。"""
        service, _ = _service(
            ["鎌を研ぐ", "小麦を集める"],
            _RecordingPort({"鎌を研ぐ": 0.1, "小麦を集める": 0.93}),
        )

        detection = service.detect(_BEING, "麦を刈った", "小麦を得た")

        verdicts = {j.memo_id: j.accepted for j in detection.judgments}
        assert verdicts == {"memo-0": False, "memo-1": True}
        assert all(j.min_probability == 0.7 for j in detection.judgments)


class _PartialAnswerPort(ITypedJudgmentPort):
    """先頭の質問にだけ答え、残りを返さないポート (契約違反)。"""

    def judge(
        self,
        state: str | Mapping[str, Any] | Sequence[Any],
        questions: Mapping[str, Question],
    ) -> Mapping[str, JudgmentResult]:
        first = next(iter(questions))
        return {
            first: JudgmentResult(
                value=0.1,
                probabilities={},
                confidence=None,
                source=JudgmentSource.JEV,
                latency_ms=10.0,
            )
        }


class TestAMissingAnswerIsNotReadAsUnfulfilled:
    """答えが欠けた memo を「まだ果たされていない」に読み替えないことを保証する。"""

    def test_a_partial_answer_falls_back_to_overlap(self) -> None:
        """一部の memo の答えが返らなければ、判断を使わず重なり判定へ縮退する。

        欠けを「果たされていない」と読むと、問うたのに答えが無い memo が黙って
        対象外になる。どの memo が判定されたのか分からなくなる。
        """
        service, _ = _service(["水を汲む", "鎌を研ぐ"], _PartialAnswerPort())

        detection = service.detect(_BEING, "井戸で水を汲もうとした", "桶が見つからない")

        assert detection.unavailable_reason == "TYPED_JUDGMENT_ANSWER_MISSING"
        assert detection.hint is not None
        assert detection.hint.source == "overlap"


class TestAnUnavailablePortFallsBackToOverlap:
    """判断を得られないとき、現行の重なり判定へ縮退することを保証する。"""

    def test_a_failing_port_falls_back_to_the_overlap_ratio(self) -> None:
        """ポートが落ちたら、従来の重なり判定で hint を出す。"""
        service, _ = _service(["水を汲む"], _RecordingPort(raises=True))

        detection = service.detect(_BEING, "井戸で水を汲もうとした", "桶が見つからない")

        assert detection.hint is not None
        assert detection.hint.source == "overlap"

    def test_the_fallback_is_reported(self) -> None:
        """縮退したことが理由つきで残る。hint が減った理由を後から追える。"""
        service, _ = _service(["水を汲む"], _RecordingPort(raises=True))

        detection = service.detect(_BEING, "井戸で水を汲もうとした", "桶が見つからない")

        assert detection.unavailable_reason == "TYPED_JUDGMENT_RATE_LIMITED"

    def test_without_a_port_nothing_is_reported_as_fallback(self) -> None:
        """ポートを持たない run は縮退ではない。理由を残さない (**正の対照**)。"""
        service, _ = _service(["水を汲む"], None)

        detection = service.detect(_BEING, "井戸で水を汲もうとした", "桶が見つからない")

        assert detection.unavailable_reason is None
        assert detection.judgments == ()


class TestTheHintTextKeepsItsShape:
    """hint 文の形が変わらず、数の意味だけが正しく書かれることを保証する。"""

    def test_the_overlap_hint_text_is_unchanged(self) -> None:
        """判断を使わない run の hint 文は現行のまま (「類似度」)。"""
        service, _ = _service(["水を汲む"], None)

        detection = service.detect(_BEING, "井戸で水を汲もうとした", "桶が見つからない")

        assert detection.hint is not None
        text = detection.hint.to_hint_text()
        assert "[hint] やること「水を汲む」" in text
        assert "類似度" in text
        assert "memo の remove で消してください" in text

    def test_the_judged_hint_text_says_it_is_a_probability(self) -> None:
        """判断由来の数は「類似度」と呼ばない。意味が違うものを同じ語で呼ばない。"""
        service, _ = _service(["小麦を集める"], _RecordingPort({"小麦を集める": 0.93}))

        detection = service.detect(_BEING, "麦を刈った", "小麦を得た")

        assert detection.hint is not None
        text = detection.hint.to_hint_text()
        assert "[hint] やること「小麦を集める」" in text
        assert "類似度" not in text
        assert "0.93" in text
