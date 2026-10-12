from __future__ import annotations

from ai_rpg_world.being.domain.memo_book import MemoBook, MemoKind
from ai_rpg_world.being.infrastructure.in_memory_memo_book_repository import (
    InMemoryMemoBookRepository,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

ADA = BeingId("being-ada")
BEN = BeingId("being-ben")


def _book(text: str = "事務所で鍵を取る") -> MemoBook:
    return MemoBook.empty().add(
        memo_id="3f2a7b9c-1d2e-4f00-8a00-000000000001",
        kind=MemoKind.TODO,
        text=text,
        provenance=None,
        turn=1,
        environment_name="水門の町",
    )


class TestInMemoryMemoBookRepository:
    """InMemoryMemoBookRepository が、Being ごとにメモ帳を 1 つ持ち、丸ごと置き換えることを保証する。"""

    def test_a_being_without_memos_gets_an_empty_book(self) -> None:
        """まだ何も保存していない Being には、空のメモ帳を返す。"""
        repository = InMemoryMemoBookRepository()

        assert repository.get(ADA) == MemoBook.empty()

    def test_saved_book_comes_back_only_for_its_being(self) -> None:
        """保存したメモ帳はその Being にだけ返り、別の Being は空のまま。"""
        repository = InMemoryMemoBookRepository()

        repository.save(ADA, _book())

        assert (repository.get(ADA), repository.get(BEN)) == (_book(), MemoBook.empty())

    def test_save_replaces_the_whole_book(self) -> None:
        """もう一度保存すると、前のメモ帳を丸ごと置き換える。"""
        repository = InMemoryMemoBookRepository()
        repository.save(ADA, _book())

        repository.save(ADA, _book("水門を見に行く"))

        assert [m.text for m in repository.get(ADA).memos] == ["水門を見に行く"]

    def test_replace_all_with_an_empty_book_forgets_the_being(self) -> None:
        """持ち越しから空のメモ帳で戻すと、その Being の記録が消え、空のメモ帳を返す。"""
        repository = InMemoryMemoBookRepository()
        repository.save(ADA, _book())

        repository.replace_all_by_being(ADA, MemoBook.empty())

        assert repository.get(ADA) == MemoBook.empty()
        assert ADA not in repository._by_being

    def test_replace_all_puts_the_given_book(self) -> None:
        """持ち越しから戻すと、渡したメモ帳がそのまま入る。"""
        repository = InMemoryMemoBookRepository()

        repository.replace_all_by_being(ADA, _book())

        assert repository.get(ADA) == _book()
