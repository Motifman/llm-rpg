"""目的を達成したかもしれないとき、Jev の判定で本人に知らせる (#1448)。

目的の清算は本人の申告 (`goal_outcome`) のままにする。規則で達成・断念を推定
すると誤った材料が信念に流れるので、その案は捨てた
(docs/memory_system/unified_memory_phase2_implementation_plan.md の P8)。

一方で、達成したのに申告し忘れると、目的が残り続けて行動を縛る。memo と同じ
形で「達成したかもしれない」と知らせ、清算するかは本人に任せる。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

import pytest

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    NoulQuestion,
    Question,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services.goal_completion_hint_service import (
    GoalCompletionHintService,
)
from ai_rpg_world.application.llm.services.in_memory_goal_journal_store import (
    InMemoryGoalJournalStore,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.goal.value_object.goal_entry import (
    GOAL_ORIGIN_SCENARIO,
    GOAL_ORIGIN_SELF,
    GOAL_STATUS_ACHIEVED,
    GOAL_STATUS_ACTIVE,
    GoalEntry,
)

_BEING = BeingId("being_w1_p1")


def _goal(
    goal_id: str,
    text: str,
    *,
    status: str = GOAL_STATUS_ACTIVE,
    locked: bool = False,
) -> GoalEntry:
    return GoalEntry(
        goal_id=goal_id,
        player_id=1,
        text=text,
        status=status,
        locked=locked,
        origin=GOAL_ORIGIN_SCENARIO if locked else GOAL_ORIGIN_SELF,
        created_tick=1,
        created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )


class _RecordingPort(ITypedJudgmentPort):
    """問われた内容を記録し、目的の文ごとに決めた確率を返す。"""

    def __init__(
        self,
        probabilities_by_text: Mapping[str, float] | None = None,
        *,
        raises: bool = False,
        drop_answers: bool = False,
    ) -> None:
        self.calls: list[tuple[Any, Mapping[str, Question]]] = []
        self._by_text = dict(probabilities_by_text or {})
        self._raises = raises
        self._drop_answers = drop_answers

    def judge(
        self,
        state: str | Mapping[str, Any] | Sequence[Any],
        questions: Mapping[str, Question],
    ) -> Mapping[str, JudgmentResult]:
        self.calls.append((state, questions))
        if self._raises:
            raise TypedJudgmentUnavailableException(
                "down", error_code="TYPED_JUDGMENT_RATE_LIMITED"
            )
        if self._drop_answers:
            return {}
        answers = {}
        for name, question in questions.items():
            assert isinstance(question, NoulQuestion)
            probability = 0.0
            for text, value in self._by_text.items():
                if text in question.instructions:
                    probability = value
                    break
            answers[name] = JudgmentResult(
                value=probability,
                probabilities={},
                confidence=None,
                source=JudgmentSource.JEV,
                latency_ms=91.0,
            )
        return answers


def _service(
    goals: Sequence[GoalEntry],
    port: ITypedJudgmentPort,
    *,
    min_probability: float = 0.7,
) -> tuple[GoalCompletionHintService, InMemoryGoalJournalStore]:
    store = InMemoryGoalJournalStore()
    for goal in goals:
        store.add_by_being(_BEING, goal)
    return (
        GoalCompletionHintService(
            goal_store=store, judgment_port=port, min_probability=min_probability
        ),
        store,
    )


class TestEveryOpenGoalIsAskedInOneRequest:
    """未達成の目的をまとめて 1 回で問うことを保証する。"""

    def test_two_open_goals_are_asked_in_one_call(self) -> None:
        """未達成の目的が 2 件あるとき、Jev を 1 回だけ呼び、質問は 2 件になる。"""
        port = _RecordingPort()
        service, _ = _service(
            [_goal("g1", "斧を手に入れる"), _goal("g2", "倉庫の鍵を開ける")], port
        )

        service.detect(_BEING, "倉庫で斧を拾った", "斧を手に入れた")

        assert len(port.calls) == 1
        _, questions = port.calls[0]
        assert len(questions) == 2

    def test_the_state_carries_the_action_and_the_result_but_no_goal_id(self) -> None:
        """判断の材料は行動と結果で、目的の内部 ID は質問にも材料にも入らない。"""
        port = _RecordingPort()
        service, _ = _service([_goal("goal-internal-7f3a", "斧を手に入れる")], port)

        service.detect(_BEING, "倉庫で斧を拾った", "斧を手に入れた")

        state, questions = port.calls[0]
        assert state == {"action": "倉庫で斧を拾った", "result": "斧を手に入れた"}
        assert "goal-internal-7f3a" not in repr(state)
        assert "goal-internal-7f3a" not in repr(questions)
        (question,) = questions.values()
        assert isinstance(question, NoulQuestion)
        assert "斧を手に入れる" in question.instructions

    def test_no_open_goal_means_no_call(self) -> None:
        """未達成の目的が無いときは Jev を呼ばず、hint も出ない。"""
        port = _RecordingPort()
        service, _ = _service(
            [_goal("g1", "斧を手に入れる", status=GOAL_STATUS_ACHIEVED)], port
        )

        detection = service.detect(_BEING, "倉庫で斧を拾った", "斧を手に入れた")

        assert port.calls == []
        assert detection.hints == ()
        assert detection.judgments == ()

    def test_a_goal_the_scenario_locked_is_not_asked(self) -> None:
        """シナリオが固定した目的は goal_outcome で清算できないので問わない。

        問えば、拒否される申告を勧めることになる。
        """
        port = _RecordingPort({"島から脱出する": 0.95})
        service, _ = _service([_goal("g1", "島から脱出する", locked=True)], port)

        detection = service.detect(_BEING, "筏で漕ぎ出した", "沖へ出た")

        assert port.calls == []
        assert detection.hints == ()


class TestOnlyLikelyGoalsAreHinted:
    """確率が閾値以上の目的にだけ hint を出すことを保証する。"""

    def test_only_the_goal_above_the_threshold_gets_a_hint(self) -> None:
        """閾値 0.7 で 0.9 と 0.3 の目的があるとき、0.9 の目的にだけ hint が付く。"""
        port = _RecordingPort({"斧を手に入れる": 0.9, "倉庫の鍵を開ける": 0.3})
        service, _ = _service(
            [_goal("g1", "斧を手に入れる"), _goal("g2", "倉庫の鍵を開ける")], port
        )

        detection = service.detect(_BEING, "倉庫で斧を拾った", "斧を手に入れた")

        assert [hint.goal.goal_id for hint in detection.hints] == ["g1"]

    def test_a_probability_equal_to_the_threshold_is_hinted(self) -> None:
        """確率が閾値ちょうどなら hint を出す。"""
        port = _RecordingPort({"斧を手に入れる": 0.7})
        service, _ = _service([_goal("g1", "斧を手に入れる")], port)

        detection = service.detect(_BEING, "倉庫で斧を拾った", "斧を手に入れた")

        assert len(detection.hints) == 1

    def test_every_judgment_is_kept_whether_or_not_it_was_hinted(self) -> None:
        """採らなかった目的の判断も、確率・閾値・採否とともに残る。"""
        port = _RecordingPort({"斧を手に入れる": 0.9, "倉庫の鍵を開ける": 0.3})
        service, _ = _service(
            [_goal("g1", "斧を手に入れる"), _goal("g2", "倉庫の鍵を開ける")], port
        )

        detection = service.detect(_BEING, "倉庫で斧を拾った", "斧を手に入れた")

        by_goal = {judgment.goal_id: judgment for judgment in detection.judgments}
        assert by_goal["g1"].accepted is True
        assert by_goal["g2"].accepted is False
        assert by_goal["g2"].probability == pytest.approx(0.3)
        assert by_goal["g2"].min_probability == pytest.approx(0.7)
        assert by_goal["g2"].source == "jev"
        assert detection.unavailable_reason is None

    def test_the_hint_text_names_the_goal_and_goal_outcome(self) -> None:
        """hint の文は目的の文を引き、goal_outcome で記録するよう促す。"""
        port = _RecordingPort({"斧を手に入れる": 0.9})
        service, _ = _service([_goal("g1", "斧を手に入れる")], port)

        (hint,) = service.detect(_BEING, "倉庫で斧を拾った", "斧を手に入れた").hints

        assert hint.to_hint_text() == (
            "\n\n[hint] 目的「斧を手に入れる」は達成したかもしれない。"
            "達成したなら goal_outcome で記録する。"
        )


class TestTheGoalIsLeftToItsOwner:
    """hint を出しても目的の状態を変えないことを保証する。"""

    def test_a_hinted_goal_stays_active(self) -> None:
        """確率が閾値以上で hint を出しても、目的は active のまま残る。"""
        port = _RecordingPort({"斧を手に入れる": 0.99})
        service, store = _service([_goal("g1", "斧を手に入れる")], port)

        detection = service.detect(_BEING, "倉庫で斧を拾った", "斧を手に入れた")

        assert len(detection.hints) == 1
        (goal,) = store.list_all_by_being(_BEING)
        assert goal.status == GOAL_STATUS_ACTIVE


class TestNoHintWithoutAJudgment:
    """判断が得られないときは hint を出さず、理由を残すことを保証する。"""

    def test_an_unavailable_port_gives_no_hint_and_a_reason(self) -> None:
        """Jev が例外を投げたら hint を出さず、例外の error_code を理由に残す。"""
        port = _RecordingPort(raises=True)
        service, _ = _service([_goal("g1", "斧を手に入れる")], port)

        detection = service.detect(_BEING, "倉庫で斧を拾った", "斧を手に入れた")

        assert detection.hints == ()
        assert detection.judgments == ()
        assert detection.unavailable_reason == "TYPED_JUDGMENT_RATE_LIMITED"

    def test_a_missing_answer_is_not_read_as_not_achieved(self) -> None:
        """答えが欠けていたら「達成していない」に読み替えず、判断なしとして理由を残す。"""
        port = _RecordingPort(drop_answers=True)
        service, _ = _service([_goal("g1", "斧を手に入れる")], port)

        detection = service.detect(_BEING, "倉庫で斧を拾った", "斧を手に入れた")

        assert detection.hints == ()
        assert detection.judgments == ()
        assert detection.unavailable_reason == "TYPED_JUDGMENT_ANSWER_MISSING"


class TestTheThresholdIsValidated:
    """閾値の範囲外を構築時に止めることを保証する。"""

    @pytest.mark.parametrize("value", [0.0, -0.1, 1.5])
    def test_a_threshold_outside_the_unit_interval_is_rejected(
        self, value: float
    ) -> None:
        """閾値が (0, 1] の外なら ValueError になる。黙って丸めない。"""
        with pytest.raises(ValueError, match="min_probability"):
            GoalCompletionHintService(
                goal_store=InMemoryGoalJournalStore(),
                judgment_port=_RecordingPort(),
                min_probability=value,
            )
