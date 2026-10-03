"""信念を作る直前に、形と同じ意味の既存の信念を Jev に問う (#1453)。

信念を固める LLM が「作る」を選んでも、そのまま作ると 2 つの形で外れる。

- **同じ内容が重複する**: 既存の信念の候補を cue の一致で選んでいたので、
  同じ内容の信念が候補に入らず「作る」が選ばれた。過去の snapshot で、文字の
  上でよく似た組が 96 組、まったく同じ文の組が 14 組あった
- **いまの状況が信念になる**: 「ノアとリオは干潟に向かっている」のような
  数ターンで古くなる状態が信念として残る。LLM への指示で守らせきれない

そこで作る直前に、同じ state で 2 つを 1 回の呼び出しで問う。

- 形: 世界の決まり / 他者の性質 / 場所の状態 / 行動の方針 / いまの状況
- 同じ意味: 文だけで絞った既存の信念の上位 K 件 / 該当なし

## 確信度が閾値に届かない答えでは振る舞いを変えない

閾値は profile から受ける。決定論 stub は迷った答え (Choice の確信度
``1 / 選択肢数``) を返すので、stub を挟んだ run は作るをそのまま通す。
「該当なし」を選択肢の先頭に置くのも同じ理由で、stub は先頭を選ぶ。

## 判断が得られないときは作るを通す

縮退先は LLM が選んだ「作る」。縮退したことは ``unavailable_reason`` に残す
(design_decisions #5)。Jev は選ぶだけで、信念の文は変えない。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    ITypedJudgmentPort,
    JudgmentResult,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.application.llm.services.text_candidate_narrowing import (
    ITextCandidateNarrower,
    RankedCandidate,
    TextCandidate,
)

logger = logging.getLogger(__name__)

SHAPE_QUESTION = "belief_shape"
SAME_MEANING_QUESTION = "belief_same_meaning"

SHAPE_CURRENT_SITUATION = "いまの状況"
NO_SAME_MEANING = "該当なし"

OUTCOME_CREATE = "create"
OUTCOME_STRENGTHEN = "strengthen"
OUTCOME_SKIP_CURRENT_SITUATION = "skip_current_situation"

_UNAVAILABLE_ANSWER_INVALID = "TYPED_JUDGMENT_ANSWER_INVALID"
_UNAVAILABLE_ANSWER_MISSING = "TYPED_JUDGMENT_ANSWER_MISSING"
_UNAVAILABLE_UNEXPECTED = "UNEXPECTED_ERROR"

# 「いまの状況」を先頭に置かない。stub は先頭を選ぶ。
_SHAPE_OPTIONS: Mapping[str, str] = {
    "世界の決まり": "この世界で繰り返し成り立つ仕組みや因果 (例: 湿った薪は燃えにくい)",
    "他者の性質": "特定の人物の性格・能力・傾向 (例: カイは約束を守る)",
    "場所の状態": "ある場所に続いてある性質 (例: 東の崖は足場が悪い)",
    "行動の方針": "自分がどう振る舞うとよいかの方針 (例: 嵐の前に食料を蓄える)",
    SHAPE_CURRENT_SITUATION: (
        "数ターンで変わる、いまこの時の状態・予定・誰がどこで何をしているか"
        " (例: カイは森へ向かっている、出口がまだ見つからない)"
    ),
}


@dataclass(frozen=True)
class BeliefCreateReview:
    """作る前に問うた結果。採らなかった答えも残す。

    Attributes:
        outcome: ``create`` / ``strengthen`` / ``skip_current_situation``
        target_key: ``strengthen`` のとき強める既存の信念の key
        unavailable_reason: 判断を得られず作るを通した理由。判断が得られたら None
    """

    text: str
    candidates: tuple[RankedCandidate, ...]
    outcome: str
    target_key: str | None
    narrower: str
    top_k: int
    min_confidence: float
    shape: str | None = None
    shape_confidence: float | None = None
    shape_probabilities: Mapping[str, float] | None = None
    same_meaning: str | None = None
    same_meaning_confidence: float | None = None
    same_meaning_probabilities: Mapping[str, float] | None = None
    unavailable_reason: str | None = None
    latency_ms: float | None = None
    source: str | None = None

    def as_trace_payload(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "candidates": [
                {"key": c.key, "text": c.text, "score": round(c.score, 4)}
                for c in self.candidates
            ],
            "shape": self.shape,
            "shape_confidence": self.shape_confidence,
            "shape_probabilities": _rounded(self.shape_probabilities),
            "same_meaning": self.same_meaning,
            "same_meaning_confidence": self.same_meaning_confidence,
            "same_meaning_probabilities": _rounded(self.same_meaning_probabilities),
            "outcome": self.outcome,
            "target_key": self.target_key,
            "unavailable_reason": self.unavailable_reason,
            "narrower": self.narrower,
            "top_k": self.top_k,
            "min_confidence": self.min_confidence,
            "latency_ms": self.latency_ms,
            "source": self.source,
        }


class BeliefCreateGate:
    """新しい信念の文と既存の信念を受け、作る / 強める / 作らないを決める。"""

    def __init__(
        self,
        *,
        judgment_port: ITypedJudgmentPort,
        narrower: ITextCandidateNarrower,
        top_k: int,
        min_confidence: float,
    ) -> None:
        if not isinstance(judgment_port, ITypedJudgmentPort):
            raise TypeError("judgment_port must be ITypedJudgmentPort")
        if not isinstance(narrower, ITextCandidateNarrower):
            raise TypeError("narrower must be ITextCandidateNarrower")
        if not isinstance(top_k, int) or top_k < 1:
            raise ValueError("top_k must be int >= 1")
        if not 0.0 < float(min_confidence) <= 1.0:
            raise ValueError("min_confidence must be in (0, 1]")
        self._port = judgment_port
        self._narrower = narrower
        self._top_k = top_k
        self._min_confidence = float(min_confidence)

    def review(
        self, text: str, existing: Sequence[TextCandidate]
    ) -> BeliefCreateReview:
        candidates = _distinct_texts(
            self._narrower.narrow(text, existing, top_k=self._top_k)
        )
        base = {
            "text": text,
            "candidates": candidates,
            "narrower": self._narrower.name,
            "top_k": self._top_k,
            "min_confidence": self._min_confidence,
        }
        questions: dict[str, ChoiceQuestion] = {SHAPE_QUESTION: _shape_question()}
        if candidates:
            questions[SAME_MEANING_QUESTION] = _same_meaning_question(candidates)
        try:
            answers = self._port.judge({"new_belief": text}, questions)
            shape = _answer(answers, SHAPE_QUESTION, questions[SHAPE_QUESTION])
            same = (
                _answer(
                    answers, SAME_MEANING_QUESTION, questions[SAME_MEANING_QUESTION]
                )
                if SAME_MEANING_QUESTION in questions
                else None
            )
        except TypedJudgmentUnavailableException as exc:
            return BeliefCreateReview(
                **base,
                outcome=OUTCOME_CREATE,
                target_key=None,
                unavailable_reason=getattr(exc, "error_code", None) or "UNAVAILABLE",
            )
        except Exception:
            # ここから漏れると、呼び出し側は作るを適用できずに学びを落とす。
            logger.exception("belief create gate judgment failed")
            return BeliefCreateReview(
                **base,
                outcome=OUTCOME_CREATE,
                target_key=None,
                unavailable_reason=_UNAVAILABLE_UNEXPECTED,
            )

        outcome, target_key = self._decide(shape, same, candidates)
        return BeliefCreateReview(
            **base,
            outcome=outcome,
            target_key=target_key,
            shape=shape.value,
            shape_confidence=shape.confidence,
            shape_probabilities=shape.probabilities,
            same_meaning=same.value if same is not None else None,
            same_meaning_confidence=same.confidence if same is not None else None,
            same_meaning_probabilities=(
                same.probabilities if same is not None else None
            ),
            latency_ms=shape.latency_ms,
            source=shape.source.value,
        )

    def _decide(
        self,
        shape: JudgmentResult,
        same: JudgmentResult | None,
        candidates: tuple[RankedCandidate, ...],
    ) -> tuple[str, str | None]:
        if shape.value == SHAPE_CURRENT_SITUATION and self._sure(shape):
            return OUTCOME_SKIP_CURRENT_SITUATION, None
        if same is not None and same.value != NO_SAME_MEANING and self._sure(same):
            target = next(c for c in candidates if c.text == same.value)
            return OUTCOME_STRENGTHEN, target.key
        return OUTCOME_CREATE, None

    def _sure(self, result: JudgmentResult) -> bool:
        assert result.confidence is not None
        return result.confidence >= self._min_confidence


def _shape_question() -> ChoiceQuestion:
    return ChoiceQuestion(
        instructions="この新しい信念の文は、次のどれを述べているか。",
        options=_SHAPE_OPTIONS,
    )


def _same_meaning_question(candidates: tuple[RankedCandidate, ...]) -> ChoiceQuestion:
    options: dict[str, str | None] = {
        NO_SAME_MEANING: "どの既存の信念とも主張が違う",
    }
    for candidate in candidates:
        options[candidate.text] = "この既存の信念と主張が同じ"
    return ChoiceQuestion(
        instructions=(
            "この新しい信念の文と同じ主張をしている既存の信念はどれか。言い回しが"
            "違っても主張が同じなら同じとする。対象・条件・結論のどれかが違えば"
            "同じとしない。"
        ),
        options=options,
    )


def _distinct_texts(
    ranked: tuple[RankedCandidate, ...],
) -> tuple[RankedCandidate, ...]:
    # 選択肢は文そのものを名前にするので、同じ文は 1 つにまとめる。「該当なし」と
    # 同じ文の信念は選択肢として区別できないので並べない。
    seen = {NO_SAME_MEANING}
    out: list[RankedCandidate] = []
    for candidate in ranked:
        if candidate.text in seen:
            continue
        seen.add(candidate.text)
        out.append(candidate)
    return tuple(out)


def _answer(
    answers: Mapping[str, JudgmentResult], name: str, question: ChoiceQuestion
) -> JudgmentResult:
    answer = answers.get(name)
    if answer is None:
        raise TypedJudgmentUnavailableException(
            f"belief create gate answer missing for {name!r}",
            error_code=_UNAVAILABLE_ANSWER_MISSING,
        )
    if answer.value not in question.options or answer.confidence is None:
        raise TypedJudgmentUnavailableException(
            f"belief create gate answer for {name!r} was not usable",
            error_code=_UNAVAILABLE_ANSWER_INVALID,
        )
    return answer


def _rounded(probabilities: Mapping[str, float] | None) -> dict[str, float] | None:
    if probabilities is None:
        return None
    return {k: round(v, 4) for k, v in probabilities.items()}


__all__ = [
    "BeliefCreateGate",
    "BeliefCreateReview",
    "NO_SAME_MEANING",
    "OUTCOME_CREATE",
    "OUTCOME_SKIP_CURRENT_SITUATION",
    "OUTCOME_STRENGTHEN",
    "SAME_MEANING_QUESTION",
    "SHAPE_CURRENT_SITUATION",
    "SHAPE_QUESTION",
]
