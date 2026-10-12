"""メモ帳を、毎ターンのプロンプトの【メモ】に出す文にする (#1628)。"""

from __future__ import annotations

from ai_rpg_world.being.domain.memo_book import (
    Memo,
    MemoBook,
    MemoCertainty,
    MemoKind,
    MemoProvenance,
    MemoSource,
)

MEMO_BOOK_HEADING = "【メモ】"

KIND_HEADINGS = {
    MemoKind.TODO: "やること",
    MemoKind.FACT: "分かったこと",
    MemoKind.PERSON: "人について",
}


def _provenance_text(provenance: MemoProvenance) -> str:
    guess = provenance.certainty is MemoCertainty.GUESS
    if provenance.source is MemoSource.SELF:
        return "自分の推測" if guess else "自分で確かめた"
    if provenance.source is MemoSource.HEARD:
        where = f"{provenance.source_from}から聞いた"
    else:
        where = f"{provenance.source_from} の記憶から"
    return f"{where}・推測" if guess else where


def _line(memo: Memo) -> str:
    suffix = "" if memo.provenance is None else f" ({_provenance_text(memo.provenance)})"
    return f"  [{memo.handle}] {memo.text}{suffix}"


def format_memo_book(book: MemoBook, *, current_environment_name: str) -> str:
    """空の分類も見出しを出す。何を書けるかを、毎ターン同じ形で見せるため。

    前にいた環境のメモは 1 件ずつ添えず、環境ごとの見出しでまとめる。
    """
    lines: list[str] = []
    for kind, heading in KIND_HEADINGS.items():
        lines.append(f"{heading}:")
        memos = [m for m in book.memos if m.kind is kind]
        if not memos:
            lines.append("  (なし)")
            continue
        lines.extend(_line(m) for m in memos if m.environment_name == current_environment_name)
        elsewhere: dict[str, list[Memo]] = {}
        for memo in memos:
            if memo.environment_name != current_environment_name:
                elsewhere.setdefault(memo.environment_name, []).append(memo)
        for environment_name, grouped in elsewhere.items():
            lines.append(f"  前にいた場所 ({environment_name}) で:")
            lines.extend(_line(m) for m in grouped)
    return "\n".join(lines)


__all__ = ["KIND_HEADINGS", "MEMO_BOOK_HEADING", "format_memo_book"]
