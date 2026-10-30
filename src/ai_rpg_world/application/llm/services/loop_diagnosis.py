"""ループ警告が発火したとき、繰り返しの理由を型付き判断に選ばせる (#1411)。

繰り返しを見つけるのは検出器で、件数と tick 差はコードで数える。ここで問うのは
「なぜ繰り返しているか」だけ。居場所を取り違えている人に要るのは「もう土手に
居る」という事実で、「別の行動を選べ」ではない。理由ごとに伝える事実を変える。

## 選んだ理由で警告を消さない

どの理由を選んでも、警告は出す。「待機」を選んだからと警告を消すと、判断が外れた
ときに詰まったエージェントに誰も気づかない (design_decisions #222 と同じ非対称)。

## 閾値は置かない

誤っても変わるのは警告の文面だけで、行動は実行されない。確率が低くても、
「該当なし」以外を選べばその理由の文面にする (design_decisions #234)。

## 縮退は 2 通りあり、trace で分ける

「該当なし」と、判断が得られない。どちらも今の文面で警告を出す。
「該当なし」が多い場面は選択肢が足りていない場面なので、区別して残す。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    ITypedJudgmentPort,
    TypedJudgmentUnavailableException,
)

logger = logging.getLogger(__name__)

QUESTION_NAME = "loop_diagnosis"

#: 理由の名前と衝突しない形にする。
NONE_APPLICABLE_OPTION = "__none_applicable__"


class RepeatReason(Enum):
    ACHIEVED = "achieved"
    STATE_MISTAKEN = "state_mistaken"
    MISSING_PRECONDITION = "missing_precondition"
    WAITING = "waiting"
    UNANSWERED_REQUEST = "unanswered_request"
    FIXED_MEANS = "fixed_means"


_REASON_MEANINGS: Mapping[RepeatReason, str] = {
    RepeatReason.ACHIEVED: ("目的の状態に既に届いているのに、同じ行動を取っている"),
    RepeatReason.STATE_MISTAKEN: ("自分の居場所、所持品、移動中かどうかを取り違えている"),
    RepeatReason.MISSING_PRECONDITION: ("失敗文が示す条件を満たさないまま、同じ行動を試している"),
    RepeatReason.WAITING: ("世界の変化や他者の到着を待っていて、繰り返し自体は意図どおり"),
    RepeatReason.UNANSWERED_REQUEST: ("返事の無い相手に、同じ依頼を繰り返している"),
    RepeatReason.FIXED_MEANS: ("目的は妥当だが、同じ手段だけを試し続けている"),
}

_NONE_APPLICABLE_MEANING = "上のどの理由にも当たらない"


class DiagnosisFallback(Enum):
    NONE_APPLICABLE = "none_applicable"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class LoopDiagnosisJudgment:
    """繰り返しの理由を問うた結果。採らなかった判断も、採らなかった理由と対で残す。

    ``reason`` と ``fallback`` はどちらか一方だけが None でない。
    """

    reason: RepeatReason | None
    fallback: DiagnosisFallback | None
    chosen: str | None = None
    probabilities: Mapping[str, float] = field(default_factory=dict)
    probability: float | None = None
    confidence: float | None = None
    latency_ms: float | None = None
    source: str | None = None
    unavailable_reason: str | None = None


class LoopDiagnosis:
    """繰り返しの理由を 1 回問い、「該当なし」以外を選べばその理由を採る。"""

    def __init__(self, *, port: ITypedJudgmentPort) -> None:
        if not isinstance(port, ITypedJudgmentPort):
            raise TypeError("port must be ITypedJudgmentPort")
        #: 公開するのは、ポートが profile から届いたかを外から確かめるため。
        self.port = port

    def diagnose(self, state: Mapping[str, Any] | Sequence[Any] | str) -> LoopDiagnosisJudgment:
        try:
            answer = self.port.judge(state, {QUESTION_NAME: _question()}).get(QUESTION_NAME)
        except TypedJudgmentUnavailableException as exc:
            logger.warning("loop diagnosis unavailable: %s", exc)
            return self._unavailable(exc.error_code)
        except Exception:
            # 理由は文面を選ぶだけなので、ここで落ちて警告まで消してはいけない。
            logger.exception("loop diagnosis failed unexpectedly")
            return self._unavailable("UNEXPECTED_ERROR")
        if answer is None:
            return self._unavailable("ANSWER_MISSING")

        chosen = str(answer.value)
        probability = answer.probabilities.get(chosen)
        evidence = LoopDiagnosisJudgment(
            reason=None,
            fallback=None,
            chosen=chosen,
            probabilities=dict(answer.probabilities),
            probability=probability,
            confidence=answer.confidence,
            latency_ms=answer.latency_ms,
            source=answer.source.value,
        )
        if chosen == NONE_APPLICABLE_OPTION:
            return replace(evidence, fallback=DiagnosisFallback.NONE_APPLICABLE)
        try:
            reason = RepeatReason(chosen)
        except ValueError:
            return replace(
                evidence,
                fallback=DiagnosisFallback.UNAVAILABLE,
                unavailable_reason="INVALID_RESPONSE",
            )
        return replace(evidence, reason=reason)

    def _unavailable(self, code: str) -> LoopDiagnosisJudgment:
        return LoopDiagnosisJudgment(
            reason=None,
            fallback=DiagnosisFallback.UNAVAILABLE,
            unavailable_reason=code,
        )


def _question() -> ChoiceQuestion:
    return ChoiceQuestion(
        instructions=(
            "この人は repeated_action を繰り返している。直近の行動とその結果、"
            "いまの居場所、いま届いている観測から、繰り返している理由として"
            "最も当たるものを選ぶ。どれにも当たらなければ "
            f"{NONE_APPLICABLE_OPTION} を選ぶ。"
        ),
        options={
            **{reason.value: meaning for reason, meaning in _REASON_MEANINGS.items()},
            NONE_APPLICABLE_OPTION: _NONE_APPLICABLE_MEANING,
        },
    )


__all__ = [
    "DiagnosisFallback",
    "LoopDiagnosis",
    "LoopDiagnosisJudgment",
    "NONE_APPLICABLE_OPTION",
    "QUESTION_NAME",
    "RepeatReason",
]
