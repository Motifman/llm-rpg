from __future__ import annotations

import itertools

import pytest

from ai_rpg_world.being.application.memo_writing import (
    REJECTED_LIMIT_REACHED,
    REJECTED_NO_SUCH_MEMO,
    REJECTED_PROVENANCE_OUTSIDE_FACT,
    REJECTED_UNKNOWN_EPISODE,
    AddMemo,
    EditMemo,
    RemoveMemo,
    apply_memo_operations,
)
from ai_rpg_world.being.domain.memo_book import (
    KIND_LIMITS,
    MemoBook,
    MemoCertainty,
    MemoKind,
    MemoProvenance,
    MemoSource,
)

SURE_BY_SELF = MemoProvenance(source=MemoSource.SELF, certainty=MemoCertainty.SURE)
FROM_EPISODE = MemoProvenance(
    source=MemoSource.EPISODE, certainty=MemoCertainty.SURE, source_from="ep_a07c33"
)


#: 試験をまたいで重ならない ID。メモ帳にある ID と重なると、別の決まりで外れて見える。
_SERIALS = itertools.count(1)


def _new_id() -> str:
    return f"{next(_SERIALS):06x}aa-1d2e-4f00-8a00-000000000000"


def _apply(book: MemoBook, *operations: object, known_episode_handles: frozenset[str] = frozenset()):
    return apply_memo_operations(
        book,
        tuple(enumerate(operations)),  # type: ignore[arg-type]
        turn=7,
        environment_name="水門の町",
        known_episode_handles=known_episode_handles,
        new_memo_id=_new_id,
    )


def _todos(count: int) -> MemoBook:
    outcome = _apply(MemoBook.empty(), *(AddMemo(MemoKind.TODO, f"用事{n}", None) for n in range(count)))
    return outcome.book


class TestApplyingOperations:
    """apply_memo_operations が、1 回の行動に書かれた操作を順に 1 つのメモ帳へ当て、崩れた操作だけを外すことを保証する。"""

    def test_add_writes_turn_and_environment(self) -> None:
        """足す操作は、渡したターンと環境の名前でメモを作り、適用した操作として呼び名を返す。"""
        outcome = _apply(MemoBook.empty(), AddMemo(MemoKind.TODO, "事務所で鍵を取る", None))

        (memo,) = outcome.book.memos
        assert (memo.text, memo.written_turn, memo.environment_name) == ("事務所で鍵を取る", 7, "水門の町")
        assert [(a.index, a.memo.handle) for a in outcome.applied] == [(0, memo.handle)]
        assert outcome.rejected == ()

    def test_edit_and_remove_are_applied_in_order(self) -> None:
        """書き換えと消すを続けて書くと、どちらも当たり、消したメモは適用した操作に残る。"""
        book = _todos(2)
        first, second = book.memos

        outcome = _apply(book, EditMemo(first.handle, "鍵を二つ取る", None), RemoveMemo(second.handle))

        assert [m.text for m in outcome.book.memos] == ["鍵を二つ取る"]
        assert outcome.applied[1].memo == second

    def test_over_the_limit_only_that_add_is_rejected(self) -> None:
        """やることが上限のとき、やることを足す操作だけが外れ、同じ行動に書いた人についての操作は当たる。"""
        book = _todos(KIND_LIMITS[MemoKind.TODO])

        outcome = _apply(
            book,
            AddMemo(MemoKind.TODO, "もう一つ", None),
            AddMemo(MemoKind.PERSON, "ミオは水門に詳しい", None),
        )

        assert [(r.index, r.reason) for r in outcome.rejected] == [(0, REJECTED_LIMIT_REACHED)]
        assert outcome.rejected[0].kind is MemoKind.TODO
        assert outcome.book.memos[-1].text == "ミオは水門に詳しい"

    def test_remove_before_add_makes_room_in_the_same_call(self) -> None:
        """上限のやることを消してから足すと、同じ行動の中で足せる。"""
        book = _todos(KIND_LIMITS[MemoKind.TODO])

        outcome = _apply(book, RemoveMemo(book.memos[0].handle), AddMemo(MemoKind.TODO, "新しい用事", None))

        assert outcome.rejected == ()
        assert outcome.book.memos[-1].text == "新しい用事"

    @pytest.mark.parametrize("operation", [EditMemo("m_000000", "鍵", None), RemoveMemo("m_000000")])
    def test_unknown_handle_is_rejected(self, operation: object) -> None:
        """メモ帳に無い呼び名を書き換えたり消したりする操作は外れ、メモ帳は変わらない。"""
        book = _todos(1)

        outcome = _apply(book, operation)

        assert [r.reason for r in outcome.rejected] == [REJECTED_NO_SUCH_MEMO]
        assert outcome.book == book

    def test_provenance_on_a_todo_edit_is_rejected(self) -> None:
        """やることを書き換える操作に出どころを書くと外れる。"""
        book = _todos(1)

        outcome = _apply(book, EditMemo(book.memos[0].handle, "鍵", SURE_BY_SELF))

        assert [r.reason for r in outcome.rejected] == [REJECTED_PROVENANCE_OUTSIDE_FACT]

    def test_unknown_episode_source_is_rejected(self) -> None:
        """出どころに知らないエピソードの呼び名を書いた分かったことは外れる。"""
        outcome = _apply(MemoBook.empty(), AddMemo(MemoKind.FACT, "籠は 3 人まで", FROM_EPISODE))

        assert [r.reason for r in outcome.rejected] == [REJECTED_UNKNOWN_EPISODE]

    def test_known_episode_source_is_accepted(self) -> None:
        """出どころのエピソードの呼び名を知っていれば、分かったことを足せる。"""
        outcome = _apply(
            MemoBook.empty(),
            AddMemo(MemoKind.FACT, "籠は 3 人まで", FROM_EPISODE),
            known_episode_handles=frozenset({"ep_a07c33"}),
        )

        assert outcome.book.memos[0].provenance == FROM_EPISODE

    def test_rejected_operation_keeps_its_original_index(self) -> None:
        """外れた操作は、行動に書かれた配列の中の位置を持つ。"""
        outcome = apply_memo_operations(
            MemoBook.empty(),
            ((3, RemoveMemo("m_000000")),),
            turn=7,
            environment_name="水門の町",
            new_memo_id=lambda: "3f2a7b9c-1d2e-4f00-8a00-000000000001",
        )

        assert outcome.rejected[0].index == 3
