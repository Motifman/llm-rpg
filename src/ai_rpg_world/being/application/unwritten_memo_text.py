"""行動と一緒に書こうとして書けなかったメモの操作を、【直近の出来事】で本人に返す文。

番号 (「2 件目」) ではなく操作の中身で言う。番号では、どの操作のことかを本人が読み取れない (D2240)。
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from ai_rpg_world.being.application.memo_arguments import (
    REJECTED_FROM_NOT_NEEDED,
    REJECTED_INVALID,
    REJECTED_LIMIT_REACHED,
    REJECTED_MISSING_EPISODE_FROM,
    REJECTED_MISSING_FROM,
    REJECTED_MISSING_ID,
    REJECTED_MISSING_PROVENANCE,
    REJECTED_MISSING_TEXT,
    REJECTED_NO_SUCH_MEMO,
    REJECTED_NOT_A_LIST,
    REJECTED_NOT_AN_OBJECT,
    REJECTED_PROVENANCE_OUTSIDE_FACT,
    REJECTED_TEXT_TOO_LONG,
    REJECTED_UNKNOWN_DO,
    REJECTED_UNKNOWN_EPISODE,
    REJECTED_UNKNOWN_KIND,
)
from ai_rpg_world.being.application.write_memos import UnwrittenMemo
from ai_rpg_world.being.domain.memo_book import KIND_LIMITS, MEMO_TEXT_MAX_LENGTH, MemoKind

WHOLE_MEMO = "メモの書き込み"

_KIND_LABELS = {MemoKind.TODO: "やること", MemoKind.FACT: "分かったこと", MemoKind.PERSON: "人について"}
_KIND_PLACES = {MemoKind.TODO: "やることに", MemoKind.FACT: "分かったことに", MemoKind.PERSON: "人についてのメモに"}

_SHORT_REASONS = {
    REJECTED_NOT_A_LIST: "memo は操作の配列で書く",
    REJECTED_NOT_AN_OBJECT: '操作は {"do": ...} の形で書く',
    REJECTED_UNKNOWN_DO: "do は add / edit / remove のどれか",
    REJECTED_UNKNOWN_KIND: "kind は todo / fact / person のどれか",
    REJECTED_MISSING_TEXT: "text が空",
    REJECTED_TEXT_TOO_LONG: f"text は {MEMO_TEXT_MAX_LENGTH} 字まで",
    REJECTED_MISSING_ID: "id に m_ で始まる呼び名がない",
    REJECTED_MISSING_PROVENANCE: "分かったことには source と certainty が要る",
    REJECTED_MISSING_FROM: "人から聞いたことには from に誰から聞いたかが要る",
    REJECTED_MISSING_EPISODE_FROM: "エピソードから分かったことには from にエピソードの呼び名が要る",
    REJECTED_FROM_NOT_NEEDED: "自分で確かめたことには from を書かない",
    REJECTED_PROVENANCE_OUTSIDE_FACT: "source と certainty は分かったことにだけ書ける",
    REJECTED_NO_SUCH_MEMO: "そのメモはない",
    REJECTED_UNKNOWN_EPISODE: "そのエピソードはない",
    REJECTED_INVALID: "書けない形だった",
}


def unwritten_memo_lines(unwritten: Iterable[UnwrittenMemo]) -> tuple[str, ...]:
    """書かれていた順に並べる。引数ごと崩れていたときの行は先頭に置く。"""
    return tuple(
        unwritten_memo_line(
            WHOLE_MEMO if u.index is None else attempted_raw_operation(u.raw), short_reason(u.reason, kind=u.kind)
        )
        for u in sorted(unwritten, key=lambda u: -1 if u.index is None else u.index)
    )


def unwritten_memo_line(attempted: str, reason: str) -> str:
    return f"「{attempted}」は書けなかった（理由: {reason}）"


def attempted_raw_operation(raw: object) -> str:
    """読めなかった操作は、書かれていた do・kind・text・id のうち読めたものから言う。"""
    if not isinstance(raw, dict) or raw.get("do") not in ("add", "edit", "remove"):
        return json.dumps(raw, ensure_ascii=False)
    text = _text(raw.get("text"))
    handle = _text(raw.get("id"))
    if raw["do"] == "remove":
        return f"{handle} を消す" if handle else "メモを消す"
    if raw["do"] == "edit":
        if handle and text:
            return f"{handle} を「{text}」に書き換える"
        return f"{handle} を書き換える" if handle else "メモを書き換える"
    if not text:
        return "メモを足す"
    kind = next((k for k in MemoKind if k.value == raw.get("kind")), None)
    return f"「{text}」を書く" if kind is None else f"{_KIND_PLACES[kind]}「{text}」を書く"


def short_reason(reason: str, *, kind: MemoKind | None = None) -> str:
    """操作の中身と重ならない短い理由。操作の側で呼び名を言うので、理由では繰り返さない。"""
    if reason == REJECTED_LIMIT_REACHED and kind is not None:
        return f"{_KIND_LABELS[kind]}が上限の {KIND_LIMITS[kind]} 件。消すか書き換える"
    return _SHORT_REASONS.get(reason, _SHORT_REASONS[REJECTED_INVALID])


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
