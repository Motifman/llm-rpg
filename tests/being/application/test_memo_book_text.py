from __future__ import annotations

from ai_rpg_world.being.application.memo_book_text import format_memo_book
from ai_rpg_world.being.domain.memo_book import (
    MemoBook,
    MemoCertainty,
    MemoKind,
    MemoProvenance,
    MemoSource,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId

ADA = BeingId("being-ada")
HERE = "水門の町"
MINE = "廃坑の山村"


def _add(book: MemoBook, serial: int, kind: MemoKind, text: str, *, provenance=None, where: str = HERE) -> MemoBook:
    """足したあとの同じメモ帳を返す。試験で足すのを続けて書くため。"""
    book.add(
        memo_id=f"{serial:06x}aa-1d2e-4f00-8a00-000000000000",
        kind=kind,
        text=text,
        provenance=provenance,
        turn=serial,
        environment_name=where,
        known_episode_handles={"ep_a07c33"},
    )
    return book


class TestFormatMemoBook:
    """format_memo_book が、分類ごとの見出しの下に書いた順でメモを並べ、空の分類と前にいた場所のメモも分かる形にすることを保証する。"""

    def test_empty_book_shows_every_heading_with_none(self) -> None:
        """メモが 1 件も無いとき、3 つの分類の見出しをどれも出し、その下に (なし) と書く。"""
        assert format_memo_book(MemoBook.empty(ADA), current_environment_name=HERE) == (
            "やること:\n  (なし)\n分かったこと:\n  (なし)\n人について:\n  (なし)"
        )

    def test_memos_are_grouped_by_kind_in_written_order(self) -> None:
        """メモは分類の見出しの下に、呼び名と文で、書いた順に並ぶ。"""
        book = _add(MemoBook.empty(ADA), 1, MemoKind.TODO, "事務所で鍵を取る")
        book = _add(book, 2, MemoKind.PERSON, "ミオは水門に詳しい")
        book = _add(book, 3, MemoKind.TODO, "水門を見に行く")

        assert format_memo_book(book, current_environment_name=HERE) == (
            "やること:\n"
            "  [m_000001] 事務所で鍵を取る\n"
            "  [m_000003] 水門を見に行く\n"
            "分かったこと:\n"
            "  (なし)\n"
            "人について:\n"
            "  [m_000002] ミオは水門に詳しい"
        )

    def test_facts_show_source_and_certainty(self) -> None:
        """分かったことには、出どころと確かさを括弧で添える。確かなら確かさは書かず、推測なら推測と書く。"""
        cases = [
            MemoProvenance(source=MemoSource.SELF, certainty=MemoCertainty.SURE),
            MemoProvenance(source=MemoSource.SELF, certainty=MemoCertainty.GUESS),
            MemoProvenance(source=MemoSource.HEARD, certainty=MemoCertainty.SURE, source_from="ミオ"),
            MemoProvenance(source=MemoSource.HEARD, certainty=MemoCertainty.GUESS, source_from="ミオ"),
            MemoProvenance(source=MemoSource.EPISODE, certainty=MemoCertainty.GUESS, source_from="ep_a07c33"),
        ]
        book = MemoBook.empty(ADA)
        for serial, provenance in enumerate(cases, start=1):
            book = _add(book, serial, MemoKind.FACT, f"事実{serial}", provenance=provenance)

        lines = format_memo_book(book, current_environment_name=HERE).split("\n")[3:8]

        assert lines == [
            "  [m_000001] 事実1 (自分で確かめた)",
            "  [m_000002] 事実2 (自分の推測)",
            "  [m_000003] 事実3 (ミオから聞いた)",
            "  [m_000004] 事実4 (ミオから聞いた・推測)",
            "  [m_000005] 事実5 (ep_a07c33 の記憶から・推測)",
        ]

    def test_memos_from_another_environment_are_grouped_under_its_name(self) -> None:
        """今と違う環境で書いたメモは、分類の中で今の環境のメモの後ろに、環境ごとの見出しでまとめて出す。"""
        sure = MemoProvenance(source=MemoSource.SELF, certainty=MemoCertainty.SURE)
        book = _add(MemoBook.empty(ADA), 1, MemoKind.FACT, "籠は 3 人まで", provenance=sure, where=MINE)
        book = _add(book, 2, MemoKind.FACT, "水門を開けると近道が沈む", provenance=sure)
        book = _add(book, 3, MemoKind.FACT, "発電機は温めてから使う", provenance=sure, where=MINE)

        assert format_memo_book(book, current_environment_name=HERE).split("\n")[2:8] == [
            "分かったこと:",
            "  [m_000002] 水門を開けると近道が沈む (自分で確かめた)",
            f"  前にいた場所 ({MINE}) で:",
            "  [m_000001] 籠は 3 人まで (自分で確かめた)",
            "  [m_000003] 発電機は温めてから使う (自分で確かめた)",
            "人について:",
        ]
