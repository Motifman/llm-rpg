from __future__ import annotations

import itertools
from typing import Any

import pytest

from ai_rpg_world.being.application.memo_arguments import (
    REJECTED_FROM_NOT_NEEDED,
    REJECTED_INVALID,
    REJECTED_LIMIT_REACHED,
    REJECTED_MISSING_PROVENANCE,
    REJECTED_NO_SUCH_MEMO,
    REJECTED_NOT_AN_OBJECT,
    REJECTED_PROVENANCE_OUTSIDE_FACT,
    REJECTED_TEXT_TOO_LONG,
    REJECTED_UNKNOWN_EPISODE,
    REJECTED_UNKNOWN_KIND,
)
from ai_rpg_world.being.application.write_memos import WriteMemos, WriteMemosCommand, WrittenMemos
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode import Episode, EpisodeIndex
from ai_rpg_world.being.domain.memo_book import (
    KIND_LIMITS,
    MemoAddition,
    MemoBook,
    MemoBookRepository,
    MemoKind,
)
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import InMemoryEpisodeRepository
from ai_rpg_world.being.infrastructure.in_memory_memo_book_repository import InMemoryMemoBookRepository
from tests.event_handoff_helpers import discard_events

ADA = BeingId("being-ada")

#: 試験をまたいで重ならない ID。メモ帳にある ID と重なると、別の決まりで外れて見える。
_SERIALS = itertools.count(1)


def _new_id() -> str:
    return f"{next(_SERIALS):06x}aa-1d2e-4f00-8a00-000000000000"


def _todo(text: str) -> dict[str, Any]:
    return {"do": "add", "kind": "todo", "text": text}


def _fact_from_episode(handle: str) -> dict[str, Any]:
    return {
        "do": "add",
        "kind": "fact",
        "text": "籠は 3 人まで",
        "source": "episode",
        "certainty": "sure",
        "from": handle,
    }


class _Memory:
    def __init__(self) -> None:
        self.memo_books = InMemoryMemoBookRepository(handoff=discard_events)
        self.episodes = InMemoryEpisodeRepository(handoff=discard_events)

    def write(self, *items: Any, episode_source_offered: bool = False) -> WrittenMemos:
        return self.write_raw(list(items), episode_source_offered=episode_source_offered)

    def write_raw(self, memo: Any, *, episode_source_offered: bool = False) -> WrittenMemos:
        return WriteMemos(memo_books=self.memo_books, episodes=self.episodes, new_memo_id=_new_id).execute(
            WriteMemosCommand(
                being_id=ADA,
                memo=memo,
                episode_source_offered=episode_source_offered,
                turn=7,
                environment_name="水門の町",
            )
        )

    def memos(self) -> list[str]:
        return [m.text for m in self.memo_books.get(ADA).memos]

    def remember_episode(self) -> str:
        episode = Episode.write(
            being_id=ADA,
            episode_id="3f2a7b00-0000-4000-8000-00000000abcd",
            environment_name="水門の町",
            written_turn=1,
            index=EpisodeIndex(summary="籠に乗った", recall_when="籠の話が出たとき"),
            body="籠には 3 人しか乗れなかった。",
        )
        self.episodes.add(episode)
        return episode.handle


def _full_of_todos() -> _Memory:
    memory = _Memory()
    memory.write(*(_todo(f"用事{n}") for n in range(KIND_LIMITS[MemoKind.TODO])))
    return memory


