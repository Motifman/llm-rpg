"""自分の体の状態を「平常 / 注意 / 危機」の帯に丸める (#1414)。

HP や空腹の段階の表示は環境ごとに違うので、帯への丸めは規則で書かずに Jev に
選ばせる。帯の語は自分の状態の欄に文として足す。エピソードの書き込み時のキー
(#1454、例: 「囲まれた・危機・入口へ走って離脱・逃げ切れた」) と語を揃え、環境の
言い回しが違っても一致させるため (design_decisions D1414-4)。

材料は清算の時系列で、体の状態の観測の本文もそこに入っている。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ai_rpg_world.application.being.recall.situation import (
    DEGRADED_ANSWER_INVALID,
    DEGRADED_ANSWER_MISSING,
    DEGRADED_JUDGMENT_UNAVAILABLE,
)
from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    JudgmentResult,
    TypedJudgmentUnavailableException,
)

BODY_BAND_QUESTION = "recall_body_band"
UNKNOWN_BAND = "分からない"
#: 時系列に体のことが書かれていなかった。判断の失敗ではないが、帯は付けない。
BODY_NOT_MENTIONED = "body_not_mentioned"


class BodyBand(Enum):
    CALM = "平常"
    CAUTION = "注意"
    CRISIS = "危機"

    def sentence(self) -> str:
        return f"体の状態は{self.value}"


@dataclass(frozen=True)
class BodyBandReading:
    """帯の判断。``band`` が None なら帯を付けずに、生の本文だけで引く。"""

    band: BodyBand | None
    degraded_reason: str | None = None
    degraded_detail: str | None = None
    probabilities: Mapping[str, float] = field(default_factory=dict)
    source: str | None = None

    @classmethod
    def degraded(cls, reason: str, detail: str | None = None) -> BodyBandReading:
        return cls(band=None, degraded_reason=reason, degraded_detail=detail)

    @classmethod
    def unavailable(cls, exc: TypedJudgmentUnavailableException) -> BodyBandReading:
        return cls.degraded(DEGRADED_JUDGMENT_UNAVAILABLE, f"{exc.error_code}: {exc}")

    def to_trace_payload(self) -> dict[str, Any]:
        return {
            "band": None if self.band is None else self.band.value,
            "degraded_reason": self.degraded_reason,
            "degraded_detail": self.degraded_detail,
            "probabilities": dict(self.probabilities),
            "source": self.source,
        }


def body_band_question(self_name: str) -> ChoiceQuestion:
    return ChoiceQuestion(
        instructions=(
            f"{self_name}の体の状態は、いまどの帯にあるか。出来事の時系列に書かれた"
            f"{self_name}の体のこと (怪我、空腹、疲れ、攻撃を受けた、回復したなど) から選ぶ。"
            "体のことが書かれていなければ、平常ではなく「分からない」を選ぶ。"
        ),
        options={
            BodyBand.CALM.value: "平常。体に差し迫った問題は無い",
            BodyBand.CAUTION.value: "注意。放っておくと困る体の問題がある (空腹、疲れ、軽い怪我など)",
            BodyBand.CRISIS.value: "危機。すぐ手を打たないと倒れるか死ぬおそれがある",
            UNKNOWN_BAND: "分からない。時系列に体のことが書かれていない",
        },
    )


def body_band_from_answers(answers: Mapping[str, JudgmentResult]) -> BodyBandReading:
    answer = answers.get(BODY_BAND_QUESTION)
    if answer is None:
        return BodyBandReading.degraded(DEGRADED_ANSWER_MISSING, f"missing: {BODY_BAND_QUESTION}")
    if answer.value == UNKNOWN_BAND:
        # 続いている不調が時系列から流れたあとに平常と丸めると、いまの体と食い違う。
        return BodyBandReading(
            band=None,
            degraded_reason=BODY_NOT_MENTIONED,
            probabilities=dict(answer.probabilities),
            source=answer.source.value,
        )
    try:
        band = BodyBand(answer.value)
    except ValueError:
        return BodyBandReading.degraded(
            DEGRADED_ANSWER_INVALID, f"{BODY_BAND_QUESTION}={answer.value!r}"
        )
    return BodyBandReading(
        band=band, probabilities=dict(answer.probabilities), source=answer.source.value
    )


__all__ = [
    "BODY_BAND_QUESTION",
    "BODY_NOT_MENTIONED",
    "UNKNOWN_BAND",
    "BodyBand",
    "BodyBandReading",
    "body_band_from_answers",
    "body_band_question",
]
