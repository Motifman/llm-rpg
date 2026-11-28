"""tool 呼び出しの引数 ``memo`` から、メモの操作を読む (#1628)。

provider は JSON の形を強制しないので、受け取った側で操作ごとに確かめる。崩れた操作は
その操作だけを外し、ほかの操作と行動そのものは通す。
外した理由は、本人に返す文と trace に使う。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from ai_rpg_world.being.application.memo_argument import (
    MEMO_FIELD_NAME,
)
from ai_rpg_world.being.domain.memo_book import (
    KIND_LIMITS,
    MEMO_TEXT_MAX_LENGTH,
    MemoAddition,
    MemoCertainty,
    MemoKind,
    MemoOperation,
    MemoProvenance,
    MemoRemoval,
    MemoRevision,
    MemoSource,
)
from ai_rpg_world.domain.being.exception.being_exceptions import (
    MemoEpisodeSourceFromMissingException,
    MemoHeardSourceFromMissingException,
    MemoLimitReachedException,
    MemoNotFoundException,
    MemoProvenanceMissingException,
    MemoProvenanceOutsideFactException,
    MemoSourceEpisodeUnknownException,
    MemoSourceFromNotNeededException,
    MemoSourceNotEpisodeHandleException,
    MemoTextTooLongException,
    MemoValidationException,
)

REJECTED_NOT_A_LIST = "not_a_list"
REJECTED_NOT_AN_OBJECT = "not_an_object"
REJECTED_UNKNOWN_DO = "unknown_do"
REJECTED_UNKNOWN_KIND = "unknown_kind"
REJECTED_MISSING_TEXT = "missing_text"
REJECTED_TEXT_TOO_LONG = "text_too_long"
REJECTED_MISSING_ID = "missing_id"
REJECTED_MISSING_PROVENANCE = "missing_provenance"
REJECTED_MISSING_FROM = "missing_from"
REJECTED_MISSING_EPISODE_FROM = "missing_episode_from"
REJECTED_FROM_NOT_NEEDED = "from_not_needed"
REJECTED_LIMIT_REACHED = "limit_reached"
REJECTED_NO_SUCH_MEMO = "no_such_memo"
REJECTED_PROVENANCE_OUTSIDE_FACT = "provenance_outside_fact"
REJECTED_UNKNOWN_EPISODE = "unknown_episode"
REJECTED_INVALID = "invalid"

_REASONS_BY_ERROR_CODE = {
    MemoTextTooLongException.error_code: REJECTED_TEXT_TOO_LONG,
    MemoProvenanceMissingException.error_code: REJECTED_MISSING_PROVENANCE,
    MemoProvenanceOutsideFactException.error_code: REJECTED_PROVENANCE_OUTSIDE_FACT,
    MemoHeardSourceFromMissingException.error_code: REJECTED_MISSING_FROM,
    MemoEpisodeSourceFromMissingException.error_code: REJECTED_MISSING_EPISODE_FROM,
    MemoSourceFromNotNeededException.error_code: REJECTED_FROM_NOT_NEEDED,
    MemoSourceNotEpisodeHandleException.error_code: REJECTED_UNKNOWN_EPISODE,
    MemoSourceEpisodeUnknownException.error_code: REJECTED_UNKNOWN_EPISODE,
    MemoLimitReachedException.error_code: REJECTED_LIMIT_REACHED,
    MemoNotFoundException.error_code: REJECTED_NO_SUCH_MEMO,
}

MemoRefusal = MemoValidationException | MemoLimitReachedException | MemoNotFoundException


def refusal_reason(refusal: MemoRefusal) -> str:
    return _REASONS_BY_ERROR_CODE.get(refusal.error_code, REJECTED_INVALID)


@dataclass(frozen=True)
class RejectedMemoArgument:
    """``index`` は配列の中の位置で、引数ごと崩れていれば None。"""

    index: int | None
    reason: str
    raw: Any


@dataclass(frozen=True)
class ReadMemoOperation:
    """``do`` は書かれていた操作の種類 (add / edit / remove)。"""

    index: int
    do: str
    operation: MemoOperation
    raw: Any


@dataclass(frozen=True)
class ReadMemoOperations:
    """``present`` は引数そのものがあったか。"""

    operations: tuple[ReadMemoOperation, ...] = ()
    rejected: tuple[RejectedMemoArgument, ...] = ()
    present: bool = False


def read_memo_operations(arguments: Mapping[str, Any], *, episode_source_offered: bool) -> ReadMemoOperations:
    if MEMO_FIELD_NAME not in arguments:
        return ReadMemoOperations()
    raw = arguments[MEMO_FIELD_NAME]
    if raw is None:
        return ReadMemoOperations(present=True)
    if not isinstance(raw, list):
        return ReadMemoOperations(rejected=(RejectedMemoArgument(None, REJECTED_NOT_A_LIST, raw),), present=True)
    operations: list[ReadMemoOperation] = []
    rejected: list[RejectedMemoArgument] = []
    for index, item in enumerate(raw):
        read = _read_item(item, episode_source_offered=episode_source_offered)
        if isinstance(read, str):
            rejected.append(RejectedMemoArgument(index, read, item))
        else:
            operations.append(ReadMemoOperation(index, item["do"], read, item))
    return ReadMemoOperations(operations=tuple(operations), rejected=tuple(rejected), present=True)


def _given(value: Any) -> bool:
    return value is not None and not (isinstance(value, str) and not value.strip())


def _read_text(item: Mapping[str, Any]) -> str | None:
    text = item.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    return text.strip()


def _read_handle(item: Mapping[str, Any]) -> str | None:
    handle = item.get("id")
    if not isinstance(handle, str) or not handle.strip():
        return None
    return handle.strip()


def _read_provenance(item: Mapping[str, Any], *, episode_source_offered: bool) -> MemoProvenance | str | None:
    """どれも書かれていなければ None。書かれていて形が崩れているか、出どころの決まりに反していれば理由を返す。"""
    source_raw, certainty_raw, source_from = (
        item.get("source"),
        item.get("certainty"),
        item.get("from"),
    )
    if not any(_given(v) for v in (source_raw, certainty_raw, source_from)):
        return None
    offered = {MemoSource.SELF.value, MemoSource.HEARD.value}
    if episode_source_offered:
        offered.add(MemoSource.EPISODE.value)
    if (
        not isinstance(source_raw, str)
        or not isinstance(certainty_raw, str)
        or source_raw not in offered
        or certainty_raw not in {c.value for c in MemoCertainty}
    ):
        return REJECTED_MISSING_PROVENANCE
    try:
        return MemoProvenance(
            source=MemoSource(source_raw),
            certainty=MemoCertainty(certainty_raw),
            source_from=source_from.strip() if isinstance(source_from, str) and _given(source_from) else None,
        )
    except MemoValidationException as refusal:
        return refusal_reason(refusal)


def _read_item(item: Any, *, episode_source_offered: bool) -> MemoOperation | str:
    if not isinstance(item, Mapping):
        return REJECTED_NOT_AN_OBJECT
    do = item.get("do")
    if do == "remove":
        handle = _read_handle(item)
        return REJECTED_MISSING_ID if handle is None else MemoRemoval(handle)
    if do not in ("add", "edit"):
        return REJECTED_UNKNOWN_DO
    text = _read_text(item)
    if text is None:
        return REJECTED_MISSING_TEXT
    provenance = _read_provenance(item, episode_source_offered=episode_source_offered)
    if isinstance(provenance, str):
        return provenance
    if do == "edit":
        handle = _read_handle(item)
        return REJECTED_MISSING_ID if handle is None else MemoRevision(handle, text, provenance)
    try:
        kind = MemoKind(item.get("kind"))
    except ValueError:
        return REJECTED_UNKNOWN_KIND
    return MemoAddition(kind, text, provenance)


_KIND_LABELS = {MemoKind.TODO: "やること", MemoKind.FACT: "分かったこと", MemoKind.PERSON: "人について"}

_REASON_TEXTS = {
    REJECTED_NOT_A_LIST: "memo は操作の配列で書いてください。",
    REJECTED_NOT_AN_OBJECT: '操作は {"do": ...} の形で書いてください。',
    REJECTED_UNKNOWN_DO: "do は add / edit / remove のどれかです。",
    REJECTED_UNKNOWN_KIND: "kind は todo / fact / person のどれかです。",
    REJECTED_MISSING_TEXT: "text が空です。",
    REJECTED_TEXT_TOO_LONG: f"text は {MEMO_TEXT_MAX_LENGTH} 字までです。",
    REJECTED_MISSING_ID: "id に書き換える・消すメモの呼び名 (m_ で始まる) を書いてください。",
    REJECTED_MISSING_PROVENANCE: (
        "分かったこと (fact) には source (self / heard など) と certainty (sure / guess) を書いてください。"
    ),
    REJECTED_MISSING_FROM: "人から聞いたこと (heard) には、from に誰から聞いたかを書いてください。",
    REJECTED_MISSING_EPISODE_FROM: (
        "エピソードから分かったこと (episode) には、from にエピソードの呼び名 (ep_ で始まる) を書いてください。"
    ),
    REJECTED_FROM_NOT_NEEDED: "自分で確かめたこと (self) には from を書きません。",
    REJECTED_PROVENANCE_OUTSIDE_FACT: "source と certainty は分かったこと (fact) にだけ書けます。",
    REJECTED_INVALID: "書けませんでした。",
}


def rejection_text(reason: str, *, kind: MemoKind | None = None, detail: str | None = None) -> str:
    """外した理由を、本人に返す文にする。"""
    if reason == REJECTED_LIMIT_REACHED and kind is not None:
        return f"{_KIND_LABELS[kind]}が上限 ({KIND_LIMITS[kind]} 件) です。消すか書き換えてください。"
    if reason == REJECTED_NO_SUCH_MEMO:
        return f"{detail} というメモはありません。" if detail else "そのメモはありません。"
    if reason == REJECTED_UNKNOWN_EPISODE:
        return f"{detail} というエピソードはありません。" if detail else "そのエピソードはありません。"
    return _REASON_TEXTS.get(reason, _REASON_TEXTS[REJECTED_INVALID])


def feedback_text(rejections: Iterable[tuple[int | None, str]]) -> str:
    """``rejections`` は (配列の中の位置, 理由の文)。無ければ空文字。"""
    lines = [f"- {'memo' if index is None else f'{index + 1} 件目'}: {text}" for index, text in rejections]
    if not lines:
        return ""
    return "\n\n[メモ] 次の操作は書けませんでした。\n" + "\n".join(lines)


__all__ = [
    "REJECTED_FROM_NOT_NEEDED",
    "REJECTED_INVALID",
    "REJECTED_LIMIT_REACHED",
    "REJECTED_MISSING_EPISODE_FROM",
    "REJECTED_MISSING_FROM",
    "REJECTED_MISSING_ID",
    "REJECTED_MISSING_PROVENANCE",
    "REJECTED_MISSING_TEXT",
    "REJECTED_NOT_AN_OBJECT",
    "REJECTED_NOT_A_LIST",
    "REJECTED_NO_SUCH_MEMO",
    "REJECTED_PROVENANCE_OUTSIDE_FACT",
    "REJECTED_TEXT_TOO_LONG",
    "REJECTED_UNKNOWN_DO",
    "REJECTED_UNKNOWN_EPISODE",
    "REJECTED_UNKNOWN_KIND",
    "MemoRefusal",
    "ReadMemoOperation",
    "ReadMemoOperations",
    "RejectedMemoArgument",
    "refusal_reason",
    "feedback_text",
    "read_memo_operations",
    "rejection_text",
]
