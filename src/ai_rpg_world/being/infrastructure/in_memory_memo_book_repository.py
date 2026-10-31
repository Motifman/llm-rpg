from __future__ import annotations

from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.memo_book import MemoBook, MemoBookRepository
from ai_rpg_world.being.infrastructure.event_handoff import EventHandoff, save_and_hand_off


def _require_book(book: object) -> MemoBook:
    if not isinstance(book, MemoBook):
        raise TypeError("book must be MemoBook")
    return book


def _copy(book: MemoBook) -> MemoBook:
    """メモは中身の変わらない値なので、同じメモを持つ新しい集約を作れば写しになる。ためたイベントは写さない。"""
    return MemoBook(book.being_id, memos=book.memos)


class InMemoryMemoBookRepository(MemoBookRepository):
    """出し入れのたびに写しを渡す。同じ集約を指し続けると、save し忘れた書き換えも保存されたように見えるため。

    保存した集約がためたイベントは、``handoff`` に渡す。
    """

    def __init__(self, *, handoff: EventHandoff | None = None) -> None:
        self._by_being: dict[BeingId, MemoBook] = {}
        self._handoff = handoff

    def get(self, being_id: BeingId) -> MemoBook:
        stored = self._by_being.get(being_id)
        return MemoBook.empty(being_id) if stored is None else _copy(stored)

    def save(self, book: MemoBook) -> None:
        _require_book(book)

        def store() -> None:
            self._by_being[book.being_id] = _copy(book)

        save_and_hand_off(book, self._handoff, store)

    def replace_all_by_being(self, book: MemoBook) -> None:
        if not _require_book(book).memos:
            self._by_being.pop(book.being_id, None)
            return
        self.save(book)


__all__ = ["InMemoryMemoBookRepository"]
