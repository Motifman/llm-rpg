"""tool 呼び出しの引数 ``expectations`` から、書かれた予期を読む (#1441)。

崩れた 1 件はその 1 件だけを外し、ほかの予期は積む。外した予期は理由と元の値を
残し、trace で「書かなかった」と「書いたが積めなかった」を見分けられるようにする。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ai_rpg_world.application.being.expectation.forming import WrittenExpectation
from ai_rpg_world.application.being.expectation.likelihood_labels import (
    LIKELIHOOD_BY_LABEL,
)
from ai_rpg_world.application.llm.services.tool_catalog.subjective_action import (
    EXPECTATIONS_FIELD_NAME,
)

REJECTED_NOT_A_LIST = "not_a_list"
REJECTED_NOT_AN_OBJECT = "not_an_object"
REJECTED_MISSING_WHAT = "missing_what"
REJECTED_INVALID_WHEN = "invalid_when"
REJECTED_INVALID_LIKELIHOOD = "invalid_likelihood"


@dataclass(frozen=True)
class RejectedExpectation:
    """積まなかった予期。``index`` は配列の中の位置で、引数ごと崩れていれば None。"""

    index: int | None
    reason: str
    raw: Any


@dataclass(frozen=True)
class ReadExpectations:
    """1 回の呼び出しから読んだ予期。``present`` は引数そのものがあったか。"""

    written: tuple[WrittenExpectation, ...] = ()
    rejected: tuple[RejectedExpectation, ...] = ()
    present: bool = False


def read_written_expectations(arguments: Mapping[str, Any]) -> ReadExpectations:
    if EXPECTATIONS_FIELD_NAME not in arguments:
        return ReadExpectations()
    raw = arguments[EXPECTATIONS_FIELD_NAME]
    if raw is None:
        return ReadExpectations(present=True)
    if not isinstance(raw, list):
        return ReadExpectations(
            rejected=(RejectedExpectation(None, REJECTED_NOT_A_LIST, raw),),
            present=True,
        )
    written: list[WrittenExpectation] = []
    rejected: list[RejectedExpectation] = []
    for index, item in enumerate(raw):
        read = _read_item(item)
        if isinstance(read, WrittenExpectation):
            written.append(read)
        else:
            rejected.append(RejectedExpectation(index, read, item))
    return ReadExpectations(
        written=tuple(written), rejected=tuple(rejected), present=True
    )


def _read_item(item: Any) -> WrittenExpectation | str:
    if not isinstance(item, Mapping):
        return REJECTED_NOT_AN_OBJECT
    what = item.get("what")
    if not isinstance(what, str) or not what.strip():
        return REJECTED_MISSING_WHAT
    when = item.get("when")
    if when is not None and not isinstance(when, str):
        return REJECTED_INVALID_WHEN
    label = item.get("likelihood")
    likelihood = LIKELIHOOD_BY_LABEL.get(label) if isinstance(label, str) else None
    if likelihood is None:
        return REJECTED_INVALID_LIKELIHOOD
    return WrittenExpectation(
        what=what.strip(),
        when=(when.strip() or None) if when is not None else None,
        likelihood=likelihood,
    )


__all__ = [
    "REJECTED_INVALID_LIKELIHOOD",
    "REJECTED_INVALID_WHEN",
    "REJECTED_MISSING_WHAT",
    "REJECTED_NOT_AN_OBJECT",
    "REJECTED_NOT_A_LIST",
    "ReadExpectations",
    "RejectedExpectation",
    "read_written_expectations",
]
