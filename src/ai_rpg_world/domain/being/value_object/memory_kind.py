"""Beingが所有する記憶の種類を宣言するenum。

宣言は記憶の内容を保持しない。各記憶の保存先への読み書きは別に行う。
"""

from __future__ import annotations

from enum import Enum


class MemoryKind(str, Enum):
    """Being が所有しうる記憶 store の種類。

    str を継承しているのは、シリアライズ時に enum value を文字列として扱える
    ようにするため。
    """

    SHORT_TERM = "short_term"
    EPISODIC = "episodic"
    MEMO = "memo"


__all__ = ["MemoryKind"]
