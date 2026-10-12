"""1 回の行動に書かれたメモの操作を、メモ帳への 1 回の変更として当てる (#1628)。

崩れた操作はその操作だけを外し、ほかの操作は当てる。外した理由は、本人に返す文と
trace に使う。
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass

from ai_rpg_world.being.domain.memo_book import (
    Memo,
    MemoBook,
    MemoKind,
    MemoProvenance,
    MemoSource,
)
from ai_rpg_world.domain.being.exception.being_exceptions import (
    MemoLimitReachedException,
    MemoNotFoundException,
    MemoValidationException,
)

REJECTED_LIMIT_REACHED = "limit_reached"
REJECTED_NO_SUCH_MEMO = "no_such_memo"
REJECTED_PROVENANCE_OUTSIDE_FACT = "provenance_outside_fact"
REJECTED_UNKNOWN_EPISODE = "unknown_episode"
REJECTED_INVALID = "invalid"


@dataclass(frozen=True)
class AddMemo:
    kind: MemoKind
    text: str
    provenance: MemoProvenance | None


@dataclass(frozen=True)
class EditMemo:
    handle: str
    text: str
    provenance: MemoProvenance | None


@dataclass(frozen=True)
class RemoveMemo:
    handle: str


MemoOperation = AddMemo | EditMemo | RemoveMemo


@dataclass(frozen=True)
class AppliedMemoOperation:
    """``memo`` は足した・書き換えたあとのメモか、消したメモ。"""

    index: int
    operation: MemoOperation
    memo: Memo


@dataclass(frozen=True)
class RejectedMemoOperation:
    index: int
    operation: MemoOperation
    reason: str
    kind: MemoKind | None = None
    detail: str | None = None


@dataclass(frozen=True)
class MemoOperationsOutcome:
    book: MemoBook
    applied: tuple[AppliedMemoOperation, ...]
    rejected: tuple[RejectedMemoOperation, ...]


def _from_unknown_episode(
    provenance: MemoProvenance | None, known_episode_handles: Collection[str]
) -> bool:
    return (
        provenance is not None
        and provenance.source is MemoSource.EPISODE
        and provenance.source_from not in known_episode_handles
    )


def apply_memo_operations(
    book: MemoBook,
    operations: Sequence[tuple[int, MemoOperation]],
    *,
    turn: int,
    environment_name: str,
    new_memo_id: Callable[[], str],
    known_episode_handles: Collection[str] = (),
) -> MemoOperationsOutcome:
    """``operations`` の数は行動の引数に書かれた配列の位置。外した操作を返すときに使う。"""
    applied: list[AppliedMemoOperation] = []
    rejected: list[RejectedMemoOperation] = []
    for index, operation in operations:

        def reject(reason: str, kind: MemoKind | None = None, detail: str | None = None) -> None:
            rejected.append(RejectedMemoOperation(index, operation, reason, kind, detail))

        provenance = None if isinstance(operation, RemoveMemo) else operation.provenance
        if _from_unknown_episode(provenance, known_episode_handles):
            reject(REJECTED_UNKNOWN_EPISODE, detail=provenance.source_from if provenance else None)
            continue
        try:
            if isinstance(operation, AddMemo):
                book = book.add(
                    memo_id=new_memo_id(),
                    kind=operation.kind,
                    text=operation.text,
                    provenance=operation.provenance,
                    turn=turn,
                    environment_name=environment_name,
                    known_episode_handles=known_episode_handles,
                )
                applied.append(AppliedMemoOperation(index, operation, book.memos[-1]))
            elif isinstance(operation, EditMemo):
                target = book.find(operation.handle)
                if target is not None and provenance is not None and target.kind is not MemoKind.FACT:
                    reject(REJECTED_PROVENANCE_OUTSIDE_FACT, kind=target.kind)
                    continue
                book = book.edit(
                    operation.handle,
                    text=operation.text,
                    turn=turn,
                    provenance=operation.provenance,
                    known_episode_handles=known_episode_handles,
                )
                edited = book.find(operation.handle)
                assert edited is not None
                applied.append(AppliedMemoOperation(index, operation, edited))
            else:
                book, removed = book.remove(operation.handle)
                applied.append(AppliedMemoOperation(index, operation, removed))
        except MemoLimitReachedException:
            reject(REJECTED_LIMIT_REACHED, kind=operation.kind if isinstance(operation, AddMemo) else None)
        except MemoNotFoundException:
            reject(REJECTED_NO_SUCH_MEMO, detail=getattr(operation, "handle", None))
        except MemoValidationException as exc:
            reject(REJECTED_INVALID, detail=str(exc))
    return MemoOperationsOutcome(book=book, applied=tuple(applied), rejected=tuple(rejected))


__all__ = [
    "REJECTED_INVALID",
    "REJECTED_LIMIT_REACHED",
    "REJECTED_NO_SUCH_MEMO",
    "REJECTED_PROVENANCE_OUTSIDE_FACT",
    "REJECTED_UNKNOWN_EPISODE",
    "AddMemo",
    "AppliedMemoOperation",
    "EditMemo",
    "MemoOperation",
    "MemoOperationsOutcome",
    "RejectedMemoOperation",
    "RemoveMemo",
    "apply_memo_operations",
]
