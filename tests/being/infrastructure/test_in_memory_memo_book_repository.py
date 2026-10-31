from __future__ import annotations

import pytest

from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.memo_book import MemoAdded, MemoBook, MemoKind
from ai_rpg_world.being.infrastructure.in_memory_memo_book_repository import (
    InMemoryMemoBookRepository,
)
from tests.event_handoff_helpers import discard_events

ADA = BeingId("being-ada")
BEN = BeingId("being-ben")


def _book(being_id: BeingId = ADA, text: str = "事務所で鍵を取る") -> MemoBook:
    book = MemoBook.empty(being_id)
    book.add(
        memo_id="3f2a7b9c-1d2e-4f00-8a00-000000000001",
        kind=MemoKind.TODO,
        text=text,
        provenance=None,
        turn=1,
        environment_name="水門の町",
    )
    return book


def _texts(book: MemoBook) -> list[str]:
    return [m.text for m in book.memos]


class TestInMemoryMemoBookRepository:
    """InMemoryMemoBookRepository が、Being ごとにメモ帳を 1 つ持ち、丸ごと置き換えることを保証する。"""

    def test_a_being_without_memos_gets_an_empty_book(self) -> None:
        """まだ何も保存していない Being には、その Being の空のメモ帳を返す。"""
        repository = InMemoryMemoBookRepository(handoff=discard_events)

        book = repository.get(ADA)

        assert (book.being_id, book.memos) == (ADA, ())

    def test_saved_book_comes_back_only_for_its_being(self) -> None:
        """保存したメモ帳は持ち主の Being にだけ返り、別の Being は空のまま。"""
        repository = InMemoryMemoBookRepository(handoff=discard_events)

        repository.save(_book())

        assert (_texts(repository.get(ADA)), repository.get(BEN).memos) == (["事務所で鍵を取る"], ())

    def test_save_replaces_the_whole_book(self) -> None:
        """もう一度保存すると、前のメモ帳を丸ごと置き換える。"""
        repository = InMemoryMemoBookRepository(handoff=discard_events)
        repository.save(_book())

        repository.save(_book(text="水門を見に行く"))

        assert _texts(repository.get(ADA)) == ["水門を見に行く"]

    def test_replace_all_with_an_empty_book_leaves_no_memo(self) -> None:
        """持ち越しから空のメモ帳で戻すと、前に保存したメモは残らず、空のメモ帳を返す。"""
        repository = InMemoryMemoBookRepository(handoff=discard_events)
        repository.save(_book())

        repository.replace_all_by_being(MemoBook.empty(ADA))

        assert repository.get(ADA).memos == ()

    def test_replace_all_puts_the_given_book(self) -> None:
        """持ち越しから戻すと、渡したメモ帳がそのまま入る。"""
        repository = InMemoryMemoBookRepository(handoff=discard_events)

        repository.replace_all_by_being(_book())

        assert _texts(repository.get(ADA)) == ["事務所で鍵を取る"]


class TestTheRepositoryHandsOutCopies:
    """InMemoryMemoBookRepository が、出し入れのたびに写しを渡し、save し忘れた書き換えを保存したように見せないことを保証する。"""

    def test_changing_a_fetched_book_without_saving_leaves_the_store(self) -> None:
        """取り出したメモ帳を書き換えても、save しなければ、次に取り出したメモ帳は前のまま。"""
        repository = InMemoryMemoBookRepository(handoff=discard_events)
        repository.save(_book())

        repository.get(ADA).remove("m_3f2a7b")

        assert _texts(repository.get(ADA)) == ["事務所で鍵を取る"]

    def test_changing_a_book_after_saving_leaves_the_store(self) -> None:
        """保存したあとで渡したメモ帳を書き換えても、保存先は保存した時のまま。"""
        repository = InMemoryMemoBookRepository(handoff=discard_events)
        book = _book()
        repository.save(book)

        book.remove("m_3f2a7b")

        assert _texts(repository.get(ADA)) == ["事務所で鍵を取る"]

    def test_recorded_events_are_not_stored(self) -> None:
        """ためたイベントは保存先に残らず、取り出したメモ帳はイベントを持たない。"""
        repository = InMemoryMemoBookRepository(handoff=discard_events)

        repository.save(_book())

        assert repository.get(ADA).get_events() == []


class TestHandoff:
    """メモ帳を保存するときに、ためたイベント (MemoAdded など) を取り出して配り手に渡すことを保証する (design_decisions D1837 の 6)。"""

    def test_saved_events_are_handed_off_and_cleared(self) -> None:
        """メモを足したメモ帳を保存すると、MemoAdded が配り手に渡り、呼び手のメモ帳のイベントは空になる。"""
        handed: list[object] = []
        repository = InMemoryMemoBookRepository(handoff=handed.extend)
        book = _book()

        repository.save(book)

        assert [type(e) for e in handed] == [MemoAdded]
        assert book.get_events() == []

    def test_pending_events_without_handoff_stop_before_saving(self) -> None:
        """配り手の無い保存先に、イベントのたまったメモ帳を保存しようとすると、保存する前に RuntimeError で止まる。"""
        repository = InMemoryMemoBookRepository()

        with pytest.raises(RuntimeError):
            repository.save(_book())
        assert repository.get(ADA).memos == ()