class TestWritingMemos:
    """WriteMemos が、行動の引数 memo に書かれた操作を順にメモ帳へ当てて保存し、当てた操作と外した操作を返すことを保証する。"""

    def test_add_is_saved_with_turn_and_environment(self) -> None:
        """足す操作は、渡したターンと環境の名前でメモを作って保存し、位置・操作の種類・メモを返す。"""
        memory = _Memory()

        written = memory.write(_todo(" 事務所で鍵を取る "))

        (memo,) = memory.memo_books.get(ADA).memos
        assert (memo.text, memo.written_turn, memo.environment_name) == ("事務所で鍵を取る", 7, "水門の町")
        assert [(w.index, w.do, w.memo) for w in written.written] == [(0, "add", memo)]
        assert written.unwritten == ()

    def test_edit_and_remove_are_written_in_order(self) -> None:
        """書き換えと消すを続けて書くと、どちらも当たり、消したメモも当てた操作として返る。"""
        memory = _Memory()
        memory.write(_todo("鍵を取る"), _todo("水門を見に行く"))
        first, second = memory.memo_books.get(ADA).memos

        written = memory.write(
            {"do": "edit", "id": first.handle, "text": "鍵を二つ取る"}, {"do": "remove", "id": second.handle}
        )

        assert memory.memos() == ["鍵を二つ取る"]
        assert [(w.do, w.memo.handle) for w in written.written] == [("edit", first.handle), ("remove", second.handle)]

    def test_written_memos_are_the_ones_the_book_recorded(self) -> None:
        """当てた操作 1 件ごとに、メモ帳がためたイベントのメモを、当てた順に返す。外した操作はイベントを残さない。"""
        memory = _Memory()

        written = memory.write(_todo("鍵を取る"), {"do": "remove", "id": "m_000000"}, _todo("水門を見に行く"))

        assert [(w.index, w.memo.text) for w in written.written] == [(0, "鍵を取る"), (2, "水門を見に行く")]

    def test_events_left_in_the_book_stop_the_writing(self) -> None:
        """取り出したメモ帳に前のイベントが残っていて当てた操作と数が合わなければ、保存せずに止まる。"""

        class _StaleRepository(MemoBookRepository):
            def __init__(self) -> None:
                self.saved: list[MemoBook] = []

            def get(self, being_id: BeingId) -> MemoBook:
                book = MemoBook.empty(being_id)
                book.write(
                    MemoAddition(MemoKind.TODO, "前の用事", None),
                    turn=1,
                    environment_name="水門の町",
                    new_memo_id=_new_id,
                )
                return book

            def save(self, book: MemoBook) -> None:
                self.saved.append(book)

            def replace_all_by_being(self, book: MemoBook) -> None:
                raise AssertionError

        repository = _StaleRepository()
        use_case = WriteMemos(memo_books=repository, episodes=InMemoryEpisodeRepository(), new_memo_id=_new_id)
        command = WriteMemosCommand(
            being_id=ADA, memo=[_todo("鍵を取る")], episode_source_offered=False, turn=7, environment_name="水門の町"
        )

        with pytest.raises(RuntimeError):
            use_case.execute(command)
        assert repository.saved == []

    def test_over_the_limit_only_that_add_is_unwritten(self) -> None:
        """やることが上限のとき、やることを足す操作だけが分類つきで外れ、同じ行動に書いた人についての操作は当たる。"""
        memory = _full_of_todos()

        written = memory.write(_todo("もう一つ"), {"do": "add", "kind": "person", "text": "ミオは水門に詳しい"})

        assert [(u.index, u.reason, u.kind) for u in written.unwritten] == [(0, REJECTED_LIMIT_REACHED, MemoKind.TODO)]
        assert memory.memos()[-1] == "ミオは水門に詳しい"

    def test_remove_before_add_makes_room_in_the_same_call(self) -> None:
        """上限のやることを消してから足すと、同じ行動の中で足せる。"""
        memory = _full_of_todos()
        oldest = memory.memo_books.get(ADA).memos[0].handle

        written = memory.write({"do": "remove", "id": oldest}, _todo("新しい用事"))

        assert written.unwritten == ()
        assert memory.memos()[-1] == "新しい用事"

    @pytest.mark.parametrize(
        "item",
        [{"do": "edit", "id": "m_000000", "text": "鍵"}, {"do": "remove", "id": "m_000000"}],
        ids=["edit", "remove"],
    )
    def test_unknown_handle_is_unwritten_with_the_handle(self, item: dict[str, Any]) -> None:
        """メモ帳に無い呼び名を書き換えたり消したりする操作は、呼び名を添えて外れ、メモ帳は変わらない。"""
        memory = _Memory()
        memory.write(_todo("鍵を取る"))

        written = memory.write(item)

        assert [(u.reason, u.detail, u.raw) for u in written.unwritten] == [(REJECTED_NO_SUCH_MEMO, "m_000000", item)]
        assert memory.memos() == ["鍵を取る"]

    def test_unknown_episode_is_unwritten_with_the_handle(self) -> None:
        """出どころに知らないエピソードの呼び名を書いた分かったことは、呼び名を添えて外れる。"""
        written = _Memory().write(_fact_from_episode("ep_a07c33"), episode_source_offered=True)

        assert [(u.reason, u.detail) for u in written.unwritten] == [(REJECTED_UNKNOWN_EPISODE, "ep_a07c33")]

    def test_known_episode_source_is_written(self) -> None:
        """出どころのエピソードが本人のエピソードにあれば、分かったことを足せる。"""
        memory = _Memory()
        handle = memory.remember_episode()

        written = memory.write(_fact_from_episode(handle), episode_source_offered=True)

        assert written.unwritten == ()
        assert memory.memo_books.get(ADA).memos[0].provenance.source_from == handle  # type: ignore[union-attr]

    def test_fact_can_be_revised_to_a_known_episode_source(self) -> None:
        """分かったことを書き換えるとき、出どころを本人のエピソードに直せる。"""
        memory = _Memory()
        handle = memory.remember_episode()
        memory.write({"do": "add", "kind": "fact", "text": "籠は 3 人まで", "source": "self", "certainty": "guess"})
        memo = memory.memo_books.get(ADA).memos[0].handle

        written = memory.write({**_fact_from_episode(handle), "do": "edit", "id": memo}, episode_source_offered=True)

        assert written.unwritten == ()
        assert memory.memo_books.get(ADA).memos[0].provenance.source_from == handle  # type: ignore[union-attr]

    def test_episode_source_is_not_read_when_not_offered(self) -> None:
        """出どころにエピソードを出していない設定では、本人のエピソードがあっても出どころが崩れた操作として外す。"""
        memory = _Memory()
        handle = memory.remember_episode()

        written = memory.write(_fact_from_episode(handle))

        assert [u.reason for u in written.unwritten] == [REJECTED_MISSING_PROVENANCE]

    @pytest.mark.parametrize(
        ("item", "reason"),
        [
            (_todo("あ" * 61), REJECTED_TEXT_TOO_LONG),
            ({"do": "add", "kind": "fact", "text": "鍵"}, REJECTED_MISSING_PROVENANCE),
            (
                {"do": "add", "kind": "todo", "text": "鍵", "source": "self", "certainty": "sure"},
                REJECTED_PROVENANCE_OUTSIDE_FACT,
            ),
        ],
        ids=["text_61_chars", "fact_without_provenance", "todo_with_provenance"],
    )
    def test_rule_the_book_refuses_is_unwritten_with_its_reason(self, item: dict[str, Any], reason: str) -> None:
        """形は読めてもメモ帳の決まりに反する操作は、決まりごとの理由と元の値を持って外れる。"""
        written = _Memory().write(item)

        assert [(u.index, u.reason, u.raw) for u in written.unwritten] == [(0, reason, item)]

    def test_provenance_on_a_todo_edit_is_unwritten(self) -> None:
        """やることを書き換える操作に出どころを書くと外れる。"""
        memory = _Memory()
        memory.write(_todo("鍵を取る"))
        handle = memory.memo_books.get(ADA).memos[0].handle

        written = memory.write({"do": "edit", "id": handle, "text": "鍵", "source": "self", "certainty": "sure"})

        assert [u.reason for u in written.unwritten] == [REJECTED_PROVENANCE_OUTSIDE_FACT]

    @pytest.mark.parametrize(
        ("item", "reason"),
        [
            ({"do": "add", "kind": "note", "text": "あ" * 61}, REJECTED_UNKNOWN_KIND),
            (
                {"do": "add", "kind": "fact", "text": "あ" * 61, "source": "self", "certainty": "sure", "from": "門番"},
                REJECTED_FROM_NOT_NEEDED,
            ),
            ({"do": "edit", "id": "m_000000", "text": "あ" * 61}, REJECTED_NO_SUCH_MEMO),
        ],
        ids=["unknown_kind", "self_with_from", "edit_of_a_missing_memo"],
    )
    def test_text_too_long_yields_to_a_broken_shape(self, item: dict[str, Any], reason: str) -> None:
        """61 字の文にほかの不備も重なっていると、文の長さではなく、先に読む形や出どころの不備を理由にする。"""
        written = _Memory().write(item)

        assert [u.reason for u in written.unwritten] == [reason]

    def test_operation_refused_by_another_rule_carries_the_message(self) -> None:
        """理由を分けていない決まりで断られた操作は、書けない形として外れ、断った文を添える。"""
        memory = _Memory()
        memory.write(_todo("鍵を取る"))
        handle = memory.memo_books.get(ADA).memos[0].handle
        earlier = WriteMemos(memo_books=memory.memo_books, episodes=memory.episodes, new_memo_id=_new_id)

        written = earlier.execute(
            WriteMemosCommand(
                being_id=ADA,
                memo=[{"do": "edit", "id": handle, "text": "鍵"}],
                episode_source_offered=False,
                turn=3,
                environment_name="水門の町",
            )
        )

        ((unwritten),) = written.unwritten
        assert unwritten.reason == REJECTED_INVALID and unwritten.detail

    def test_unread_operations_come_before_refused_ones(self) -> None:
        """読めなかった操作を先に、メモ帳が断った操作を後に返し、どちらも配列の中の位置を持つ。"""
        written = _Memory().write({"do": "remove", "id": "m_000000"}, "壊れた")

        assert [(u.index, u.reason) for u in written.unwritten] == [
            (1, REJECTED_NOT_AN_OBJECT),
            (0, REJECTED_NO_SUCH_MEMO),
        ]

    def test_null_memo_writes_nothing(self) -> None:
        """memo が null なら、何も当てず、何も外さない。"""
        written = _Memory().write_raw(None)

        assert (written.written, written.unwritten) == ((), ())
