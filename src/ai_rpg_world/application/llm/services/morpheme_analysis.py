"""文を形態素解析し、中身のある語だけを取り出す (#1498)。

文字の 2 字組は語尾 (「った」「ている」) も中身のある語と同じに数え、1 文字の語
(「水」) を比べられない。品詞で助詞・助動詞・記号・数を外し、動詞と形容詞は
原形にそろえる。

辞書に無い語 (このゲームの人名や地名) は、どちらの解析器も未知の名詞として切り出す
ので、名詞の決まりのまま残る。切られ方は解析器ごとに違い、比べた結果は
``docs/experiments/issue_1498_narrower_comparison/`` にある。

解析器の構築は辞書を読むので重い。プロセスで 1 つだけ作り、tokenize はロックで
1 つずつ通す (どちらの解析器もスレッドをまたいだ共有を保証していない)。辞書は
``JanomeAnalyzer()`` / ``SudachiAnalyzer()`` を作る時点で読む。最初の想起まで遅らせると、
読めないときに想起が毎ターン失敗したまま run が最後まで走る。
"""

from __future__ import annotations

import threading
import unicodedata
from collections.abc import Callable
from functools import cache
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from janome.tokenizer import Tokenizer as JanomeTokenizer
    from sudachipy import Tokenizer as SudachiTokenizer


class MorphemeAnalyzer(Protocol):
    def content_words(self, text: str) -> list[str]:
        """文に出る順で、中身のある語を返す。同じ語は出た回数だけ並ぶ。"""
        ...


def split_at_separators(text: str) -> list[str]:
    """NFKC と小文字にそろえ、改行・句読点・空白・記号で区切る。

    区切らずに渡すと、Janome は記号の並び (「）。」) を未知の名詞にし、その直後の
    「水」を接尾辞と解析した。
    """
    pieces: list[str] = []
    current: list[str] = []
    for ch in unicodedata.normalize("NFKC", text).lower():
        if unicodedata.category(ch).startswith(("P", "Z", "C", "S")):
            if current:
                pieces.append("".join(current))
                current = []
        else:
            current.append(ch)
    if current:
        pieces.append("".join(current))
    return pieces


_JANOME_DROPPED_NOUNS = frozenset({"数", "非自立", "代名詞", "接尾"})


class JanomeAnalyzer:
    """Janome (IPADIC を同梱) で解析する。"""

    def __init__(self) -> None:
        self._tokenizer, self._lock = _load("Janome", _janome)

    def content_words(self, text: str) -> list[str]:
        with self._lock:
            tokens = [
                t for piece in split_at_separators(text) for t in self._tokenizer.tokenize(piece)
            ]
        words: list[str] = []
        for token in tokens:
            pos, pos1 = token.part_of_speech.split(",")[:2]
            if (pos == "名詞" and pos1 not in _JANOME_DROPPED_NOUNS) or (
                pos in ("動詞", "形容詞") and pos1 == "自立"
            ):
                words.append(token.surface if token.base_form == "*" else token.base_form)
        return words


class SudachiAnalyzer:
    """SudachiPy (辞書は sudachidict_core) の短い単位で解析する。

    短い単位にするのは、「観測拠点跡」と「観測拠点」のように一部だけ重なる名前を、
    重なる語で当てるため。語は表記ゆれをそろえた正規化形 (「キノコ」→「茸」) にする。
    """

    def __init__(self) -> None:
        self._tokenizer, self._lock = _load("SudachiPy", _sudachi)

    def content_words(self, text: str) -> list[str]:
        from sudachipy import SplitMode

        with self._lock:
            morphemes = [
                (m.part_of_speech(), m.normalized_form())
                for piece in split_at_separators(text)
                for m in self._tokenizer.tokenize(piece, SplitMode.A)
            ]
        words: list[str] = []
        for (pos, pos1, *_), word in morphemes:
            if (
                (pos == "名詞" and pos1 not in ("数詞", "助動詞語幹"))
                or (pos in ("動詞", "形容詞") and pos1 != "非自立可能")
                or (pos == "形状詞" and pos1 != "助動詞語幹")
            ):
                words.append(word)
        return words


_LOAD_LOCK = threading.Lock()


def _load(
    label: str, loader: Callable[[], tuple[Any, threading.Lock]]
) -> tuple[Any, threading.Lock]:
    try:
        with _LOAD_LOCK:
            return loader()
    except Exception as exc:
        raise RuntimeError(
            f"{label} とその辞書を読み込めない。`uv sync` で依存を入れ直す"
        ) from exc


@cache
def _janome() -> tuple[JanomeTokenizer, threading.Lock]:
    from janome.tokenizer import Tokenizer

    return Tokenizer(), threading.Lock()


@cache
def _sudachi() -> tuple[SudachiTokenizer, threading.Lock]:
    from sudachipy import Dictionary

    return Dictionary(dict="core").create(), threading.Lock()


__all__ = ["JanomeAnalyzer", "MorphemeAnalyzer", "SudachiAnalyzer", "split_at_separators"]
