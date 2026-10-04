"""目的の達成 hint サービス (#1448)。

行動の結果が返ったあと、未達成の目的ごとに「この行動と結果で達成されたか」を
判断ポートに問い、確率が閾値以上の目的について「達成したかもしれない」と
本人に知らせる。

## 清算は本人がする

目的の状態は変えない。規則で達成・断念を推定する案は、誤った材料が信念に
流れるので捨てた (docs/memory_system/unified_memory_phase2_implementation_plan.md
の P8)。hint を見て ``goal_outcome`` で申告するかは本人が決める。

## シナリオが固定した目的は問わない

``locked`` の目的への ``goal_outcome`` は拒否される。問えば、拒否される申告を
勧めることになる。

## 判断が無ければ hint も無い

memo の hint と違い、縮退先の規則を持たない。文字の重なりで目的の達成を
推すと、捨てた規則推定と同じ誤りを本人に勧めることになる。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ITypedJudgmentPort,
    NoulQuestion,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.goal.repository.goal_journal_repository import (
    GoalJournalRepository,
)
from ai_rpg_world.domain.memory.goal.value_object.goal_entry import (
    GOAL_STATUS_ACTIVE,
    GoalEntry,
)

#: trace と呼び出し側の分岐に使う質問名。
QUESTION_NAME = "goal_achieved"

#: 問える目的が無いので見送った理由。trace の ``skipped_reason`` に載る (#1448)。
SKIPPED_NO_ACTIVE_GOAL = "no_active_goal"
SKIPPED_ONLY_LOCKED_GOALS = "only_locked_goals"


@dataclass(frozen=True)
class GoalCompletionHint:
    """達成した可能性がある目的 1 件。"""

    goal: GoalEntry
    probability: float

    def to_hint_text(self) -> str:
        """結果の文に添える hint 文を返す。"""
        return (
            f"\n\n[hint] 目的「{self.goal.text}」は達成したかもしれない。"
            "達成したなら goal_outcome で記録する。"
        )


@dataclass(frozen=True)
class GoalCompletionJudgment:
    """目的 1 件について「達成されたか」を問うた結果。採らなかった判断も残す。"""

    goal_id: str
    probability: float
    min_probability: float
    accepted: bool
    latency_ms: float | None = None
    source: str | None = None


@dataclass(frozen=True)
class GoalHintDetection:
    """1 回の検出で起きたこと。

    Attributes:
        hints: 出す hint。閾値以上の目的ごとに 1 件
        judgments: 問うた目的ごとの判断。問わなかったときは空
        unavailable_reason: 判断を得られなかった理由。得られたときは None
        skipped_reason: 問える目的が無く、判断を求めなかった理由。求めたときは None
    """

    hints: tuple[GoalCompletionHint, ...] = ()
    judgments: tuple[GoalCompletionJudgment, ...] = ()
    unavailable_reason: str | None = None
    skipped_reason: str | None = None


class GoalCompletionHintService:
    """行動の結果に添える目的の達成 hint を生成する。detect は目的を書き換えない。"""

    def __init__(
        self,
        goal_store: GoalJournalRepository,
        *,
        judgment_port: ITypedJudgmentPort,
        min_probability: float,
    ) -> None:
        if not isinstance(goal_store, GoalJournalRepository):
            raise TypeError("goal_store must be GoalJournalRepository")
        if not isinstance(judgment_port, ITypedJudgmentPort):
            raise TypeError("judgment_port must be ITypedJudgmentPort")
        if not isinstance(min_probability, (int, float)):
            raise TypeError("min_probability must be a number")
        if not 0.0 < float(min_probability) <= 1.0:
            raise ValueError("min_probability must be in (0, 1]")
        self._goal_store = goal_store
        #: 公開するのは、配線が組まれたかを外から確かめられるようにするため。
        self.judgment_port = judgment_port
        self.min_probability = float(min_probability)

    def detect(
        self,
        being_id: BeingId,
        action_summary: str,
        result_summary: str,
    ) -> GoalHintDetection:
        """未達成の目的のうち、達成した可能性が閾値以上のものの hint を返す。

        1 件でも答えが得られなければ、全体を判断なしとして扱う。目的を 1 回の
        呼び出しで問うので、欠けた答えは同じ呼び出しの他の答えの信頼も損なう。
        """
        active = [
            goal
            for goal in self._goal_store.list_all_by_being(being_id)
            if goal.status == GOAL_STATUS_ACTIVE
        ]
        goals = [goal for goal in active if not goal.locked]
        if not goals:
            return GoalHintDetection(
                skipped_reason=(
                    SKIPPED_ONLY_LOCKED_GOALS if active else SKIPPED_NO_ACTIVE_GOAL
                )
            )
        try:
            return self._by_judgment(goals, action_summary, result_summary)
        except TypedJudgmentUnavailableException as exc:
            return GoalHintDetection(
                unavailable_reason=exc.error_code
            )

    def _by_judgment(
        self,
        goals: list[GoalEntry],
        action_summary: str,
        result_summary: str,
    ) -> GoalHintDetection:
        # 質問のキーを連番にするのは、目的の内部 ID を判断の語彙に混ぜないため (設計原則 1)。
        by_key: dict[str, GoalEntry] = {
            f"{QUESTION_NAME}_{index}": goal for index, goal in enumerate(goals)
        }
        questions = {
            key: NoulQuestion(
                instructions=(
                    f"この行動と結果で、目的「{goal.text}」は達成されたか。"
                ),
                true_means="達成された",
                false_means="まだ達成されていない",
            )
            for key, goal in by_key.items()
        }
        answers = self.judgment_port.judge(
            _state(action_summary, result_summary), questions
        )

        judgments: list[GoalCompletionJudgment] = []
        hints: list[GoalCompletionHint] = []
        for key, goal in by_key.items():
            answer = answers.get(key)
            if answer is None:
                raise TypedJudgmentUnavailableException(
                    f"goal completion answer missing for {key!r}",
                    error_code="TYPED_JUDGMENT_ANSWER_MISSING",
                )
            try:
                probability = float(answer.value)
            except (TypeError, ValueError) as exc:
                raise TypedJudgmentUnavailableException(
                    f"goal completion answer is not a probability for {key!r}",
                    error_code="TYPED_JUDGMENT_ANSWER_INVALID",
                    cause=exc,
                ) from exc
            accepted = probability >= self.min_probability
            judgments.append(
                GoalCompletionJudgment(
                    goal_id=goal.goal_id,
                    probability=probability,
                    min_probability=self.min_probability,
                    accepted=accepted,
                    latency_ms=answer.latency_ms,
                    source=answer.source.value,
                )
            )
            if accepted:
                hints.append(GoalCompletionHint(goal=goal, probability=probability))
        return GoalHintDetection(hints=tuple(hints), judgments=tuple(judgments))


def _state(action_summary: str, result_summary: str) -> Mapping[str, Any]:
    return {"action": action_summary, "result": result_summary}


__all__ = [
    "GoalCompletionHint",
    "GoalCompletionHintService",
    "GoalCompletionJudgment",
    "GoalHintDetection",
    "QUESTION_NAME",
    "SKIPPED_NO_ACTIVE_GOAL",
    "SKIPPED_ONLY_LOCKED_GOALS",
]
