from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from ai_rpg_world.being.application.memo_argument import MEMO_FIELD_NAME
from ai_rpg_world.being.application.memo_arguments import (
    MemoRefusal,
    ReadMemoOperation,
    read_memo_operations,
    refusal_reason,
)
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode import EpisodeRepository
from ai_rpg_world.being.domain.memo_book import Memo, MemoBookRepository, MemoKind
from ai_rpg_world.domain.being.exception.being_exceptions import (
    MemoLimitReachedException,
    MemoNotFoundException,
    MemoSourceEpisodeUnknownException,
    MemoValidationException,
)


@dataclass(frozen=True, kw_only=True)
class WriteMemosCommand:
    """``memo`` は行動の引数 memo に書かれていた値。``turn`` はメモに残す記憶のターン。"""

    being_id: BeingId
    memo: Any
    episode_source_offered: bool
    turn: int
    environment_name: str


@dataclass(frozen=True)
class WrittenMemo:
    """``memo`` は足した・書き換えたあとのメモか、消したメモ。"""

    index: int
    do: str
    memo: Memo


@dataclass(frozen=True)
class UnwrittenMemo:
    """``index`` は配列の中の位置で、引数ごと崩れていれば None。"""

    index: int | None
    reason: str
    raw: Any
    kind: MemoKind | None = None
    detail: str | None = None


@dataclass(frozen=True)
class WrittenMemos:
    written: tuple[WrittenMemo, ...]
    unwritten: tuple[UnwrittenMemo, ...]


class WriteMemos:
    def __init__(
        self,
        *,
        memo_books: MemoBookRepository,
        episodes: EpisodeRepository,
        new_memo_id: Callable[[], str] = lambda: str(uuid4()),
    ) -> None:
        self._memo_books = memo_books
        self._episodes = episodes
        self._new_memo_id = new_memo_id

    def execute(self, command: WriteMemosCommand) -> WrittenMemos:
        read = read_memo_operations(
            {MEMO_FIELD_NAME: command.memo}, episode_source_offered=command.episode_source_offered
        )
        known_episode_handles = (
            frozenset(e.handle for e in self._episodes.list_by_being(command.being_id))
            if command.episode_source_offered
            else frozenset()
        )
        book = self._memo_books.get(command.being_id)
        accepted: list[ReadMemoOperation] = []
        refused: list[UnwrittenMemo] = []
        for read_operation in read.operations:
            try:
                book.write(
                    read_operation.operation,
                    turn=command.turn,
                    environment_name=command.environment_name,
                    new_memo_id=self._new_memo_id,
                    known_episode_handles=known_episode_handles,
                )
            except MemoLimitReachedException as refusal:
                refused.append(_unwritten(read_operation, refusal, kind=refusal.kind))
                continue
            except (MemoNotFoundException, MemoSourceEpisodeUnknownException) as refusal:
                refused.append(_unwritten(read_operation, refusal, detail=refusal.handle))
                continue
            except MemoValidationException as refusal:
                refused.append(_unwritten(read_operation, refusal, detail=str(refusal)))
                continue
            accepted.append(read_operation)
        events = book.get_events()
        if len(events) != len(accepted):
            raise RuntimeError(f"{len(accepted)} memo operations were written but the book recorded {len(events)}")
        self._memo_books.save(book)
        return WrittenMemos(
            written=tuple(WrittenMemo(r.index, r.do, e.memo) for r, e in zip(accepted, events, strict=True)),
            unwritten=(
                *(UnwrittenMemo(r.index, r.reason, r.raw) for r in read.rejected),
                *refused,
            ),
        )


def _unwritten(
    read_operation: ReadMemoOperation,
    refusal: MemoRefusal,
    *,
    kind: MemoKind | None = None,
    detail: str | None = None,
) -> UnwrittenMemo:
    return UnwrittenMemo(read_operation.index, refusal_reason(refusal), read_operation.raw, kind=kind, detail=detail)


__all__ = ["UnwrittenMemo", "WriteMemos", "WriteMemosCommand", "WrittenMemo", "WrittenMemos"]
