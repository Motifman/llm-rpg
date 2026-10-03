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

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    JudgmentResult,
    TypedJudgmentUnavailableException,
)

KEEP = "残す"
DROP = "捨てる"


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
    """欄ごとの答え。閾値を持たないので、どの程度の確信で残したかを trace で読めるようにする。"""

    field: SituationField
    value: str
    probabilities: Mapping[str, float]
    source: str

    def to_trace_payload(self) -> dict[str, Any]:
        return {
            "field": self.field.value,
            "value": self.value,
            "probabilities": dict(self.probabilities),
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
    """場所以外の欄に 1 問ずつ。並びは ``SELECTABLE_FIELDS`` と同じ。"""
    return {
        field_question_name(field): ChoiceQuestion(
            instructions=(
                f"「{field.value}」の欄を手がかりに残すか。"
                f"{self_name}が次のターンに思い出す学びを、いまの状況の欄で引く。"
                "体が危ないなら自分の状態といま起きたこと、探索したいならやろうとしていること、"
                "相手が誰かを知りたいなら相手、のように、次の判断に効く記憶を引く欄だけを残す。"
            ),
            options={
                KEEP: f"「{field.value}」は、次の判断に効く記憶を引く手がかりになる",
                DROP: f"「{field.value}」で引くと、次の判断に効かない記憶が混ざる",
            },
        )
        for field in SELECTABLE_FIELDS
    }


def field_selection_from_answers(answers: Mapping[str, JudgmentResult]) -> FieldSelection:
    """答えが欠けたか選択肢に無ければ全部の欄に縮退する。一部の欄だけを採らない。"""
    names = {field_question_name(field): field for field in SELECTABLE_FIELDS}
    missing = sorted(set(names) - set(answers))
    if missing:
        return FieldSelection.degraded(DEGRADED_ANSWER_MISSING, f"missing: {missing}")
    judgments: list[FieldJudgment] = []
    for name, field in names.items():
        answer = answers[name]
        if answer.value not in (KEEP, DROP):
            return FieldSelection.degraded(
                DEGRADED_ANSWER_INVALID, f"{name}={answer.value!r}"
            )
        judgments.append(
            FieldJudgment(
                field=field,
                value=answer.value,
                probabilities=dict(answer.probabilities),
                source=answer.source.value,
            )
        )
    return FieldSelection(
        kept=frozenset(j.field for j in judgments if j.value == KEEP),
        judgments=tuple(judgments),
    )


def field_question_name(field: SituationField) -> str:
    return f"recall_field_{field.name.lower()}"


__all__ = [
    "DEGRADED_ANSWER_INVALID",
    "DEGRADED_ANSWER_MISSING",
    "DEGRADED_JUDGMENT_UNAVAILABLE",
    "DROP",
    "KEEP",
    "FieldJudgment",
    "FieldSelection",
    "RecallMask",
    "SELECTABLE_FIELDS",
    "Situation",
    "SituationField",
    "field_question_name",
    "field_selection_from_answers",
    "field_selection_questions",
]
