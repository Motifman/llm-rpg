from __future__ import annotations

from ai_rpg_world.being.domain.memo_book import MemoBook, MemoBookRepository
from ai_rpg_world.domain.being.value_object.being_id import BeingId


class InMemoryMemoBookRepository(MemoBookRepository):
    def __init__(self) -> None:
        self._by_being: dict[BeingId, MemoBook] = {}

    def get(self, being_id: BeingId) -> MemoBook:
        return self._by_being.get(being_id, MemoBook.empty())

    def save(self, being_id: BeingId, book: MemoBook) -> None:
        if not isinstance(book, MemoBook):
            raise TypeError("book must be MemoBook")
        self._by_being[being_id] = book

    def replace_all_by_being(self, being_id: BeingId, book: MemoBook) -> None:
        if not isinstance(book, MemoBook):
            raise TypeError("book must be MemoBook")
        if not book.memos:
            self._by_being.pop(being_id, None)
            return
        self._by_being[being_id] = book


__all__ = ["InMemoryMemoBookRepository"]
