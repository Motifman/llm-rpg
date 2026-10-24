from __future__ import annotations

import dataclasses

import pytest

from ai_rpg_world.being.domain.memo_book import (
    KIND_LIMITS,
    Memo,
    MemoAdded,
    MemoBook,
    MemoCertainty,
    MemoEdited,
    MemoKind,
    MemoProvenance,
    MemoRemoved,
    MemoSource,
)
from ai_rpg_world.domain.being.exception.being_exceptions import (
    MemoLimitReachedException,
    MemoNotFoundException,
    MemoValidationException,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

ADA = BeingId("being-ada")

FIRST_ID = "3f2a7b9c-1d2e-4f00-8a00-000000000001"
SECOND_ID = "91c0de00-1d2e-4f00-8a00-000000000002"
SAME_PREFIX_ID = "3f2a7b11-1d2e-4f00-8a00-000000000003"
SURE_BY_SELF = MemoProvenance(source=MemoSource.SELF, certainty=MemoCertainty.SURE)
FROM_UNKNOWN_EPISODE = MemoProvenance(
    source=MemoSource.EPISODE, certainty=MemoCertainty.SURE, source_from="ep_a07c33"
)


def _id(n: int) -> str:
    """先頭 6 文字が n ごとに違う ID。呼び名が伸びずに済む。"""
    return f"{n:06x}aa-1d2e-4f00-8a00-000000000000"


def _add(book: MemoBook, **overrides: object) -> MemoBook:
    """足したあとの同じメモ帳を返す。試験で足すのを続けて書くため。"""
    fields: dict[str, object] = {
        "memo_id": FIRST_ID,
        "kind": MemoKind.TODO,
        "text": "事務所で鍵を取る",
        "provenance": None,
        "turn": 3,
        "environment_name": "水門の町",
    }
    fields.update(overrides)
    book.add(**fields)  # type: ignore[arg-type]
    return book


class TestMemoProvenance:
    """MemoProvenance が、出どころごとに「誰から」「どのエピソードから」の要る組み合わせを守ることを保証する。"""

    def test_heard_requires_who(self) -> None:
        """出どころが「人から聞いた」のに誰からが無ければ MemoValidationException を投げる。"""
        with pytest.raises(MemoValidationException):
            MemoProvenance(source=MemoSource.HEARD, certainty=MemoCertainty.GUESS)

    def test_heard_keeps_who(self) -> None:
        """出どころが「人から聞いた」なら、誰からの文をそのまま持つ。"""
        provenance = MemoProvenance(
            source=MemoSource.HEARD, certainty=MemoCertainty.GUESS, source_from="ミオ"
        )

        assert provenance.source_from == "ミオ"

    def test_episode_requires_an_episode_handle(self) -> None:
        """出どころが「エピソードから」なら、ep_ で始まる呼び名でないと MemoValidationException を投げる。"""
        with pytest.raises(MemoValidationException):
            MemoProvenance(
                source=MemoSource.EPISODE, certainty=MemoCertainty.SURE, source_from="ミオ"
            )

    def test_self_must_not_name_a_source(self) -> None:
        """出どころが「自分で確かめた」なのに誰からを持たせると MemoValidationException を投げる。"""
        with pytest.raises(MemoValidationException):
            MemoProvenance(
                source=MemoSource.SELF, certainty=MemoCertainty.SURE, source_from="ミオ"
            )


class TestAddingAMemo:
    """MemoBook.add が、分類ごとの必須の組み合わせと文の長さを守ってメモを作ることを保証する。"""

    def test_added_memo_has_handle_from_id_and_no_edit_yet(self) -> None:
        """足したメモは、呼び名が m_ と ID の先頭 6 文字で、書いた時と環境の名前を持ち、書き換えた時が無い。"""
        book = _add(MemoBook.empty(ADA))

        (memo,) = book.memos
        assert memo.handle == "m_3f2a7b"
        assert (memo.kind, memo.text, memo.provenance) == (MemoKind.TODO, "事務所で鍵を取る", None)
        assert (memo.written_turn, memo.edited_turn, memo.environment_name) == (3, None, "水門の町")

    def test_adding_changes_the_book_itself_and_returns_nothing(self) -> None:
        """足すとそのメモ帳の中身が変わり、add は何も返さない。"""
        book = MemoBook.empty(ADA)

        returned = book.add(
            memo_id=FIRST_ID,
            kind=MemoKind.TODO,
            text="事務所で鍵を取る",
            provenance=None,
            turn=3,
            environment_name="水門の町",
        )

        assert returned is None
        assert [m.handle for m in book.memos] == ["m_3f2a7b"]

    def test_sixty_characters_are_accepted(self) -> None:
        """文はちょうど 60 字なら受け付ける。"""
        book = _add(MemoBook.empty(ADA), text="あ" * 60)

        assert book.memos[0].text == "あ" * 60

    def test_sixty_one_characters_are_rejected(self) -> None:
        """文が 61 字あると MemoValidationException を投げる。"""
        with pytest.raises(MemoValidationException):
            _add(MemoBook.empty(ADA), text="あ" * 61)

    @pytest.mark.parametrize("blank", ["", "   ", "\n"])
    def test_blank_text_is_rejected(self, blank: str) -> None:
        """文が空や空白だけなら MemoValidationException を投げる。"""
        with pytest.raises(MemoValidationException):
            _add(MemoBook.empty(ADA), text=blank)

    def test_fact_without_provenance_is_rejected(self) -> None:
        """分かったことに出どころと確かさが無ければ MemoValidationException を投げる。"""
        with pytest.raises(MemoValidationException):
            _add(MemoBook.empty(ADA), kind=MemoKind.FACT, provenance=None)

    @pytest.mark.parametrize("kind", [MemoKind.TODO, MemoKind.PERSON])
    def test_provenance_outside_fact_is_rejected(self, kind: MemoKind) -> None:
        """やること・人についてに出どころを持たせると MemoValidationException を投げる。"""
        with pytest.raises(MemoValidationException):
            _add(MemoBook.empty(ADA), kind=kind, provenance=SURE_BY_SELF)

    def test_fact_keeps_provenance(self) -> None:
        """分かったことは、渡した出どころと確かさを持つ。"""
        book = _add(MemoBook.empty(ADA), kind=MemoKind.FACT, provenance=SURE_BY_SELF)

        assert book.memos[0].provenance == SURE_BY_SELF

    def test_episode_source_must_be_a_known_episode(self) -> None:
        """出どころのエピソードの呼び名が、知っている呼び名に無ければ MemoValidationException を投げる。"""
        provenance = MemoProvenance(
            source=MemoSource.EPISODE, certainty=MemoCertainty.SURE, source_from="ep_a07c33"
        )

        with pytest.raises(MemoValidationException):
            _add(MemoBook.empty(ADA), kind=MemoKind.FACT, provenance=provenance)

    def test_episode_source_is_accepted_when_known(self) -> None:
        """出どころのエピソードの呼び名が、知っている呼び名にあれば受け付ける。"""
        provenance = MemoProvenance(
            source=MemoSource.EPISODE, certainty=MemoCertainty.SURE, source_from="ep_a07c33"
        )

        book = _add(
            MemoBook.empty(ADA),
            kind=MemoKind.FACT,
            provenance=provenance,
            known_episode_handles={"ep_a07c33"},
        )

        assert book.memos[0].provenance == provenance

    def test_handle_grows_when_the_short_one_is_taken(self) -> None:
        """先頭 6 文字が同じ ID のメモを足すと、後から足した方だけが 7 文字の呼び名になる。"""
        book = _add(_add(MemoBook.empty(ADA)), memo_id=SAME_PREFIX_ID)

        assert [m.handle for m in book.memos] == ["m_3f2a7b", "m_3f2a7b1"]

    def test_the_same_id_twice_is_rejected(self) -> None:
        """同じ ID のメモをもう一度足すと MemoValidationException を投げる。"""
        with pytest.raises(MemoValidationException):
            _add(_add(MemoBook.empty(ADA)))

    def test_memos_stay_in_written_order(self) -> None:
        """メモは分類によらず、足した順に並ぶ。"""
        book = _add(MemoBook.empty(ADA), kind=MemoKind.PERSON, text="ミオは水門に詳しい")
        book = _add(book, memo_id=SECOND_ID, text="鍵を取る")

        assert [m.text for m in book.memos] == ["ミオは水門に詳しい", "鍵を取る"]


class TestKindLimits:
    """MemoBook が、分類ごとの件数の上限 (やること 5 / 分かったこと 10 / 人について 5) を自分で守ることを保証する。"""

    def test_limits_are_five_ten_five(self) -> None:
        """件数の上限は、やること 5 件、分かったこと 10 件、人について 5 件。"""
        assert KIND_LIMITS == {MemoKind.TODO: 5, MemoKind.FACT: 10, MemoKind.PERSON: 5}

    @pytest.mark.parametrize("kind", list(MemoKind))
    def test_adding_beyond_the_limit_is_rejected(self, kind: MemoKind) -> None:
        """上限まで足した分類にもう 1 件足すと MemoLimitReachedException を投げ、件数は上限のまま。"""
        provenance = SURE_BY_SELF if kind is MemoKind.FACT else None
        book = MemoBook.empty(ADA)
        for n in range(KIND_LIMITS[kind]):
            book = _add(book, memo_id=_id(n), kind=kind, provenance=provenance)

        with pytest.raises(MemoLimitReachedException):
            _add(book, memo_id=_id(99), kind=kind, provenance=provenance)
        assert len(book.memos) == KIND_LIMITS[kind]

    def test_a_full_kind_does_not_block_another_kind(self) -> None:
        """やることが上限でも、人についてのメモは足せる。"""
        book = MemoBook.empty(ADA)
        for n in range(KIND_LIMITS[MemoKind.TODO]):
            book = _add(book, memo_id=_id(n))

        book = _add(book, memo_id=_id(99), kind=MemoKind.PERSON, text="ミオは水門に詳しい")

        assert book.memos[-1].kind is MemoKind.PERSON

    def test_a_book_built_beyond_the_limit_is_rejected(self) -> None:
        """上限を超えるメモを並べてメモ帳を作ると MemoValidationException を投げる。"""
        memos = _add_many(MemoKind.TODO, KIND_LIMITS[MemoKind.TODO]).memos
        extra = _add(MemoBook.empty(ADA), memo_id=_id(99)).memos

        with pytest.raises(MemoValidationException):
            MemoBook(ADA, memos=(*memos, *extra))


def _add_many(kind: MemoKind, count: int) -> MemoBook:
    book = MemoBook.empty(ADA)
    for n in range(count):
        book = _add(book, memo_id=_id(n), kind=kind)
    return book


class TestEditingAMemo:
    """MemoBook.edit が、呼び名で選んだメモの文 (分かったことなら出どころも) を書き換え、ほかは変えないことを保証する。"""

    def test_edit_changes_text_and_records_the_turn(self) -> None:
        """書き換えると、文が変わり、書き換えた時が記録され、分類・書いた時・環境の名前・並びは変わらない。"""
        book = _add(_add(MemoBook.empty(ADA)), memo_id=SECOND_ID, text="水門を見に行く")

        second = book.memos[1]

        book.edit("m_3f2a7b", text="事務所の金庫で鍵を取る", turn=8)

        first = book.memos[0]
        assert (first.handle, first.text, first.edited_turn) == ("m_3f2a7b", "事務所の金庫で鍵を取る", 8)
        assert (first.kind, first.written_turn, first.environment_name) == (MemoKind.TODO, 3, "水門の町")
        assert book.memos[1] == second

    def test_edit_of_a_fact_can_replace_provenance(self) -> None:
        """分かったことを書き換えるとき、出どころと確かさを渡すと置き換わる。"""
        book = _add(MemoBook.empty(ADA), kind=MemoKind.FACT, provenance=SURE_BY_SELF)
        heard = MemoProvenance(
            source=MemoSource.HEARD, certainty=MemoCertainty.GUESS, source_from="ミオ"
        )

        book.edit("m_3f2a7b", text="弁の目盛りが関係する", provenance=heard, turn=8)

        assert book.memos[0].provenance == heard

    def test_edit_of_a_fact_without_provenance_keeps_it(self) -> None:
        """分かったことを書き換えるとき、出どころを渡さなければ前の出どころのまま。"""
        book = _add(MemoBook.empty(ADA), kind=MemoKind.FACT, provenance=SURE_BY_SELF)

        book.edit("m_3f2a7b", text="弁の目盛りが関係する", turn=8)

        assert book.memos[0].provenance == SURE_BY_SELF

    def test_provenance_on_a_todo_edit_is_rejected(self) -> None:
        """やることを書き換えるときに出どころを渡すと MemoValidationException を投げる。"""
        book = _add(MemoBook.empty(ADA))

        with pytest.raises(MemoValidationException):
            book.edit("m_3f2a7b", text="鍵を取る", provenance=SURE_BY_SELF, turn=8)

    def test_unknown_handle_is_rejected(self) -> None:
        """メモ帳に無い呼び名を書き換えようとすると MemoNotFoundException を投げる。"""
        with pytest.raises(MemoNotFoundException):
            _add(MemoBook.empty(ADA)).edit("m_000000", text="鍵を取る", turn=8)

    def test_edit_before_written_turn_is_rejected(self) -> None:
        """書いた時より前のターンで書き換えると MemoValidationException を投げる。"""
        with pytest.raises(MemoValidationException):
            _add(MemoBook.empty(ADA), turn=5).edit("m_3f2a7b", text="鍵を取る", turn=4)

    def test_edit_before_the_last_edit_is_rejected(self) -> None:
        """前に書き換えた時より前のターンで書き換えると MemoValidationException を投げる。"""
        book = _add(MemoBook.empty(ADA), turn=5)
        book.edit("m_3f2a7b", text="鍵を取る", turn=8)

        with pytest.raises(MemoValidationException):
            book.edit("m_3f2a7b", text="鍵を二つ取る", turn=6)


class TestRemovingAMemo:
    """MemoBook.remove が、呼び名で選んだメモを記録から消すことを保証する。"""

    def test_remove_drops_the_memo_and_returns_nothing(self) -> None:
        """消すと、そのメモがメモ帳から無くなり、remove は何も返さない。"""
        book = _add(_add(MemoBook.empty(ADA)), memo_id=SECOND_ID, text="水門を見に行く")

        returned = book.remove("m_3f2a7b")

        assert returned is None
        assert [m.text for m in book.memos] == ["水門を見に行く"]

    def test_removing_frees_room_under_the_limit(self) -> None:
        """上限のやることを 1 件消すと、また 1 件足せる。"""
        book = _add_many(MemoKind.TODO, KIND_LIMITS[MemoKind.TODO])

        book.remove(book.memos[0].handle)

        assert len(_add(book, memo_id=_id(99)).memos) == KIND_LIMITS[MemoKind.TODO]

    def test_unknown_handle_is_rejected(self) -> None:
        """メモ帳に無い呼び名を消そうとすると MemoNotFoundException を投げる。"""
        with pytest.raises(MemoNotFoundException):
            _add(MemoBook.empty(ADA)).remove("m_000000")


class TestMemoInvariants:
    """Memo を直接組むときにも、呼び名・分類と出どころ・ターンの決まりが守られることを保証する。"""

    def _memo(self, **overrides: object) -> Memo:
        return dataclasses.replace(_add(MemoBook.empty(ADA)).memos[0], **overrides)

    def test_handle_not_from_the_id_is_rejected(self) -> None:
        """呼び名が ID の先頭から作られていなければ MemoValidationException を投げる。"""
        with pytest.raises(MemoValidationException):
            self._memo(handle="m_91c0de")

    def test_edited_turn_before_written_turn_is_rejected(self) -> None:
        """書き換えた時が書いた時より前なら MemoValidationException を投げる。"""
        with pytest.raises(MemoValidationException):
            self._memo(written_turn=5, edited_turn=4)

    def test_blank_environment_name_is_rejected(self) -> None:
        """環境の名前が空なら MemoValidationException を投げる。"""
        with pytest.raises(MemoValidationException):
            self._memo(environment_name=" ")

    def test_duplicate_handles_in_a_book_are_rejected(self) -> None:
        """ID が違っても同じ呼び名のメモが 2 件あるメモ帳は作れず、MemoValidationException を投げる。"""
        memo = _add(MemoBook.empty(ADA)).memos[0]
        same_handle = _add(MemoBook.empty(ADA), memo_id=SAME_PREFIX_ID).memos[0]

        with pytest.raises(MemoValidationException):
            MemoBook(ADA, memos=(memo, same_handle))

    def test_duplicate_ids_in_a_book_are_rejected(self) -> None:
        """同じ ID のメモが 2 件あるメモ帳は作れず、MemoValidationException を投げる。"""
        memo = _add(MemoBook.empty(ADA)).memos[0]
        longer = dataclasses.replace(memo, handle="m_3f2a7b9")

        with pytest.raises(MemoValidationException):
            MemoBook(ADA, memos=(memo, longer))

    def test_find_returns_the_memo_or_none(self) -> None:
        """呼び名で引くと、あればそのメモを、無ければ None を返す。"""
        book = _add(MemoBook.empty(ADA))

        assert (book.find("m_3f2a7b"), book.find("m_000000")) == (book.memos[0], None)


class TestTheBookIsAnAggregate:
    """MemoBook が、持ち主の BeingId を持ち、変えた操作をイベントとしてため、決まりに反した操作では何も変えないことを保証する。"""

    def test_an_empty_book_knows_its_being(self) -> None:
        """空のメモ帳は、渡した Being の ID を持ち、メモもイベントも無い。"""
        book = MemoBook.empty(ADA)

        assert (book.being_id, book.memos, book.get_events()) == (ADA, (), [])

    def test_a_book_without_a_being_id_is_rejected(self) -> None:
        """BeingId でない持ち主を渡すと MemoValidationException を投げる。"""
        with pytest.raises(MemoValidationException):
            MemoBook("being-ada")  # type: ignore[arg-type]

    def test_adding_records_memo_added_with_the_new_memo(self) -> None:
        """足すと、足したメモと持ち主を持つ MemoAdded が 1 件たまる。"""
        book = _add(MemoBook.empty(ADA))

        (event,) = book.get_events()
        assert isinstance(event, MemoAdded)
        assert (event.being_id, event.memo) == (ADA, book.memos[0])

    def test_editing_records_memo_edited_with_the_rewritten_memo(self) -> None:
        """書き換えると、書き換えたあとのメモを持つ MemoEdited が 1 件たまる。"""
        book = _add(MemoBook.empty(ADA))
        book.clear_events()

        book.edit("m_3f2a7b", text="事務所の金庫で鍵を取る", turn=8)

        (event,) = book.get_events()
        assert isinstance(event, MemoEdited)
        assert (event.being_id, event.memo) == (ADA, book.memos[0])

    def test_removing_records_memo_removed_with_the_removed_memo(self) -> None:
        """消すと、消したメモを持つ MemoRemoved が 1 件たまる。"""
        book = _add(MemoBook.empty(ADA))
        memo = book.memos[0]
        book.clear_events()

        book.remove("m_3f2a7b")

        (event,) = book.get_events()
        assert isinstance(event, MemoRemoved)
        assert (event.being_id, event.memo) == (ADA, memo)

    def test_each_event_has_its_own_id(self) -> None:
        """続けて変えると、イベントは変えた順にたまり、ID がそれぞれ違う。"""
        book = _add(_add(MemoBook.empty(ADA)), memo_id=SECOND_ID, text="水門を見に行く")

        events = book.get_events()

        assert [type(e) for e in events] == [MemoAdded, MemoAdded]
        assert events[0].event_id != events[1].event_id

    @pytest.mark.parametrize(
        "operation",
        [
            lambda book: _add(book, memo_id=_id(99), text="あ" * 61),
            lambda book: _add(book),
            lambda book: book.edit("m_000000", text="鍵を取る", turn=8),
            lambda book: book.edit("m_3f2a7b", text="鍵を取る", turn=1),
            lambda book: book.remove("m_000000"),
            lambda book: _add(book, memo_id=_id(99), kind=MemoKind.FACT, provenance=FROM_UNKNOWN_EPISODE),
            lambda book: book.edit("m_3f2a7b", text="鍵を取る", provenance=SURE_BY_SELF, turn=8),
        ],
        ids=[
            "too_long",
            "same_id",
            "edit_unknown",
            "edit_back_in_time",
            "remove_unknown",
            "unknown_episode",
            "provenance_on_a_todo",
        ],
    )
    def test_a_rejected_operation_changes_nothing(self, operation) -> None:
        """決まりに反する操作は例外を投げ、メモもためたイベントも変えない。"""
        book = _add(MemoBook.empty(ADA))
        memos, events = book.memos, book.get_events()

        with pytest.raises((MemoValidationException, MemoNotFoundException)):
            operation(book)

        assert (book.memos, book.get_events()) == (memos, events)

    def test_adding_beyond_the_limit_changes_nothing(self) -> None:
        """上限に届いたやることにもう 1 件足すと MemoLimitReachedException を投げ、メモもためたイベントも変えない。"""
        book = _add_many(MemoKind.TODO, KIND_LIMITS[MemoKind.TODO])
        memos, events = book.memos, book.get_events()

        with pytest.raises(MemoLimitReachedException):
            _add(book, memo_id=_id(99))

        assert (book.memos, book.get_events()) == (memos, events)

    def test_clear_events_drops_the_recorded_events(self) -> None:
        """clear_events のあとは、ためたイベントが無い。メモは残る。"""
        book = _add(MemoBook.empty(ADA))

        book.clear_events()

        assert (book.get_events(), len(book.memos)) == ([], 1)
