"""想起のきっかけを状況の 6 つの欄で表し、どの欄で引くかを Jev に選ばせる (#1414)。

## 欄をつなげて 1 本で問い合わせない

いくつもの観点を 1 本の問い合わせにすると、平均に寄ってどの観点にも中途半端になる。
欄を残すか捨てるかを決めたマスクごとに引き、結果は別々の一覧で持つ。

## 場所は Jev に問わない

場所を捨てると別の場所での似た経験が、残すとこの場所についての知識が取れる。どちらが
効くかは場面で決め打ちできないので、場所を残した検索と捨てた検索を必ず両方走らせる。

## 判断が得られなければ全部の欄に縮退する

Jev が答えないか、答えが欠けたか選択肢に無い答えが返ったら、全部の欄を残し、理由を持たせる
(design_decisions 5)。誤っても行動は実行されず、頭に載る信念が変わるだけなので、
閾値は持たない (design_decisions 234)。
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    JudgmentResult,
    TypedJudgmentUnavailableException,
)

RECALL_FIELDS_QUESTION = "recall_fields"
#: 残す欄の数の既定。profile の SITUATION_FIELDS_TO_KEEP で変える。
DEFAULT_FIELDS_TO_KEEP = 2


class SituationField(Enum):
    """並び順が問い合わせ文の欄の順になる。"""

    PLACE = "場所"
    COUNTERPART = "相手"
    OWN_STATE = "自分の状態"
    INTENT = "やろうとしていること"
    HAPPENING = "いま起きたこと"
    UNRESOLVED = "未解決のこと"


SELECTABLE_FIELDS: tuple[SituationField, ...] = tuple(
    f for f in SituationField if f is not SituationField.PLACE
)


@dataclass(frozen=True)
class Situation:
    """欄の値は名前や文で持つ。世界状態への照会、ゲームの ID、tags、cue は入れない。"""

    place: tuple[str, ...] = ()
    counterpart: tuple[str, ...] = ()
    own_state: tuple[str, ...] = ()
    intent: tuple[str, ...] = ()
    happening: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field in SituationField:
            texts = self.texts(field)
            if not isinstance(texts, tuple):
                raise TypeError(f"{field.name.lower()} must be tuple[str, ...]")
            for text in texts:
                if not isinstance(text, str):
                    raise TypeError(f"{field.name.lower()} must be tuple[str, ...]")
                if not text.strip():
                    raise ValueError(f"{field.name.lower()} must not contain empty text")

    def texts(self, field: SituationField) -> tuple[str, ...]:
        texts: tuple[str, ...] = getattr(self, field.name.lower())
        return texts


@dataclass(frozen=True)
class RecallMask:
    kept: frozenset[SituationField]

    def query(self, situation: Situation) -> str:
        return "\n".join(
            text
            for field in SituationField
            if field in self.kept
            for text in situation.texts(field)
        )

    def to_trace_payload(self) -> list[str]:
        return [f.value for f in SituationField if f in self.kept]


#: 縮退の理由。trace で数えられるように分類で持ち、詳しい内容は ``degraded_detail`` に置く。
DEGRADED_ANSWER_MISSING = "answer_missing"
DEGRADED_ANSWER_INVALID = "answer_invalid"
DEGRADED_JUDGMENT_UNAVAILABLE = "judgment_unavailable"


@dataclass(frozen=True)
class FieldJudgment:
    """欄ごとの確率と、上位に入って残したか。閾値を持たないので、確率を trace で読めるようにする。"""

    field: SituationField
    probability: float
    kept: bool
    source: str

    def to_trace_payload(self) -> dict[str, Any]:
        return {
            "field": self.field.value,
            "probability": self.probability,
            "kept": self.kept,
            "source": self.source,
        }


@dataclass(frozen=True)
class FieldSelection:
    """次の想起で残す欄。``kept`` に場所は入らない。"""

    kept: frozenset[SituationField]
    degraded_reason: str | None = None
    degraded_detail: str | None = None
    judgments: tuple[FieldJudgment, ...] = ()

    def __post_init__(self) -> None:
        if SituationField.PLACE in self.kept:
            raise ValueError("place is always searched both with and without it")

    @classmethod
    def degraded(cls, reason: str, detail: str | None = None) -> FieldSelection:
        return cls(
            kept=frozenset(SELECTABLE_FIELDS),
            degraded_reason=reason,
            degraded_detail=detail,
        )

    @classmethod
    def unavailable(cls, exc: TypedJudgmentUnavailableException) -> FieldSelection:
        """``judge`` が投げたときの縮退。呼び出し側は例外をここで選び方に変える。"""
        return cls.degraded(
            DEGRADED_JUDGMENT_UNAVAILABLE, f"{exc.error_code}: {exc}"
        )

    def masks(self) -> tuple[RecallMask, RecallMask]:
        """場所を残した検索を先に返す。頭に載る枠をこの順で埋める。"""
        return (
            RecallMask(self.kept | {SituationField.PLACE}),
            RecallMask(self.kept),
        )

    def to_trace_payload(self) -> dict[str, Any]:
        return {
            "kept_fields": RecallMask(self.kept).to_trace_payload(),
            "degraded_reason": self.degraded_reason,
            "degraded_detail": self.degraded_detail,
            "judgments": [j.to_trace_payload() for j in self.judgments],
        }


def field_selection_questions(self_name: str) -> dict[str, ChoiceQuestion]:
    """場所以外の 5 つの欄を選択肢にした 1 問。選択肢ごとの確率で欄を並べる。

    欄ごとに「残す / 捨てる」を問うと、どの欄も残す側に寄った (#1414 の確かめ方)。
    1 問にして欄どうしを比べさせる。
    """
    return {
        RECALL_FIELDS_QUESTION: ChoiceQuestion(
            instructions=(
                f"{self_name}が次のターンに思い出す学びを、いまの状況のどの欄を手がかりに"
                "引くか。次の判断にいちばん効く記憶を引ける欄を選ぶ。欄の値は state の"
                "「いまの状況」にある。値の無い欄は手がかりにならない。ただし自分の状態の"
                "欄にはまだ体の帯が入っていないので、体が危ないかは出来事の時系列から読み、"
                "危ないなら自分の状態を選ぶ。探索したいならやろうとしていること、"
                "相手が誰かを知りたいなら相手、のように選ぶ。"
            ),
            options={field.value: _FIELD_MEANINGS[field] for field in SELECTABLE_FIELDS},
        )
    }


def _is_probability(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


_FIELD_MEANINGS: dict[SituationField, str] = {
    SituationField.COUNTERPART: "相手。いま関わっている人や生き物の名前",
    SituationField.OWN_STATE: "自分の状態。自分の体の具合",
    SituationField.INTENT: "やろうとしていること。目的と直前の内心",
    SituationField.HAPPENING: "いま起きたこと。直近の出来事と自分の行動の結果",
    SituationField.UNRESOLVED: "未解決のこと。まだ当たり外れが決まっていない予期",
}


def field_selection_from_answers(
    answers: Mapping[str, JudgmentResult], *, keep: int = DEFAULT_FIELDS_TO_KEEP
) -> FieldSelection:
    """選択肢ごとの確率の上位 ``keep`` 個の欄を残す。閾値は持たない (design_decisions 234)。

    答えが欠けたか、確率が全部の選択肢にそろっていなければ、全部の欄に縮退する。
    同じ確率なら欄の決まった順で先のものを採る。
    """
    if isinstance(keep, bool) or not isinstance(keep, int) or not 1 <= keep <= len(
        SELECTABLE_FIELDS
    ):
        raise ValueError(f"keep must be between 1 and {len(SELECTABLE_FIELDS)}")
    answer = answers.get(RECALL_FIELDS_QUESTION)
    if answer is None:
        return FieldSelection.degraded(
            DEGRADED_ANSWER_MISSING, f"missing: {RECALL_FIELDS_QUESTION}"
        )
    missing = [f.value for f in SELECTABLE_FIELDS if f.value not in answer.probabilities]
    if missing:
        return FieldSelection.degraded(
            DEGRADED_ANSWER_INVALID, f"probabilities missing for {missing}"
        )
    broken = [
        f.value for f in SELECTABLE_FIELDS if not _is_probability(answer.probabilities[f.value])
    ]
    if broken:
        # NaN が混ざると並びが決まらず、上位が静かに変わる。
        return FieldSelection.degraded(
            DEGRADED_ANSWER_INVALID, f"probabilities are not finite numbers for {broken}"
        )
    ranked = sorted(
        SELECTABLE_FIELDS,
        key=lambda f: (-float(answer.probabilities[f.value]), SELECTABLE_FIELDS.index(f)),
    )
    kept = frozenset(ranked[:keep])
    return FieldSelection(
        kept=kept,
        judgments=tuple(
            FieldJudgment(
                field=f,
                probability=float(answer.probabilities[f.value]),
                kept=f in kept,
                source=answer.source.value,
            )
            for f in SELECTABLE_FIELDS
        ),
    )


__all__ = [
    "DEGRADED_ANSWER_INVALID",
    "DEGRADED_ANSWER_MISSING",
    "DEGRADED_JUDGMENT_UNAVAILABLE",
    "DEFAULT_FIELDS_TO_KEEP",
    "RECALL_FIELDS_QUESTION",
    "FieldJudgment",
    "FieldSelection",
    "RecallMask",
    "SELECTABLE_FIELDS",
    "Situation",
    "SituationField",
    "field_selection_from_answers",
    "field_selection_questions",
]
